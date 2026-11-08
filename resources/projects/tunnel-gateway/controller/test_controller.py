import base64
import copy
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import controller as c  # noqa: E402

NOW = datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)
CFG = c.Config({})


class FakeKube:
    """In-memory stand-in for the API: TunnelAgents, Secrets, and a log of writes."""

    def __init__(self, agents):
        self.agents = {a["metadata"]["name"]: a for a in agents}
        self.secrets, self.writes, self.status_patches = {}, [], 0

    def list_agents(self, ns):
        return copy.deepcopy(list(self.agents.values()))

    def patch_status(self, ns, name, status):
        self.status_patches += 1
        self.agents[name]["status"] = status  # merge-patch of a whole status

    def get_secret(self, ns, name):
        s = self.secrets.get(name)
        return copy.deepcopy(s) if s else None

    # lab bridges: objects in the bridge namespace, {(kind, name): body}
    def apply(self, ns, kind, body):
        if not hasattr(self, "bridge_objs"):
            self.bridge_objs, self.applies = {}, []
        self.bridge_objs[(kind, body["metadata"]["name"])] = copy.deepcopy(body)
        self.applies.append((kind, body["metadata"]["name"]))

    def list_managed(self, ns, kind):
        return [n for (k, n) in getattr(self, "bridge_objs", {}) if k == kind]

    def delete(self, ns, kind, name):
        self.bridge_objs.pop((kind, name), None)

    def put_secret(self, ns, body, exists):
        name = body["metadata"]["name"]
        self.writes.append(name)
        stored = copy.deepcopy(body)
        stored["data"] = {k: base64.b64encode(str(v).encode()).decode() for k, v in body["stringData"].items()}
        stored["metadata"]["resourceVersion"] = str(len(self.writes))
        self.secrets[name] = stored


def agent(name, spec=None, created="2026-11-01T00:00:00Z", status=None):
    return {"metadata": {"name": name, "uid": "u-" + name, "generation": 1, "creationTimestamp": created},
            "spec": spec or {}, "status": status or {}}


def restrictions(kube):
    return base64.b64decode(kube.secrets["tunnel-gateway-restrictions"]["data"]["restrictions.yaml"]).decode()


def creds(kube, name):
    sec = kube.secrets[f"agent-{name}"]
    return {k: base64.b64decode(v).decode() for k, v in sec["data"].items()}


def test_new_agent_gets_credentials_env_port_gateway_and_restrictions():
    k = FakeKube([agent("srv1")])
    c.reconcile_once(k, "ns", CFG, NOW)
    d = creds(k, "srv1")
    assert len({d["ID_VIA"], d["ID_AGENT"], d["ID_CLIENT"]}) == 3 and len(d["ID_AGENT"]) == 48
    assert d["TUNNEL_SECRET"] == d["ID_AGENT"] and d["CLIENT_SECRET"] == d["ID_CLIENT"]
    port = k.agents["srv1"]["status"]["ports"]["ssh"]
    assert 20000 <= port <= 20999 and d["EXPOSE"] == f"ssh=XXX.XXX.XXX.XXX:22:22:{port}"
    urls = d["TUNNEL_URL"].split(",")
    assert sorted(urls) == sorted(f"wss://coordination-{i}.{d}" for i in (0, 1) for d in ("vmd1.homelab", "vmd1.homelab", "vmd1.homelab"))
    assert k.agents["srv1"]["status"]["gateway"] == urls[0][len("wss://"):]
    assert "TUNNEL_SECRET=" + d["ID_AGENT"] in d["agent.env"] and "TUNNEL_VIA_URL=wss://coordination.vmd1.homelab,wss://coordination.vmd1.homelab,wss://coordination.vmd1.homelab,wss://cf-coordination.vmd1.homelab" in d["agent.env"]
    r = restrictions(k)
    assert d["ID_AGENT"] in r and d["ID_CLIENT"] in r and d["ID_VIA"] in r and f"port: [{port}]" in r
    assert k.agents["srv1"]["status"]["conditions"][0]["status"] == "True"


def test_a_second_pass_changes_nothing():
    k = FakeKube([agent("a"), agent("b")])
    c.reconcile_once(k, "ns", CFG, NOW)
    # the API would hand back the status we patched; the fake keeps it on the object
    writes, patches = len(k.writes), k.status_patches
    c.reconcile_once(k, "ns", CFG, NOW + timedelta(seconds=15))
    assert (len(k.writes), k.status_patches) == (writes, patches)


def test_ports_are_unique_stable_and_survive_other_agents_coming_and_going():
    k = FakeKube([agent(f"s{i}", created=f"2026-11-0{i + 1}T00:00:00Z") for i in range(4)])
    c.reconcile_once(k, "ns", CFG, NOW)
    first = {n: a["status"]["ports"]["ssh"] for n, a in k.agents.items()}
    assert len(set(first.values())) == 4
    del k.agents["s1"]
    k.agents["new"] = agent("new", created="2026-11-09T00:00:00Z")
    c.reconcile_once(k, "ns", CFG, NOW)
    assert all(k.agents[n]["status"]["ports"]["ssh"] == first[n] for n in ("s0", "s2", "s3"))
    assert k.agents["new"]["status"]["ports"]["ssh"] not in first.values() or k.agents["new"]["status"]["ports"]["ssh"] == first["s1"]


def test_port_conflict_goes_to_the_newer_agent():
    old = agent("old", created="2026-01-01T00:00:00Z", status={"ports": {"ssh": 20005}})
    new = agent("new", created="2026-02-01T00:00:00Z", status={"ports": {"ssh": 20005}})
    ports = c.assign_ports([new, old], CFG)
    assert ports["old"]["ssh"] == 20005 and ports["new"]["ssh"] != 20005


def test_suspended_agent_keeps_its_secret_but_leaves_the_restrictions():
    k = FakeKube([agent("keep"), agent("gone", {"suspended": True})])
    c.reconcile_once(k, "ns", CFG, NOW)
    r = restrictions(k)
    assert creds(k, "keep")["ID_AGENT"] in r
    assert creds(k, "gone")["ID_AGENT"] not in r and "name: gone" not in r
    assert k.agents["gone"]["status"]["conditions"][0]["reason"] == "Suspended"
    k.agents["gone"]["spec"]["suspended"] = False
    c.reconcile_once(k, "ns", CFG, NOW)
    assert creds(k, "gone")["ID_AGENT"] in restrictions(k)


def test_deleting_an_agent_revokes_it():
    k = FakeKube([agent("a"), agent("b")])
    c.reconcile_once(k, "ns", CFG, NOW)
    secret_b = creds(k, "b")["ID_AGENT"]
    del k.agents["b"]
    c.reconcile_once(k, "ns", CFG, NOW)
    assert secret_b not in restrictions(k)


def test_no_agents_renders_deny_all():
    k = FakeKube([])
    c.reconcile_once(k, "ns", CFG, NOW)
    assert restrictions(k) == "restrictions: []\n"


def test_rotation_on_token_change_keeps_the_old_credentials_for_the_grace_period_only():
    k = FakeKube([agent("a", {"rotationToken": "1"})])
    c.reconcile_once(k, "ns", CFG, NOW)
    old = creds(k, "a")["ID_AGENT"]
    c.reconcile_once(k, "ns", CFG, NOW + timedelta(hours=1))
    assert creds(k, "a")["ID_AGENT"] == old  # same token: no rotation
    k.agents["a"]["spec"]["rotationToken"] = "2"
    t = NOW + timedelta(hours=2)
    c.reconcile_once(k, "ns", CFG, t)
    new = creds(k, "a")["ID_AGENT"]
    assert new != old and creds(k, "a")["ID_AGENT_PREVIOUS"] == old
    r = restrictions(k)
    assert old in r and new in r  # both work during the grace
    assert k.agents["a"]["status"]["previousValidUntil"] == c.iso(t + timedelta(hours=24))
    c.reconcile_once(k, "ns", CFG, t + timedelta(hours=25))
    r = restrictions(k)
    assert old not in r and new in r and "ID_AGENT_PREVIOUS" not in creds(k, "a")
    assert k.agents["a"]["status"]["previousValidUntil"] is None


def test_rotation_when_older_than_rotate_after_and_never_disables_it():
    k = FakeKube([agent("a", {"rotateAfter": "1h"}), agent("b", {"rotateAfter": "never"})])
    c.reconcile_once(k, "ns", CFG, NOW)
    a0, b0 = creds(k, "a")["ID_AGENT"], creds(k, "b")["ID_AGENT"]
    c.reconcile_once(k, "ns", CFG, NOW + timedelta(days=400))
    assert creds(k, "a")["ID_AGENT"] != a0 and creds(k, "b")["ID_AGENT"] == b0


def test_no_automatic_rotation_by_default_but_rotateafter_and_the_env_default_still_work():
    k = FakeKube([agent("a"), agent("b", {"rotateAfter": "90d"})])
    c.reconcile_once(k, "ns", CFG, NOW)
    a0, b0 = creds(k, "a")["ID_AGENT"], creds(k, "b")["ID_AGENT"]
    c.reconcile_once(k, "ns", CFG, NOW + timedelta(days=400))
    assert creds(k, "a")["ID_AGENT"] == a0  # nothing set: never rotates
    assert creds(k, "b")["ID_AGENT"] != b0  # asked for 90d: rotates
    opted_in = c.Config({"DEFAULT_ROTATE_AFTER": "30d"})
    k2 = FakeKube([agent("c")])
    c.reconcile_once(k2, "ns", opted_in, NOW)
    c0 = creds(k2, "c")["ID_AGENT"]
    c.reconcile_once(k2, "ns", opted_in, NOW + timedelta(days=31))
    assert creds(k2, "c")["ID_AGENT"] != c0


def test_invalid_agents_are_reported_and_get_no_access():
    bad = [agent("Bad_Name"), agent("dup", {"expose": [{"name": "ssh", "port": 22}, {"name": "ssh", "port": 23}]}),
           agent("range", {"expose": [{"name": "x", "port": 70000}]}), agent("gw", {"gateway": 9})]
    k = FakeKube(bad + [agent("ok")])
    c.reconcile_once(k, "ns", CFG, NOW)
    for a in bad:
        n = a["metadata"]["name"]
        assert k.agents[n]["status"]["conditions"][0]["reason"] == "Invalid"
        assert f"agent-{n}" not in k.secrets
    assert "name: ok" in restrictions(k) and "Bad_Name" not in restrictions(k)


def test_expose_list_ports_and_gateway_pinning():
    spec = {"gateway": 1, "expose": [{"name": "ssh", "port": 22}, {"name": "web", "port": 8080, "tailnetPort": 80}]}
    k = FakeKube([agent("a", spec)])
    c.reconcile_once(k, "ns", CFG, NOW)
    p = k.agents["a"]["status"]["ports"]
    d = creds(k, "a")
    assert d["EXPOSE"] == f"ssh=XXX.XXX.XXX.XXX:22:22:{p['ssh']},web=XXX.XXX.XXX.XXX:8080:80:{p['web']}"
    # its own replica first under every domain, then the other replica
    assert d["TUNNEL_URL"].split(",") == [f"wss://coordination-{i}.{x}" for i in (1, 0) for x in ("vmd1.homelab", "vmd1.homelab", "vmd1.homelab")]
    r = restrictions(k)
    assert f"port: [{min(p.values())}, {max(p.values())}]" in r


def test_gateways_spread_by_name():
    names = [f"srv{i}" for i in range(40)]
    firsts = {c.pick_gateway(agent(n), CFG) for n in names}
    assert firsts == {0, 1}


def test_a_lost_secret_is_reissued_and_the_old_one_stops_working():
    k = FakeKube([agent("a")])
    c.reconcile_once(k, "ns", CFG, NOW)
    old = creds(k, "a")["ID_AGENT"]
    del k.secrets["agent-a"]
    c.reconcile_once(k, "ns", CFG, NOW)
    assert creds(k, "a")["ID_AGENT"] != old and old not in restrictions(k)


def test_parse_duration():
    assert c.parse_duration("90d") == 90 * 86400 and c.parse_duration("12h") == 43200
    assert c.parse_duration("never") is None and c.parse_duration("junk", 5) == 5


# ---------------------------------------------------------------- lastSeen / connectionType

def _line(ts, restriction, esc=False):
    pre = "\x1b[32m INFO\x1b[0m " if esc else " INFO "
    return (f'{ts} 2026-11-06T14:17:29.182284Z{pre}cnx{{peer="XXX.XXX.XXX.XXX:1"}}:tunnel{{forwarded_for="XXX.XXX.XXX.XXX" id="x" '
            f'remote="controlplane.tailscale.com:443"}}: wstunnel::tunnel::server::server: Tunnel accepted due to matched restriction: {restriction}')


class LogKube(FakeKube):
    def __init__(self, agents, logs):
        super().__init__(agents)
        self.logs, self.asked = logs, []

    def pod_log(self, ns, pod, since=None):
        self.asked.append((pod, since))
        v = self.logs.get(pod, "")
        if isinstance(v, Exception):
            raise v
        return v


def test_scan_log_picks_newest_per_agent_and_ignores_clients_and_unknown():
    text = "\n".join([
        _line("2026-11-06T14:00:00.100000000Z", "a-via", esc=True),
        _line("2026-11-06T14:05:00.000000000Z", "a"),
        _line("2026-11-06T14:06:00.000000000Z", "a-client"),
        _line("2026-11-06T14:07:00.000000000Z", "ghost-via"),
        "2026-11-06T14:08:00.000000000Z INFO cnx{}: Accepting connection",
        "garbage",
    ])
    seen, newest = c.scan_log(text, {"a", "b"})
    assert seen == {"a": (datetime(2026, 11, 6, 14, 5, tzinfo=timezone.utc), "agent")}
    assert newest == datetime(2026, 11, 6, 14, 8, tzinfo=timezone.utc)
    seen2, _ = c.scan_log(text, {"a"}, since=datetime(2026, 11, 6, 14, 5, tzinfo=timezone.utc))
    assert seen2 == {}  # nothing newer than the cursor that matters


def test_names_ending_in_via_or_client_are_invalid():
    assert c.validate(agent("x-via"), CFG) and c.validate(agent("x-client"), CFG) and not c.validate(agent("x"), CFG)


def test_status_gets_last_seen_and_type_and_steady_state_writes_nothing():
    k = LogKube([agent("a")], {"tunnel-gateway-0": _line("2026-11-05T11:59:00.000000000Z", "a-via"),
                                "tunnel-gateway-1": _line("2026-11-05T11:58:00.000000000Z", "a")})
    act = c.Activity()
    c.reconcile_once(k, "ns", CFG, NOW, activity=act)
    st = k.agents["a"]["status"]
    assert st["lastSeen"] == "2026-11-05T11:59:00Z" and st["connectionType"] == "via"
    patches = k.status_patches
    c.reconcile_once(k, "ns", CFG, NOW, activity=act)
    assert k.status_patches == patches
    assert k.asked[-2][1] is not None  # second poll only asks for what is newer


def test_last_seen_moves_only_past_the_resolution_or_when_the_type_changes():
    st = {"lastSeen": "2026-11-05T11:00:00Z", "connectionType": "via"}
    t = lambda m: datetime(2026, 11, 5, 11, m, tzinfo=timezone.utc)  # noqa: E731
    assert c.seen_status(st, (t(2), "via"), 300) == st
    assert c.seen_status(st, (t(6), "via"), 300)["lastSeen"] == "2026-11-05T11:06:00Z"
    assert c.seen_status(st, (t(1), "agent"), 300) == {"lastSeen": "2026-11-05T11:01:00Z", "connectionType": "agent"}
    assert c.seen_status(st, None, 300) == st and c.seen_status({}, None, 300) == {}


def test_unreadable_gateway_log_does_not_stop_reconcile_or_wipe_the_last_seen():
    old = {"lastSeen": "2026-11-05T10:00:00Z", "connectionType": "agent"}
    k = LogKube([agent("a", status=old)], {"tunnel-gateway-0": RuntimeError("forbidden")})
    c.reconcile_once(k, "ns", CFG, NOW, activity=c.Activity())
    st = k.agents["a"]["status"]
    assert st["lastSeen"] == old["lastSeen"] and st["connectionType"] == "agent" and "secretName" in st


# ---------------------------------------------------------------- WireGuard lab bridge

def test_x25519_matches_the_rfc7748_vectors_and_wireguard_public_keys():
    k = bytes.fromhex("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4")
    u = bytes.fromhex("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")
    assert c.x25519(k, u).hex() == "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"
    alice = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
    pub = base64.b64decode(c.wg_public(base64.b64encode(alice).decode()))
    assert pub.hex() == "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"
    bob = bytes.fromhex("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
    bob_pub = c.x25519(bob, (9).to_bytes(32, "little"))
    assert c.x25519(alice, bob_pub) == c.x25519(bob, pub)  # Diffie-Hellman agrees both ways


def bridged(name, status=None, spec=None, created="2026-11-01T00:00:00Z"):
    return agent(name, {"bridge": True, **(spec or {})}, created, status)


def reconcile_bridge(k, cache=None):
    c._BRIDGES_SEEN[0] = False
    c.reconcile_once(k, "ns", CFG, NOW, bridge_cache={} if cache is None else cache)


def test_bridge_slots_are_stable_unique_and_skip_suspended_or_unwanted():
    a, b = bridged("a"), bridged("b", status={"bridge": {"slot": 0}})
    assert c.assign_bridge_slots([a, b, agent("plain"), bridged("off", spec={"suspended": True})], CFG) == {"b": 0, "a": 1}
    full = [bridged(f"x{i}") for i in range(CFG.bridge_slots + 1)]
    import pytest
    with pytest.raises(RuntimeError, match="exhausted"):
        c.assign_bridge_slots(full, CFG)
    assert c.validate(agent("z", {"bridge": "yes"}), CFG)


def test_bridge_agent_gets_wireguard_env_status_restriction_and_three_objects():
    k = FakeKube([bridged("srv")])
    reconcile_bridge(k)
    d = creds(k, "srv")
    assert d["WG_ADDRESS"] == "XXX.XXX.XXX.XXX/30" and d["WG_PEER_IP"] == "XXX.XXX.XXX.XXX" and d["WG_BRIDGE_NAME"] == "srv-bridge"
    assert d["WG_ENDPOINTS"] == "coordination.vmd1.homelab:31820,coordination.vmd1.homelab:31820,coordination.vmd1.homelab:31820"  # uk-home first, edge as fallback
    assert d["WG_MTU"] == "1100"
    assert d["WG_TUNNEL_TARGET"] == "bridge-srv.tunnel-bridge.svc.cluster.local:51820"
    assert d["WG_PRIVATE_KEY"] == d["ID_WG_AGENT"] and c.wg_public(d["ID_WG_BRIDGE"]) == d["WG_PEER_PUBKEY"]
    assert "WG_PRIVATE_KEY=" in d["agent.env"]
    st = k.agents["srv"]["status"]["bridge"]
    assert st == {"slot": 0, "address": "XXX.XXX.XXX.XXX", "agentAddress": "XXX.XXX.XXX.XXX", "nodePort": 31820}
    r = restrictions(k)
    assert "protocol: [Udp]" in r and "port: [51820]" in r and "bridge-srv\\.tunnel-bridge\\.svc\\.cluster\\.local" in r
    assert sorted(k.bridge_objs) == [("deployments", "bridge-srv"), ("secrets", "bridge-srv"), ("services", "bridge-srv")]
    sec = k.bridge_objs[("secrets", "bridge-srv")]["stringData"]
    assert sec["WG_PEER_PUBKEY"] == c.wg_public(d["ID_WG_AGENT"]) and sec["WG_PRIVATE_KEY"] == d["ID_WG_BRIDGE"]
    assert sec["WG_ADDRESS"] == "XXX.XXX.XXX.XXX/30" and sec["TS_HOSTNAME"] == "srv-bridge" and sec["WG_MTU"] == "1100"
    dep = k.bridge_objs[("deployments", "bridge-srv")]["spec"]["template"]["spec"]["containers"][0]
    assert dep["securityContext"] == {"privileged": True} and dep["env"][0]["valueFrom"]["secretKeyRef"]["name"] == "bridge-authkey"
    svc = k.bridge_objs[("services", "bridge-srv")]["spec"]
    assert svc["type"] == "NodePort" and svc["ports"][0]["nodePort"] == 31820 and svc["ports"][0]["protocol"] == "UDP"


def test_bridge_is_applied_once_then_pruned_when_removed_and_keys_survive_polls():
    k = FakeKube([bridged("srv")])
    cache = {}
    reconcile_bridge(k, cache)
    n, keys = len(k.applies), creds(k, "srv")["ID_WG_AGENT"]
    c.reconcile_once(k, "ns", CFG, NOW, bridge_cache=cache)
    assert len(k.applies) == n and creds(k, "srv")["ID_WG_AGENT"] == keys  # nothing changed, nothing written
    k.agents["srv"]["spec"].pop("bridge")
    c.reconcile_once(k, "ns", CFG, NOW, bridge_cache=cache)
    assert k.bridge_objs == {} and "ID_WG_AGENT" not in creds(k, "srv") and "WG_ADDRESS" not in creds(k, "srv")
    assert "bridge" not in {x for x in k.agents["srv"]["status"] if k.agents["srv"]["status"][x] is not None}
    assert "protocol: [Udp]" not in restrictions(k)


def test_bridge_keys_rotate_with_the_credentials_and_a_plain_agent_has_no_wireguard():
    k = FakeKube([bridged("srv"), agent("plain")])
    reconcile_bridge(k)
    old = creds(k, "srv")["ID_WG_AGENT"]
    assert "WG_ADDRESS" not in creds(k, "plain")
    k.agents["srv"]["spec"]["rotationToken"] = "now"
    c.reconcile_once(k, "ns", CFG, NOW, bridge_cache={})
    assert creds(k, "srv")["ID_WG_AGENT"] != old


def test_bridge_trouble_never_stops_credentials_or_restrictions():
    class Broken(FakeKube):
        def apply(self, ns, kind, body):
            raise RuntimeError("namespace tunnel-bridge not found")
    k = Broken([bridged("srv")])
    reconcile_bridge(k)
    assert "name: srv" in restrictions(k) and "agent-srv" in k.secrets


def test_bridge_pod_avoids_ingress_and_control_plane_nodes_and_pull_policy_is_optional():
    k = FakeKube([bridged("srv")])
    reconcile_bridge(k)
    spec = k.bridge_objs[("deployments", "bridge-srv")]["spec"]["template"]["spec"]
    exprs = spec["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"][0]["matchExpressions"]
    assert {(e["key"], e["operator"]) for e in exprs} == {("node-role.kubernetes.io/ingress", "DoesNotExist"),
                                                         ("node-role.kubernetes.io/control-plane", "DoesNotExist")}
    assert "imagePullPolicy" not in spec["containers"][0]
    cfg = c.Config({"BRIDGE_PULL_POLICY": "IfNotPresent"})
    body = dict(c.bridge_resources("srv", c.bridge_info("srv", 0, cfg), {"WG_AGENT": c.wg_private(), "WG_BRIDGE": c.wg_private()}, cfg))["deployments"]
    assert body["spec"]["template"]["spec"]["containers"][0]["imagePullPolicy"] == "IfNotPresent"


def test_bridge_pod_rolls_when_its_keys_change_and_not_otherwise():
    k = FakeKube([bridged("srv")])
    reconcile_bridge(k)
    ann = lambda: k.bridge_objs[("deployments", "bridge-srv")]["spec"]["template"]["metadata"]["annotations"]["tunnel.vmd1.homelab/config-hash"]  # noqa: E731
    first = ann()
    c.reconcile_once(k, "ns", CFG, NOW, bridge_cache={})
    assert ann() == first  # same keys, same hash: no rollout
    k.agents["srv"]["spec"]["rotationToken"] = "now"
    c.reconcile_once(k, "ns", CFG, NOW, bridge_cache={})
    assert ann() != first  # rotated keys: the Deployment's pod template changes, so the pod restarts
