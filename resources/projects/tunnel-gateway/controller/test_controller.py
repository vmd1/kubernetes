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
