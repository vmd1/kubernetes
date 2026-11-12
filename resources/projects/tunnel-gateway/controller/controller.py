#!/usr/bin/env python3
"""TunnelAgent controller for the tunnel gateway (standard library only, so it runs on a stock python image).

Watches TunnelAgent objects (tunnel.vmd1.homelab/v1alpha1) in its own namespace and keeps two things true:

  * every agent has a Secret `agent-<name>` holding its credentials and a ready-made `agent.env` (the three secrets,
    its gateway URLs, its reverse ports). Secrets are random per agent, rotated on a schedule or on demand, and the
    previous ones stay valid for a grace period so a running agent is not cut off the moment a rotation happens.
  * the Secret `tunnel-gateway-restrictions` holds the wstunnel `--restrict-config` file rendered from all agents that
    are not suspended. The gateway pods only read it (deny by default: no agents means no access).

Status goes back onto each TunnelAgent (Ready condition, gateway, ports, rotation times, and when and how it last
connected: lastSeen / connectionType, read from the gateway pods' wstunnel logs).
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import signal
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone

GROUP = "tunnel.vmd1.homelab"
VERSION = "v1alpha1"
PLURAL = "tunnelagents"
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"

ANN = "tunnel.vmd1.homelab/"  # annotations on the per-agent Secret
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,40}[a-z0-9])?$")
EXPOSE_RE = re.compile(r"^[a-z0-9]{1,16}$")

log = logging.getLogger("tunnel-controller")


def env(name, default):
    return os.environ.get(name, default)


class Config:
    def __init__(self, e=None):
        e = os.environ if e is None else e
        self.gateways = int(e.get("GATEWAYS", "2"))
        # One hostname per replica (reverse tunnels live there); a comma list gives the same replica under several domains,
        # tried in order by the agent.
        self.gateway_hosts = [h.strip() for h in e.get(
            "GATEWAY_HOST", "coordination-{i}.vmd1.homelab,coordination-{i}.vmd1.homelab,coordination-{i}.vmd1.homelab").split(",") if h.strip()]
        # Any replica: the unprivileged pathways are stateless. A comma list is tried in order.
        self.via_url = e.get("VIA_URL", "wss://coordination.vmd1.homelab,wss://coordination.vmd1.homelab,wss://coordination.vmd1.homelab")
        lo, _, hi = e.get("PORT_RANGE", "20000-20999").partition("-")
        self.port_lo, self.port_hi = int(lo), int(hi)
        self.cidrs = [c.strip() for c in e.get("AGENT_CIDRS", "XXX.XXX.XXX.XXX/16,XXX.XXX.XXX.XXX/16,XXX.XXX.XXX.XXX/16").split(",") if c.strip()]
        self.canary = e.get("TUNNEL_CANARY", "XXX.XXX.XXX.XXX:53")
        self.restrictions_secret = e.get("RESTRICTIONS_SECRET", "tunnel-gateway-restrictions")
        self.poll = int(e.get("POLL_INTERVAL", "15"))
        self.default_rotate = e.get("DEFAULT_ROTATE_AFTER", "never")
        self.default_grace = e.get("DEFAULT_GRACE", "24h")
        # Where connections are observed: the wstunnel container of each gateway pod. lastSeen is rewritten only when it has
        # moved by at least this many seconds (or the connection type changed), so a busy agent is not a write every poll.
        # Lab bridges (spec.bridge): one pod per agent in BRIDGE_NAMESPACE, a Tailscale device that forwards every port to the agent
        # over WireGuard. The agent reaches its bridge over direct UDP on a NodePort (BRIDGE_PORT_BASE + slot, so BRIDGE_SLOTS
        # bridges at most; oci/firewall opens the same range) or the same UDP inside the wss tunnel.
        self.bridge_ns = e.get("BRIDGE_NAMESPACE", "tunnel-bridge")
        self.bridge_image = e.get("BRIDGE_IMAGE", "ghcr.io/vmd1/tunnel-bridge:latest")
        self.bridge_slots = int(e.get("BRIDGE_SLOTS", "16"))
        self.bridge_port_base = int(e.get("BRIDGE_PORT_BASE", "31820"))
        self.bridge_wg_port = 51820
        self.bridge_mtu = int(e.get("BRIDGE_MTU", "1100"))  # both ends; > ~1170 does not fit the 1230-byte pod MTU and the link stalls
        self.bridge_pull_policy = e.get("BRIDGE_PULL_POLICY", "")  # empty: Kubernetes' default (Always for :latest)
        self.bridge_endpoint_hosts = [h.strip() for h in e.get(
            "BRIDGE_ENDPOINT_HOSTS", "coordination.vmd1.homelab,coordination.vmd1.homelab,coordination.vmd1.homelab").split(",") if h.strip()]
        # Enrollment: an agent trades a short-lived 3-use token (Secret enroll-<name>, created by tunnel-agent/scripts/make-provision.sh,
        # only its hash is stored) for its whole agent.env, at https://coordination.<domain>/enroll (ingressroute.yaml).
        self.enroll_port = int(e.get("ENROLL_PORT", "8080"))
        self.enroll_common = e.get("ENROLL_COMMON_SECRET", "tunnel-enroll-common")  # TS_AUTHKEY, CANARY (and for /setup: SSH_PUBKEY, ADMIN_USER, REGISTRY_*), same for every agent
        self.setup_template = e.get("SETUP_TEMPLATE", "/code/provision.template.sh")
        self.pod_prefix = e.get("GATEWAY_POD_PREFIX", "tunnel-gateway")
        self.seen_resolution = int(e.get("LAST_SEEN_RESOLUTION", "300"))


# ---------------------------------------------------------------- pure logic

def parse_duration(text, default=None):
    """'30m', '12h', '90d', bare seconds. 'never' (or 0) gives None. Garbage gives the default."""
    t = str(text if text is not None else "").strip().lower()
    if t in ("never", "0"):
        return None
    m = re.fullmatch(r"(\d+)\s*([smhd]?)", t)
    if not m:
        return default
    return max(60, int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)])


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text):
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def new_secret():
    return secrets.token_hex(24)  # hex: safe in a URL path and inside a regex


def expose_list(spec):
    """The services an agent publishes: [{name, port, tailnetPort}]; default is ssh on 22."""
    items = spec.get("expose")
    if items is None:
        items = [{"name": "ssh", "port": 22}]
    return items


def validate(agent, cfg):
    """Return a problem string, or None when the TunnelAgent is usable."""
    name = agent["metadata"]["name"]
    if not NAME_RE.match(name):
        return f"name {name!r} must be lowercase letters, digits and dashes (max 42)"
    if name.endswith(("-via", "-client")):
        return f"name {name!r} must not end in -via or -client (those are the gateway's restriction names for its credentials)"
    seen = set()
    for e in expose_list(agent.get("spec", {})):
        n, p = e.get("name"), e.get("port")
        if not isinstance(n, str) or not EXPOSE_RE.match(n):
            return f"expose name {n!r} must be 1-16 lowercase letters or digits"
        if n in seen:
            return f"expose name {n!r} appears twice"
        seen.add(n)
        if not isinstance(p, int) or not 1 <= p <= 65535:
            return f"expose {n}: port {p!r} must be 1-65535"
    if agent.get("spec", {}).get("bridge") not in (None, True, False):
        return "bridge must be true or false"
    gw = agent.get("spec", {}).get("gateway")
    if gw is not None and not (isinstance(gw, int) and 0 <= gw < cfg.gateways):
        return f"gateway must be 0..{cfg.gateways - 1}"
    return None


def assign_ports(agents, cfg):
    """{agent name: {expose name: reverse port}}. Ports are unique across all agents (an agent that fails over to the
    other gateway replica keeps its port there) and stable: a port already in an agent's status is kept unless it is
    out of range or taken. Oldest agents win a conflict."""
    order = sorted(agents, key=lambda a: (a["metadata"].get("creationTimestamp", ""), a["metadata"]["name"]))
    taken, out = set(), {}
    for a in order:
        have = (a.get("status") or {}).get("ports") or {}
        for e in expose_list(a.get("spec", {})):
            p = have.get(e["name"])
            if isinstance(p, int) and cfg.port_lo <= p <= cfg.port_hi and p not in taken:
                taken.add(p)
                out.setdefault(a["metadata"]["name"], {})[e["name"]] = p
    for a in order:
        mine = out.setdefault(a["metadata"]["name"], {})
        for e in expose_list(a.get("spec", {})):
            if e["name"] in mine:
                continue
            p = next((x for x in range(cfg.port_lo, cfg.port_hi + 1) if x not in taken), None)
            if p is None:
                raise RuntimeError("reverse port range exhausted")
            taken.add(p)
            mine[e["name"]] = p
    return out


def pick_gateway(agent, cfg):
    pinned = agent.get("spec", {}).get("gateway")
    if pinned is not None:
        return pinned
    return int(hashlib.sha256(agent["metadata"]["name"].encode()).hexdigest(), 16) % cfg.gateways


def gateway_urls(first, cfg):
    """Gateway URLs for an agent: its own replica first (under every domain), then the others as failover."""
    order = [first] + [i for i in range(cfg.gateways) if i != first]
    return ["wss://" + h.format(i=i) for i in order for h in cfg.gateway_hosts]


def plan_credentials(agent, existing, cfg, now):
    """Decide the agent's credentials. `existing` is the decoded data + annotations of its Secret (or None).
    Returns (data, annotations, rotated). data keys: VIA, AGENT, CLIENT and, during a grace period, *_PREVIOUS."""
    spec = agent.get("spec", {})
    token = str(spec.get("rotationToken") or "")
    after = parse_duration(spec.get("rotateAfter"), parse_duration(cfg.default_rotate))
    grace = parse_duration(spec.get("rotationGrace"), parse_duration(cfg.default_grace, 86400)) or 86400
    keys = ("VIA", "AGENT", "CLIENT")
    ex = existing or {"data": {}, "annotations": {}}
    data, ann = dict(ex["data"]), dict(ex["annotations"])
    rotated_at = parse_iso(ann.get(ANN + "rotated-at"))
    have = all(data.get(k) for k in keys) and rotated_at is not None
    due = have and after is not None and now >= rotated_at + timedelta(seconds=after)
    asked = have and token != ann.get(ANN + "rotation-token", "")
    rotated = (not have) or due or asked
    if rotated:
        for k in keys:
            if have:
                data[k + "_PREVIOUS"] = data[k]
            data[k] = new_secret()
        ann[ANN + "rotated-at"] = iso(now)
        ann[ANN + "rotation-token"] = token
        if have:
            ann[ANN + "previous-until"] = iso(now + timedelta(seconds=grace))
    until = parse_iso(ann.get(ANN + "previous-until"))
    if until is not None and now >= until:  # grace is over: the old credentials stop working
        for k in keys:
            data.pop(k + "_PREVIOUS", None)
        ann.pop(ANN + "previous-until", None)
    return data, ann, rotated


def valid_secrets(data, kind):
    return [v for v in (data.get(kind), data.get(kind + "_PREVIOUS")) if v]


# ---------------------------------------------------------------- lab bridge (WireGuard)

_P, _A24 = 2 ** 255 - 19, 121665


def x25519(k, u):
    """RFC 7748 scalar multiplication (Python has no X25519 in the standard library). k, u: 32 bytes; returns 32 bytes."""
    kb = bytearray(k)
    kb[0] &= 248
    kb[31] &= 127
    kb[31] |= 64
    n = int.from_bytes(kb, "little")
    x1 = int.from_bytes(u, "little") & ((1 << 255) - 1)
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in range(254, -1, -1):
        bit = (n >> t) & 1
        swap ^= bit
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = bit
        a, b = (x2 + z2) % _P, (x2 - z2) % _P
        aa, bb = a * a % _P, b * b % _P
        e = (aa - bb) % _P
        c, d = (x3 + z3) % _P, (x3 - z3) % _P
        da, cb = d * a % _P, c * b % _P
        x3, z3 = pow(da + cb, 2, _P), x1 * pow(da - cb, 2, _P) % _P
        x2, z2 = aa * bb % _P, e * (aa + _A24 * e) % _P
    if swap:
        x2, x3, z2, z3 = x3, x2, z3, z2
    return (x2 * pow(z2, _P - 2, _P) % _P).to_bytes(32, "little")


def wg_private():
    return base64.b64encode(os.urandom(32)).decode()


_PUB = {}


def wg_public(private_b64):
    """The WireGuard public key (base64) for a base64 private key. The clamping happens inside x25519."""
    if private_b64 not in _PUB:
        _PUB[private_b64] = base64.b64encode(x25519(base64.b64decode(private_b64), (9).to_bytes(32, "little"))).decode()
    return _PUB[private_b64]


def bridge_wanted(agent):
    return agent.get("spec", {}).get("bridge") is True and not agent.get("spec", {}).get("suspended")


def assign_bridge_slots(agents, cfg):
    """{agent name: slot} for agents that want a bridge. A slot is an index into the WireGuard addresses (10.99.<slot>.0/30) and
    the NodePorts; stable (kept from status.bridge.slot unless out of range or taken), oldest agent wins a conflict."""
    order = sorted((a for a in agents if bridge_wanted(a)), key=lambda a: (a["metadata"].get("creationTimestamp", ""), a["metadata"]["name"]))
    taken, out = set(), {}
    for a in order:
        have = ((a.get("status") or {}).get("bridge") or {}).get("slot")
        if isinstance(have, int) and 0 <= have < cfg.bridge_slots and have not in taken:
            taken.add(have)
            out[a["metadata"]["name"]] = have
    for a in order:
        n = a["metadata"]["name"]
        if n in out:
            continue
        slot = next((x for x in range(cfg.bridge_slots) if x not in taken), None)
        if slot is None:
            raise RuntimeError(f"bridge slots exhausted ({cfg.bridge_slots}); raise BRIDGE_SLOTS and open the NodePorts")
        taken.add(slot)
        out[n] = slot
    return out


def bridge_host(name, cfg):
    """The cluster DNS name of an agent's bridge Service, which the gateway pod dials for the UDP-in-wss pathway."""
    return f"bridge-{name}.{cfg.bridge_ns}.svc.cluster.local"


def bridge_info(name, slot, cfg):
    return {"slot": slot, "address": f"10.99.{slot}.1", "agentAddress": f"10.99.{slot}.2",
            "nodePort": cfg.bridge_port_base + slot, "host": bridge_host(name, cfg)}


def ensure_wg(data, rotated):
    """Generate the agent's and the bridge's WireGuard private keys when missing, and again on a rotation."""
    data = dict(data)
    if rotated or not data.get("WG_AGENT") or not data.get("WG_BRIDGE"):
        data["WG_AGENT"], data["WG_BRIDGE"] = wg_private(), wg_private()
    return data


def bridge_labels(name):
    return {"app.kubernetes.io/name": "tunnel-bridge", "app.kubernetes.io/instance": f"bridge-{name}",
            "app.kubernetes.io/managed-by": "tunnel-controller", "tunnel.vmd1.homelab/agent": name}


def bridge_resources(name, info, data, cfg):
    """[(kind, body)] for one agent's bridge: its Secret (WireGuard config), the Deployment (a privileged pod: tailscaled needs
    /dev/net/tun and the namespace is the one place that is allowed) and a NodePort UDP Service for the direct pathway."""
    ns, bn = cfg.bridge_ns, f"bridge-{name}"
    labels = bridge_labels(name)
    secret = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque", "metadata": {"name": bn, "namespace": ns, "labels": labels},
              "stringData": {"WG_PRIVATE_KEY": data["WG_BRIDGE"], "WG_PEER_PUBKEY": wg_public(data["WG_AGENT"]),
                             "WG_ADDRESS": f"{info['address']}/30", "WG_PEER_IP": info["agentAddress"],
                             "WG_LISTEN_PORT": str(cfg.bridge_wg_port), "WG_MTU": str(cfg.bridge_mtu), "TS_HOSTNAME": f"{name}-bridge"}}
    deploy = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": bn, "namespace": ns, "labels": labels},
              "spec": {"replicas": 1, "strategy": {"type": "Recreate"},
                       "selector": {"matchLabels": {"app.kubernetes.io/instance": bn}},
                       # The bridge reads its Secret once, as environment: a hash of it in the pod template rolls the pod when the keys change
                       # (a rotation), otherwise it would keep the old ones and the agent's new keys would never match.
                       "template": {"metadata": {"labels": labels, "annotations": {
                           "tunnel.vmd1.homelab/config-hash": hashlib.sha256(json.dumps(secret["stringData"], sort_keys=True).encode()).hexdigest()[:16]}},
                                    "spec": {"automountServiceAccountToken": False, "enableServiceLinks": False,
                                             "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
                                             # Never the small ingress nodes, and never the control-plane node (hades-01 is memory-starved and
                                             # a bridge pod there would make the cluster's control plane worse): the lab workers only.
                                             "affinity": {"nodeAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": {"nodeSelectorTerms": [
                                                 {"matchExpressions": [{"key": "node-role.kubernetes.io/ingress", "operator": "DoesNotExist"},
                                                                       {"key": "node-role.kubernetes.io/control-plane", "operator": "DoesNotExist"}]}]}}},
                                             "containers": [{
                                                 "name": "bridge", "image": cfg.bridge_image,
                                                 **({"imagePullPolicy": cfg.bridge_pull_policy} if cfg.bridge_pull_policy else {}),
                                                 "securityContext": {"privileged": True},
                                                 "envFrom": [{"secretRef": {"name": bn}}],
                                                 "env": [{"name": "TS_AUTHKEY", "valueFrom": {"secretKeyRef": {"name": "bridge-authkey", "key": "TS_AUTHKEY"}}}],
                                                 "resources": {"requests": {"cpu": "20m", "memory": "48Mi"}, "limits": {"cpu": "500m", "memory": "192Mi"}},
                                                 "volumeMounts": [{"name": "state", "mountPath": "/var/lib/tailscale"}]}],
                                             "volumes": [{"name": "state", "emptyDir": {"sizeLimit": "64Mi"}}]}}}}
    service = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": bn, "namespace": ns, "labels": labels},
               "spec": {"type": "NodePort", "selector": {"app.kubernetes.io/instance": bn},
                        "ports": [{"name": "wireguard", "protocol": "UDP", "port": cfg.bridge_wg_port,
                                   "targetPort": cfg.bridge_wg_port, "nodePort": info["nodePort"]}]}}
    return [("secrets", secret), ("deployments", deploy), ("services", service)]


def sync_bridges(kube, cfg, desired, cache, now):
    """Server-side apply every wanted bridge object (skipped while unchanged and recently applied) and delete the managed
    objects nobody wants any more. `desired`: {agent: [(kind, body)]}; `cache`: {(kind, name): (hash, time)}."""
    want = set()
    for res in desired.values():
        for kind, body in res:
            key = (kind, body["metadata"]["name"])
            want.add(key)
            digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            prev = cache.get(key)
            if prev and prev[0] == digest and (now - prev[1]).total_seconds() < 600:
                continue
            kube.apply(cfg.bridge_ns, kind, body)
            cache[key] = (digest, now)
    for kind in ("deployments", "services", "secrets"):
        for n in kube.list_managed(cfg.bridge_ns, kind):
            if (kind, n) not in want:
                kube.delete(cfg.bridge_ns, kind, n)
                cache.pop((kind, n), None)
                log.info("removed bridge %s/%s", kind, n)


def agent_env_bridge(name, data, info, cfg):
    return {"WG_PRIVATE_KEY": data["WG_AGENT"], "WG_PEER_PUBKEY": wg_public(data["WG_BRIDGE"]),
            "WG_ADDRESS": f"{info['agentAddress']}/30", "WG_PEER_IP": info["address"], "WG_BRIDGE_NAME": f"{name}-bridge",
            "WG_MTU": str(cfg.bridge_mtu), "WG_ENDPOINTS": ",".join(f"{h}:{info['nodePort']}" for h in cfg.bridge_endpoint_hosts),
            "WG_TUNNEL_TARGET": f"{info['host']}:{cfg.bridge_wg_port}"}


def agent_env(agent, data, ports, cfg, bridge=None):
    first = pick_gateway(agent, cfg)
    expose = []
    for e in expose_list(agent.get("spec", {})):
        tp = e.get("tailnetPort") or e["port"]
        expose.append(f"{e['name']}=XXX.XXX.XXX.XXX:{e['port']}:{tp}:{ports[e['name']]}")
    out = {
        "TUNNEL_URL": ",".join(gateway_urls(first, cfg)),
        "TUNNEL_VIA_URL": cfg.via_url,
        "TUNNEL_VIA_SECRET": data["VIA"],
        "TUNNEL_SECRET": data["AGENT"],
        "TUNNEL_CANARY": cfg.canary,
        "EXPOSE": ",".join(expose),
    }
    if bridge:
        out.update(agent_env_bridge(agent["metadata"]["name"], data, bridge, cfg))
    return out


def _regex(values):
    return "^(" + "|".join(sorted(values)) + ")$"


def render_restrictions(entries, cfg):
    """The wstunnel --restrict-config file. `entries`: [(name, data, ports{expose: port})] for active agents.
    No entries renders `restrictions: []`, which wstunnel treats as deny everything."""
    if not entries:
        return "restrictions: []\n"
    out = ["restrictions:"]
    for name, data, ports, *rest in sorted(entries, key=lambda e: e[0]):
        bhost = rest[0] if rest else None  # the agent's bridge Service name, when it has one
        plist = ", ".join(str(p) for p in sorted(ports.values())) or "1"
        out += [
            f"  - name: {name}-via",
            f"    description: HTTPS to Tailscale control and DERP hosts only" + (", and UDP to this agent's own lab bridge." if bhost else "."),
            "    match:",
            f'      - !PathPrefix "{_regex(valid_secrets(data, "VIA"))}"',
            "    allow:",
            "      - !Tunnel",
            "        protocol: [Tcp]",
            "        port: [443]",
            "        host: '^([a-z0-9-]+\\.)*tailscale\\.(com|io)$'",
            '        cidr: [XXX.XXX.XXX.XXX/0, "::/0"]',
            *([ "      - !Tunnel", "        protocol: [Udp]", f"        port: [{cfg.bridge_wg_port}]",
                f"        host: '^{bhost.replace('.', chr(92) + '.')}$'", f"        cidr: [{', '.join(cfg.cidrs)}]"] if bhost else []),
            f"  - name: {name}",
            "    description: Outbound to the homelab; inbound only this agent's reverse ports (the gateway pod's loopback).",
            "    match:",
            f'      - !PathPrefix "{_regex(valid_secrets(data, "AGENT"))}"',
            "    allow:",
            "      - !Tunnel",
            "        protocol: [Tcp]",
            f"        cidr: [{', '.join(cfg.cidrs)}]",
            "      - !ReverseTunnel",
            "        protocol: [Tcp]",
            f"        port: [{plist}]",
            f"  - name: {name}-client",
            "    description: A client forwarding to this agent's reverse ports on the pod's own loopback, nothing else.",
            "    match:",
            f'      - !PathPrefix "{_regex(valid_secrets(data, "CLIENT"))}"',
            "    allow:",
            "      - !Tunnel",
            "        protocol: [Tcp]",
            f"        port: [{plist}]",
            "        host: '^(localhost|127\\.0\\.0\\.1)$'",
            "        cidr: [XXX.XXX.XXX.XXX/8]",
        ]
    return "\n".join(out) + "\n"


def env_file(values):
    return "".join(f"{k}={v}\n" for k, v in values.items())


def conditions(status, reason, message, generation, previous=None, now=None):
    """The Ready condition. lastTransitionTime only moves when status or reason change, so a steady state writes nothing."""
    when = iso(now or datetime.now(timezone.utc))
    for c in previous or []:
        if c.get("type") == "Ready" and c.get("status") == status and c.get("reason") == reason:
            when = c.get("lastTransitionTime", when)
    return [{"type": "Ready", "status": status, "reason": reason, "message": message,
             "observedGeneration": generation, "lastTransitionTime": when}]


# ---------------------------------------------------------------- connection activity

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
ACCEPT_RE = re.compile(r"Tunnel accepted due to matched restriction: (\S+)")


def parse_kube_ts(text):
    """A kubelet log timestamp (RFC3339, nanoseconds) as an aware datetime, or None."""
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?Z", text or "")
    if not m:
        return None
    micro = int((m.group(2) or "0")[:6].ljust(6, "0"))
    return datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(microsecond=micro, tzinfo=timezone.utc)


def restriction_kind(restriction, names):
    """('agent name', 'via' | 'agent') for a restriction wstunnel matched, or None for a client (a person's ssh) or an unknown name.
    Agent names cannot end in -via/-client (validate), so the three restriction names of one agent are unambiguous."""
    if restriction.endswith("-via") and restriction[:-4] in names:
        return restriction[:-4], "via"
    if restriction in names:
        return restriction, "agent"
    return None


def scan_log(text, names, since=None):
    """Newest accepted tunnel per agent in a gateway log: ({agent: (time, kind)}, newest line time).
    Lines at or before `since` were seen on an earlier poll."""
    seen, newest = {}, since
    for line in text.splitlines():
        stamp, _, rest = line.partition(" ")
        when = parse_kube_ts(stamp)
        if when is None or (since and when <= since):
            continue
        newest = when if newest is None or when > newest else newest
        m = ACCEPT_RE.search(ANSI_RE.sub("", rest))
        k = restriction_kind(m.group(1), names) if m else None
        if k and (k[0] not in seen or when >= seen[k[0]][0]):
            seen[k[0]] = (when, k[1])
    return seen, newest


class Activity:
    """Reads each gateway pod's wstunnel log (only what is new since the last poll) and reports the latest connection per agent."""

    def __init__(self):
        self.cursor = {}

    def poll(self, kube, ns, cfg, names):
        out = {}
        for i in range(cfg.gateways):
            pod = f"{cfg.pod_prefix}-{i}"
            try:
                text = kube.pod_log(ns, pod, self.cursor.get(pod))
            except Exception as e:  # noqa: BLE001 - presence is a nicety; never stop credential reconciliation for it
                log.warning("cannot read %s's log: %s", pod, e)
                continue
            seen, newest = scan_log(text, names, self.cursor.get(pod))
            if newest:
                self.cursor[pod] = newest
            for n, v in seen.items():
                if n not in out or v[0] > out[n][0]:
                    out[n] = v
        return out


def seen_status(previous, observed, resolution):
    """lastSeen / connectionType for the status. A new observation only replaces the stored one when the type changed or
    the time moved by at least `resolution` seconds, so a steady state writes nothing."""
    prev = previous or {}
    last, kind = prev.get("lastSeen"), prev.get("connectionType")
    if observed:
        when, k = observed
        old = parse_iso(last)
        if k != kind or old is None or (when - old).total_seconds() >= resolution:
            last, kind = iso(when), k
    out = {}
    if last:
        out["lastSeen"] = last
    if kind:
        out["connectionType"] = kind
    return out


# ---------------------------------------------------------------- Kubernetes API

class Kube:
    def __init__(self):
        self.base = f"https://{os.environ['KUBERNETES_SERVICE_HOST']}:{os.environ.get('KUBERNETES_SERVICE_PORT', '443')}"
        self.ctx = ssl.create_default_context(cafile=f"{SA_DIR}/ca.crt")

    def _token(self):
        with open(f"{SA_DIR}/token") as f:  # re-read: projected tokens rotate
            return f.read().strip()

    def request(self, method, path, body=None, content_type="application/json"):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token()}", "Accept": "application/json", "Content-Type": content_type})
        with urllib.request.urlopen(req, timeout=30, context=self.ctx) as resp:
            return json.loads(resp.read() or b"{}")

    def list_agents(self, ns):
        return self.request("GET", f"/apis/{GROUP}/{VERSION}/namespaces/{ns}/{PLURAL}").get("items", [])

    def pod_log(self, ns, pod, since=None):
        """The wstunnel container's log with kubelet timestamps; everything on the first call, then only what is newer."""
        q = "container=wstunnel&timestamps=true" + (f"&sinceTime={since.strftime('%Y-%m-%dT%H:%M:%S.%fZ')}" if since else "")
        req = urllib.request.Request(f"{self.base}/api/v1/namespaces/{ns}/pods/{pod}/log?{q}",
                                     headers={"Authorization": f"Bearer {self._token()}"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=self.ctx) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):  # pod not there or container not started yet
                return ""
            raise

    def patch_status(self, ns, name, status):
        self.request("PATCH", f"/apis/{GROUP}/{VERSION}/namespaces/{ns}/{PLURAL}/{name}/status",
                     {"status": status}, "application/merge-patch+json")

    BRIDGE_API = {"secrets": "/api/v1", "services": "/api/v1", "deployments": "/apis/apps/v1"}

    def apply(self, ns, kind, body):
        """Server-side apply (create or update, field-owned by this controller; a Service keeps its clusterIP)."""
        name = body["metadata"]["name"]
        self.request("PATCH", f"{self.BRIDGE_API[kind]}/namespaces/{ns}/{kind}/{name}?fieldManager=tunnel-controller&force=true",
                     body, "application/apply-patch+yaml")

    def list_managed(self, ns, kind):
        sel = "app.kubernetes.io%2Fmanaged-by%3Dtunnel-controller"
        items = self.request("GET", f"{self.BRIDGE_API[kind]}/namespaces/{ns}/{kind}?labelSelector={sel}").get("items", [])
        return [i["metadata"]["name"] for i in items]

    def delete(self, ns, kind, name):
        try:
            self.request("DELETE", f"{self.BRIDGE_API[kind]}/namespaces/{ns}/{kind}/{name}")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

    def get_secret(self, ns, name):
        try:
            return self.request("GET", f"/api/v1/namespaces/{ns}/secrets/{name}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    def put_secret(self, ns, body, exists):
        name = body["metadata"]["name"]
        if exists:
            self.request("PUT", f"/api/v1/namespaces/{ns}/secrets/{name}", body)
        else:
            self.request("POST", f"/api/v1/namespaces/{ns}/secrets", body)


def decode_secret(sec):
    if sec is None:
        return None
    data = {k: base64.b64decode(v).decode() for k, v in (sec.get("data") or {}).items()}
    return {"data": {k[len("ID_"):]: v for k, v in data.items() if k.startswith("ID_")},
            "annotations": (sec.get("metadata") or {}).get("annotations") or {}, "resourceVersion":
            (sec.get("metadata") or {}).get("resourceVersion")}


def secret_body(ns, name, data, annotations, resource_version=None, owner=None, labels=None, extra=None):
    """Credentials are stored under ID_* (what the controller reads back); the same values are also exposed under the
    names an agent uses, plus agent.env, so `kubectl get secret -o jsonpath` gives something directly usable."""
    out = {f"ID_{k}": v for k, v in data.items()}
    out.update(extra or {})
    meta = {"name": name, "namespace": ns, "annotations": annotations, "labels": labels or {}}
    if resource_version:
        meta["resourceVersion"] = resource_version
    if owner:
        meta["ownerReferences"] = [owner]
    return {"apiVersion": "v1", "kind": "Secret", "metadata": meta, "type": "Opaque",
            "stringData": out}


# ---------------------------------------------------------------- reconcile

_BRIDGE_CACHE = {}   # (kind, name) -> (hash, applied at): unchanged bridge objects are not re-applied every poll
_BRIDGES_SEEN = [False]  # a bridge existed on the last pass, so one more pass has to prune what was removed


def reconcile_once(kube, ns, cfg, now=None, activity=None, bridge_cache=None):
    now = now or datetime.now(timezone.utc)
    agents = kube.list_agents(ns)
    good, bad = [], {}
    for a in agents:
        problem = validate(a, cfg)
        if problem:
            bad[a["metadata"]["name"]] = problem
        else:
            good.append(a)
    ports = assign_ports(good, cfg)
    observed = activity.poll(kube, ns, cfg, {a["metadata"]["name"] for a in good}) if activity else {}
    try:
        slots = assign_bridge_slots(good, cfg)
    except RuntimeError as e:
        log.warning("%s", e)
        slots = {}
    desired, active = {}, []
    for a in good:
        name = a["metadata"]["name"]
        gen = a["metadata"].get("generation")
        sname = f"agent-{name}"
        sec = kube.get_secret(ns, sname)
        existing = decode_secret(sec)
        data, ann, rotated = plan_credentials(a, existing, cfg, now)
        binfo = bridge_info(name, slots[name], cfg) if name in slots else None
        if binfo:
            data = ensure_wg(data, rotated)
            desired[name] = bridge_resources(name, binfo, data, cfg)
        else:
            data = {k: v for k, v in data.items() if k not in ("WG_AGENT", "WG_BRIDGE")}
        env_vals = agent_env(a, data, ports[name], cfg, binfo)
        owner = {"apiVersion": f"{GROUP}/{VERSION}", "kind": "TunnelAgent", "name": name,
                 "uid": a["metadata"]["uid"], "controller": True, "blockOwnerDeletion": True}
        extra = {**env_vals, "CLIENT_SECRET": data["CLIENT"], "agent.env": env_file(env_vals)}
        body = secret_body(ns, sname, data, ann, (existing or {}).get("resourceVersion"), owner, extra=extra,
                           labels={"app.kubernetes.io/name": "tunnel-gateway", "tunnel.vmd1.homelab/agent": name})
        want = {k: str(v) for k, v in body["stringData"].items()}
        have_all = {} if sec is None else {k: base64.b64decode(v).decode() for k, v in (sec.get("data") or {}).items()}
        if sec is None or have_all != want or (existing or {}).get("annotations") != ann:
            kube.put_secret(ns, body, exists=sec is not None)
            log.info("%s: credentials %s", name, "rotated" if rotated else "written")
        suspended = bool(a.get("spec", {}).get("suspended"))
        if not suspended:
            active.append((name, data, ports[name], binfo["host"] if binfo else None))
        gw = pick_gateway(a, cfg)
        status = {
            "observedGeneration": gen, "gateway": cfg.gateway_hosts[0].format(i=gw),
            "gateways": [u[len("wss://"):] for u in gateway_urls(gw, cfg)], "ports": ports[name],
            "secretName": sname, "rotatedAt": ann.get(ANN + "rotated-at"),
            **seen_status(a.get("status"), observed.get(name), cfg.seen_resolution),
            **({"bridge": {k: binfo[k] for k in ("slot", "address", "agentAddress", "nodePort")}} if binfo
               else ({"bridge": None} if (a.get("status") or {}).get("bridge") else {})),
            "previousValidUntil": ann.get(ANN + "previous-until"),
            "conditions": conditions("False" if suspended else "True", "Suspended" if suspended else "Active",
                                     "credentials are revoked: not in the gateway's restrictions" if suspended
                                     else "credentials issued and allowed by the gateway", gen,
                                     (a.get("status") or {}).get("conditions"), now)}
        if status != (a.get("status") or {}):
            kube.patch_status(ns, name, status)
    for a in agents:
        n = a["metadata"]["name"]
        if n in bad:
            log.warning("%s: invalid: %s", n, bad[n])
            gen = a["metadata"].get("generation")
            st = {"observedGeneration": gen, "conditions": conditions(
                "False", "Invalid", bad[n], gen, (a.get("status") or {}).get("conditions"), now)}
            if any(st.get(k) != (a.get("status") or {}).get(k) for k in st):
                kube.patch_status(ns, n, st)
    sync_restrictions(kube, ns, cfg, render_restrictions(active, cfg))
    if desired or _BRIDGES_SEEN[0]:
        try:
            sync_bridges(kube, cfg, desired, _BRIDGE_CACHE if bridge_cache is None else bridge_cache, now)
            _BRIDGES_SEEN[0] = bool(desired)
        except Exception as e:  # noqa: BLE001 - a broken bridge namespace must not stop credentials or restrictions
            log.warning("bridge sync failed: %s", e)


def sync_restrictions(kube, ns, cfg, text):
    sec = kube.get_secret(ns, cfg.restrictions_secret)
    cur = None
    if sec is not None:
        cur = base64.b64decode((sec.get("data") or {}).get("restrictions.yaml", "")).decode()
    if cur == text:
        return
    body = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
            "metadata": {"name": cfg.restrictions_secret, "namespace": ns,
                         "labels": {"app.kubernetes.io/name": "tunnel-gateway"},
                         **({"resourceVersion": sec["metadata"]["resourceVersion"]} if sec else {})},
            "stringData": {"restrictions.yaml": text}}
    kube.put_secret(ns, body, exists=sec is not None)
    log.info("restrictions updated (%d agents)", text.count("-client\n"))


# ---------------------------------------------------------------- enrollment

ENROLL_PREFIX = "enroll-"
DENIED = (403, "denied\n")


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def token_name(token):
    """Tokens made by make-provision.sh are <agent-name>.<random>, so a setup URL needs nothing but the key."""
    name, dot, rest = token.rpartition(".")
    return name if dot and rest else None


def _validate(kube, ns, name, token, now):
    """The enrollment record if `token` is good for `name` right now: (secret, fields, uses) or a (status, body) refusal."""
    if not isinstance(name, str) or not isinstance(token, str) or not NAME_RE.match(name) or not (16 <= len(token) <= 200):
        return 400, "bad request\n"
    sec = kube.get_secret(ns, ENROLL_PREFIX + name)
    if sec is None:
        log.warning("enroll %s: no token issued", name)
        return DENIED
    d = {k: base64.b64decode(v).decode() for k, v in (sec.get("data") or {}).items()}
    try:
        uses, expires = int(d.get("uses", "0")), parse_iso(d["expires"])
    except (KeyError, ValueError):
        expires = None
    if expires is None:
        log.warning("enroll %s: malformed token record", name)
        return DENIED
    if not hmac.compare_digest(token_hash(token).encode(), d.get("hash", "").encode()):
        log.warning("enroll %s: wrong token", name)
        return DENIED
    if uses <= 0 or now >= expires:
        log.warning("enroll %s: token %s", name, "used up" if uses <= 0 else "expired")
        return DENIED
    agent = next((a for a in kube.list_agents(ns) if a["metadata"]["name"] == name), None)
    if agent is None or (agent.get("spec") or {}).get("suspended"):
        log.warning("enroll %s: agent %s", name, "missing" if agent is None else "suspended")
        return DENIED
    return sec, d, uses


def _common(kube, ns, cfg):
    sec = kube.get_secret(ns, cfg.enroll_common)
    if sec is None:
        return None
    try:
        return {k: base64.b64decode(v).decode().strip() for k, v in (sec.get("data") or {}).items()}
    except ValueError:
        return None


def enroll(kube, ns, cfg, name, token, now=None):
    """Trade an enrollment token for the agent's environment: (http status, body). Every token works `uses` times, then never
    again, and expires; only a hash is stored. All failures look the same from outside (the reason is only logged)."""
    now = now or datetime.now(timezone.utc)
    for _ in range(5):  # another request may take the same token's last use first: re-read and retry
        v = _validate(kube, ns, name, token, now)
        if len(v) == 2:
            return v
        sec, d, uses = v
        asec, cdata = kube.get_secret(ns, f"agent-{name}"), _common(kube, ns, cfg)
        if asec is None or cdata is None:
            log.warning("enroll %s: credentials are not ready yet", name)
            return 503, "not ready\n"
        try:
            agent_env_text = base64.b64decode(asec["data"]["agent.env"]).decode()
        except (KeyError, ValueError):
            return 503, "not ready\n"
        body = {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                "metadata": {"name": ENROLL_PREFIX + name, "namespace": ns, "resourceVersion": sec["metadata"]["resourceVersion"],
                             "labels": {"app.kubernetes.io/name": "tunnel-gateway", "tunnel.vmd1.homelab/agent": name}},
                "stringData": {**d, "uses": str(uses - 1), "last-used": iso(now)}}
        try:
            kube.put_secret(ns, body, exists=True)  # consumed BEFORE the answer leaves, so a crash cannot hand out a free use
        except urllib.error.HTTPError as e:
            if e.code == 409:
                continue
            raise
        common_env = "".join(f"{k}={cdata[k]}\n" for k in ("CANARY", "TS_AUTHKEY") if cdata.get(k))
        log.info("enroll %s: credentials issued, %d use(s) left", name, uses - 1)
        return 200, common_env + agent_env_text
    return 503, "busy\n"


HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,60}[A-Za-z0-9])?$")
SETUP_STUB = """#!/bin/sh
# vmd1 server setup for %(name)s. Run as root:  curl -fsSL <this url> | sudo sh
set -e
f=$(mktemp /tmp/vmd1-setup.XXXXXX) || exit 1
cat > "$f" <<'__VMD1_SETUP__'
%(script)s
__VMD1_SETUP__
chmod 700 "$f"
exec bash "$f" "$@"
"""


def render_setup(kube, ns, cfg, token, host=None, now=None):
    """The provisioning script for the agent that `token` belongs to: (http status, body). Serving it does not use up a use (the
    enrollment does); it is only ever shown to a holder of a currently valid token. It is a POSIX stub that unpacks the real bash
    script, so `| sh` works on dash systems."""
    now = now or datetime.now(timezone.utc)
    name = token_name(token) if isinstance(token, str) else None
    if name is None or (host is not None and not HOST_RE.match(host)):
        return 400, "bad request\n"
    v = _validate(kube, ns, name, token, now)
    if len(v) == 2:
        return v
    cdata = _common(kube, ns, cfg)
    try:
        with open(cfg.setup_template) as f:
            tpl = f.read()
    except OSError:
        cdata = None
    if not cdata or not cdata.get("SSH_PUBKEY"):
        log.warning("setup %s: the common secret has no SSH_PUBKEY (or the template is missing)", name)
        return 503, "not ready\n"
    urls = " ".join("https://" + urllib.parse.urlparse(u).hostname for u in cfg.via_url.split(",") if u.strip())
    vals = {"TS_HOSTNAME": host or name, "ADMIN_USER": cdata.get("ADMIN_USER", "admin"), "SSH_PUBKEY": cdata["SSH_PUBKEY"],
            "ENROLL_NAME": name, "ENROLL_TOKEN": token, "ENROLL_URLS": urls,
            "AGENT_IMAGE": cdata.get("AGENT_IMAGE", "ghcr.io/vmd1/tunnel-agent:latest"),
            "REGISTRY_HOST": cdata.get("REGISTRY_HOST", "registry.vmd1.homelab"),
            "REGISTRY_IMAGE": cdata.get("REGISTRY_IMAGE", "registry.vmd1.homelab/tunnel-agent:latest"),
            "REGISTRY_USER": cdata.get("REGISTRY_USER", ""), "REGISTRY_PASSWORD": cdata.get("REGISTRY_PASSWORD", "")}
    for k, val in vals.items():
        if "'" in val or "\n" in val:  # values land inside single quotes in the script
            log.warning("setup %s: %s contains a quote or newline", name, k)
            return 503, "not ready\n"
        tpl = tpl.replace(f"@@{k}@@", val)
    if "@@" in tpl or "__VMD1_SETUP__" in tpl:
        return 503, "not ready\n"
    log.info("setup %s: script served", name)
    return 200, SETUP_STUB % {"name": name, "script": tpl.rstrip("\n")}


def enroll_handler(kube, ns, cfg):
    class H(BaseHTTPRequestHandler):
        server_version = "enroll"
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # never log request lines
            pass

        def _send(self, code, text, ctype="text/plain; charset=utf-8"):
            data = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if self.path.rstrip("/") != "/enroll" or not 0 < n <= 1024:
                    return self._send(404 if self.path.rstrip("/") != "/enroll" else 400, "no\n")
                req = json.loads(self.rfile.read(n))
                code, text = enroll(kube, ns, cfg, req.get("name"), req.get("token"))
            except (ValueError, AttributeError):
                code, text = 400, "bad request\n"
            except Exception:  # noqa: BLE001 - never leak details to a client
                log.exception("enroll failed")
                code, text = 500, "error\n"
            if code != 200:
                time.sleep(0.5)  # slows guessing; the tokens are 128-bit anyway
            self._send(code, text)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if not u.path.startswith("/setup/"):
                return self._send(404, "no\n")
            try:
                host = (urllib.parse.parse_qs(u.query).get("host") or [None])[0]
                code, text = render_setup(kube, ns, cfg, urllib.parse.unquote(u.path[len("/setup/"):]), host)
            except Exception:  # noqa: BLE001 - never leak details to a client
                log.exception("setup failed")
                code, text = 500, "error\n"
            if code != 200:
                time.sleep(0.5)
            self._send(code, text, "text/x-shellscript; charset=utf-8" if code == 200 else "text/plain; charset=utf-8")
    return H


def serve_enroll(kube, ns, cfg):
    srv = ThreadingHTTPServer(("XXX.XXX.XXX.XXX", cfg.enroll_port), enroll_handler(kube, ns, cfg))
    threading.Thread(target=srv.serve_forever, name="enroll", daemon=True).start()
    log.info("enrollment endpoint on :%d", cfg.enroll_port)
    return srv



def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    ns = os.environ.get("NAMESPACE")
    if not ns:
        with open(f"{SA_DIR}/namespace") as f:
            ns = f.read().strip()
    cfg, kube, activity = Config(), Kube(), Activity()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    serve_enroll(kube, ns, cfg)
    log.info("watching %s/%s in %s every %ds (%d gateways)", PLURAL, VERSION, ns, cfg.poll, cfg.gateways)
    while not stop.is_set():
        try:
            reconcile_once(kube, ns, cfg, activity=activity)
            open("/tmp/heartbeat", "w").close()
        except Exception:
            log.exception("reconcile failed")
        stop.wait(cfg.poll)


if __name__ == "__main__":
    main()
