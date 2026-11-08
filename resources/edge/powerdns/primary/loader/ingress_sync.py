#!/usr/bin/env python3
"""Writes the ingress.vmd1.homelab zone to the PowerDNS primary from the cluster's node labels.

Same content the old operator (controllers/powerdns-operator) put in geoip-zones.yaml, as LUA records on the primary
instead of a geoip-backend file: one apex rrset (health-checked, closest node, cloud nodes first then the uk-home
backups), one per topology zone, one A per node. Runs in its own Deployment on a stock python image with this file from
a ConfigMap (no image to build); it reads the nodes through the Kubernetes API with its ServiceAccount token.

Writes go through the same API the loader uses; content changes are gated by a hash in zone metadata
X-INGRESS-HASH, so the SOA serial (soa-edit-api) only moves when the node set does.
"""
import json
import os
import ssl
import sys
import time
import urllib.request

import loader  # same directory: API helpers
import zonesync

ZONE = "ingress.vmd1.homelab."
HASH_KIND = "X-INGRESS-HASH"
HEALTH_URL = os.environ.get("HEALTH_URL", "https://vmd1.homelab/health")
NAMESERVERS = [n.strip().rstrip(".") + "." for n in os.environ.get("NAMESERVERS", "ns1.vmd1.homelab,ns2.vmd1.homelab,ns3.vmd1.homelab,ns4.vmd1.homelab").split(",") if n.strip()]
SOA_RNAME = os.environ.get("SOA_RNAME", "admin.vmd1.homelab.")
SOA_TIMERS = os.environ.get("SOA_TIMERS", "30 30 1209600 60")  # keep equal to SOA_TIMERS in dns/shadow/render.js
TTL = 60
INTERVAL = int(os.environ.get("INTERVAL", "15"))
HOME_ZONE = "uk-home"
K8S = "https://kubernetes.default.svc"
SA = "/var/run/secrets/kubernetes.io/serviceaccount"


def list_nodes():
    with open(f"{SA}/token") as f:
        token = f.read().strip()
    ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")
    req = urllib.request.Request(f"{K8S}/api/v1/nodes", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        items = json.load(r)["items"]
    out = []
    for n in items:
        labels = n["metadata"].get("labels", {})
        ip, zone = labels.get("node.vmd1.homelab/public-ip"), labels.get("topology.kubernetes.io/zone")
        if ip and zone:
            out.append({"name": n["metadata"]["name"], "zone": zone, "ip": ip})
    return out


def lua_list(ips):
    return "{" + ", ".join(f"'{ip}'" for ip in ips) + "}"


def ifurlup(groups, nested=False):
    """nested: a list of IP groups (apex: cloud first, backups after); otherwise one flat IP list (a topology zone)."""
    inner = ", ".join(lua_list(g) for g in groups)
    inner = f"{{ {inner} }}" if nested else inner
    return f"A \"ifurlup('{HEALTH_URL}', {inner}, {{timeout=3, selector='pickclosest'}})\""


def build_rrsets(nodes):
    """Pure function: node list -> (rrsets without the SOA, hash). Order of nodes does not matter."""
    nodes = sorted(nodes, key=lambda n: (n["zone"], n["name"]))
    cloud = [n["ip"] for n in nodes if n["zone"] != HOME_ZONE]
    home = [n["ip"] for n in nodes if n["zone"] == HOME_ZONE]
    groups = [g for g in (cloud, home) if g] or [[]]
    rr = []

    def add(name, type_, *contents):
        rr.append({"name": name, "type": type_, "ttl": TTL, "records": [{"content": c, "disabled": False} for c in contents]})

    add(ZONE, "NS", *NAMESERVERS)
    add(ZONE, "LUA", ifurlup(groups, nested=True))
    for zone in sorted({n["zone"] for n in nodes}):
        members = [n for n in nodes if n["zone"] == zone]
        add(f"{zone}.{ZONE}", "LUA", ifurlup([[n["ip"] for n in members]]))
        for n in members:
            add(f"{n['name']}.{zone}.{ZONE}", "A", n["ip"])
    return rr, zonesync.digest(rr)


def sync(nodes):
    rrsets, _ = build_rrsets(nodes)
    return zonesync.put_zone(ZONE, rrsets, HASH_KIND, f"{NAMESERVERS[0]} {SOA_RNAME} 1 {SOA_TIMERS}")


def main():
    if not loader.API_KEY:
        sys.exit("API_KEY is not set")
    last = None
    while True:
        try:
            nodes = list_nodes()
            if not nodes:
                raise RuntimeError("no nodes with node.vmd1.homelab/public-ip and topology.kubernetes.io/zone labels")
            sync(nodes)
            last = None
        except Exception as e:
            if str(e) != last:
                loader.log(f"sync failed: {e}")
            last = str(e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
