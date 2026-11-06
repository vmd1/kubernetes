#!/usr/bin/env python3
"""TunnelAgent controller for the tunnel gateway (standard library only, so it runs on a stock python image).

Watches TunnelAgent objects (tunnel.vmd1.homelab/v1alpha1) in its own namespace and keeps two things true:

  * every agent has a Secret `agent-<name>` holding its credentials and a ready-made `agent.env` (the three secrets,
    its gateway URLs, its reverse ports). Secrets are random per agent, rotated on a schedule or on demand, and the
    previous ones stay valid for a grace period so a running agent is not cut off the moment a rotation happens.
  * the Secret `tunnel-gateway-restrictions` holds the wstunnel `--restrict-config` file rendered from all agents that
    are not suspended. The gateway pods only read it (deny by default: no agents means no access).

Status goes back onto each TunnelAgent (Ready condition, gateway, ports, rotation times).
"""
import base64
import hashlib
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
import urllib.request
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
        self.gateway_host = e.get("GATEWAY_HOST", "tunnel-{i}.vmd1.homelab")  # one per replica (reverse tunnels live there)
        self.via_url = e.get("VIA_URL", "wss://tunnel.vmd1.homelab")  # any replica: the unprivileged pathways are stateless
        lo, _, hi = e.get("PORT_RANGE", "20000-20999").partition("-")
        self.port_lo, self.port_hi = int(lo), int(hi)
        self.cidrs = [c.strip() for c in e.get("AGENT_CIDRS", "XXX.XXX.XXX.XXX/16,XXX.XXX.XXX.XXX/16,XXX.XXX.XXX.XXX/16").split(",") if c.strip()]
        self.canary = e.get("TUNNEL_CANARY", "XXX.XXX.XXX.XXX:53")
        self.restrictions_secret = e.get("RESTRICTIONS_SECRET", "tunnel-gateway-restrictions")
        self.poll = int(e.get("POLL_INTERVAL", "15"))
        self.default_rotate = e.get("DEFAULT_ROTATE_AFTER", "never")
        self.default_grace = e.get("DEFAULT_GRACE", "24h")


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
    """Gateway URLs for an agent, its own replica first, the others as failover."""
    order = [first] + [i for i in range(cfg.gateways) if i != first]
    return ["wss://" + cfg.gateway_host.format(i=i) for i in order]


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


def agent_env(agent, data, ports, cfg):
    first = pick_gateway(agent, cfg)
    expose = []
    for e in expose_list(agent.get("spec", {})):
        tp = e.get("tailnetPort") or e["port"]
        expose.append(f"{e['name']}=XXX.XXX.XXX.XXX:{e['port']}:{tp}:{ports[e['name']]}")
    return {
        "TUNNEL_URL": ",".join(gateway_urls(first, cfg)),
        "TUNNEL_VIA_URL": cfg.via_url,
        "TUNNEL_VIA_SECRET": data["VIA"],
        "TUNNEL_SECRET": data["AGENT"],
        "TUNNEL_CANARY": cfg.canary,
        "EXPOSE": ",".join(expose),
    }


def _regex(values):
    return "^(" + "|".join(sorted(values)) + ")$"


def render_restrictions(entries, cfg):
    """The wstunnel --restrict-config file. `entries`: [(name, data, ports{expose: port})] for active agents.
    No entries renders `restrictions: []`, which wstunnel treats as deny everything."""
    if not entries:
        return "restrictions: []\n"
    out = ["restrictions:"]
    for name, data, ports in sorted(entries, key=lambda e: e[0]):
        plist = ", ".join(str(p) for p in sorted(ports.values())) or "1"
        out += [
            f"  - name: {name}-via",
            f"    description: HTTPS to Tailscale control and DERP hosts only.",
            "    match:",
            f'      - !PathPrefix "{_regex(valid_secrets(data, "VIA"))}"',
            "    allow:",
            "      - !Tunnel",
            "        protocol: [Tcp]",
            "        port: [443]",
            "        host: '^([a-z0-9-]+\\.)*tailscale\\.(com|io)$'",
            '        cidr: [XXX.XXX.XXX.XXX/0, "::/0"]',
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

    def patch_status(self, ns, name, status):
        self.request("PATCH", f"/apis/{GROUP}/{VERSION}/namespaces/{ns}/{PLURAL}/{name}/status",
                     {"status": status}, "application/merge-patch+json")

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

def reconcile_once(kube, ns, cfg, now=None):
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
    active = []
    for a in good:
        name = a["metadata"]["name"]
        gen = a["metadata"].get("generation")
        sname = f"agent-{name}"
        sec = kube.get_secret(ns, sname)
        existing = decode_secret(sec)
        data, ann, rotated = plan_credentials(a, existing, cfg, now)
        env_vals = agent_env(a, data, ports[name], cfg)
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
            active.append((name, data, ports[name]))
        gw = pick_gateway(a, cfg)
        status = {
            "observedGeneration": gen, "gateway": cfg.gateway_host.format(i=gw),
            "gateways": [u[len("wss://"):] for u in gateway_urls(gw, cfg)], "ports": ports[name],
            "secretName": sname, "rotatedAt": ann.get(ANN + "rotated-at"),
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


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    ns = os.environ.get("NAMESPACE")
    if not ns:
        with open(f"{SA_DIR}/namespace") as f:
            ns = f.read().strip()
    cfg, kube = Config(), Kube()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    log.info("watching %s/%s in %s every %ds (%d gateways)", PLURAL, VERSION, ns, cfg.poll, cfg.gateways)
    while not stop.is_set():
        try:
            reconcile_once(kube, ns, cfg)
            open("/tmp/heartbeat", "w").close()
        except Exception:
            log.exception("reconcile failed")
        stop.wait(cfg.poll)


if __name__ == "__main__":
    main()
