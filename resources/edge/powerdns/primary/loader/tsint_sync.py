#!/usr/bin/env python3
"""Keeps ts.int.vmd1.homelab equal to what the cluster knows about the tailnet (no Tailscale API key involved):

  <node>.dev.ts.int.vmd1.homelab     every Kubernetes node: its InternalIP is the node's tailnet address (XXX.XXX.XXX.XXX/10)
  <name>.srv.ts.int.vmd1.homelab     every Service of loadBalancerClass tailscale: its published tailnet address; <name> is
                                 the Service's tailscale.com/hostname annotation, else its name
  tailnet inventory              /inventory/inventory.json (ConfigMap powerdns/tailnet-inventory, published by the
                                 tailnet-inventory controller in the tailscale namespace from the Tailscale API): every
                                 device as <name>.dev (laptops, phones, TVs, servers) and every Tailscale Service as
                                 <name>.srv (k8s-api)
  static extras                  /static/ts.int.vmd1.homelab.static.json (rendered from dns/shadow/config.json tsInt) for what
                                 neither knows (the subnet router: the operator's proxies are not listed as devices)

Precedence for one name: the cluster, then the inventory, then the static file. Reads the Kubernetes API with its
ServiceAccount token (no Tailscale credential here), writes the primary's API like the other zone owners.
"""
import ipaddress
import json
import os
import ssl
import sys
import time
import urllib.request

import loader
import zonesync

ZONE = "ts.int.vmd1.homelab."
HASH_KIND = "X-TSINT-HASH"
NAMESERVERS = [n.strip().rstrip(".") + "." for n in os.environ.get("NAMESERVERS", "ns1.vmd1.homelab,ns2.vmd1.homelab,ns3.vmd1.homelab,ns4.vmd1.homelab").split(",") if n.strip()]
SOA_RNAME = os.environ.get("SOA_RNAME", "admin.vmd1.homelab.")
SOA_TIMERS = os.environ.get("SOA_TIMERS", "30 30 1209600 60")  # keep equal to SOA_TIMERS in dns/shadow/render.js
STATIC = os.environ.get("STATIC_FILE", "/static/ts.int.vmd1.homelab.static.json")
INVENTORY = os.environ.get("INVENTORY_FILE", "/inventory/inventory.json")
TTL = 300
INTERVAL = int(os.environ.get("INTERVAL", "30"))
K8S = "https://kubernetes.default.svc"
SA = "/var/run/secrets/kubernetes.io/serviceaccount"
TAILNET = ipaddress.ip_network("XXX.XXX.XXX.XXX/10")


def k8s_get(path):
    with open(f"{SA}/token") as f:
        token = f.read().strip()
    ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")
    req = urllib.request.Request(K8S + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        return json.load(r)["items"]


def in_tailnet(ip):
    try:
        return ipaddress.ip_address(ip) in TAILNET
    except ValueError:
        return False


def label(s):
    return s.strip().lower()


def from_nodes(nodes):
    out = {}
    for n in nodes:
        ips = [a["address"] for a in n.get("status", {}).get("addresses", []) if a["type"] == "InternalIP" and in_tailnet(a["address"])]
        if ips:
            out[label(n["metadata"]["name"])] = ips[0]
    return out


def from_services(services):
    out = {}
    for s in services:
        if s.get("spec", {}).get("loadBalancerClass") != "tailscale":
            continue
        ips = [i["ip"] for i in s.get("status", {}).get("loadBalancer", {}).get("ingress", []) or [] if "ip" in i and in_tailnet(i["ip"])]
        if ips:
            name = s["metadata"].get("annotations", {}).get("tailscale.com/hostname") or s["metadata"]["name"]
            out[label(name)] = ips[0]
    return out


def load_names(path):
    """A {"dev": {...}, "srv": {...}} JSON file -> (dev, srv); a missing file is empty."""
    try:
        with open(path) as f:
            doc = json.load(f)
    except FileNotFoundError:
        return {}, {}
    return doc.get("dev", {}), doc.get("srv", {})


def load_static(path=None):
    return load_names(path or STATIC)


def build_rrsets(dev, srv):
    """Pure: {name: ip} maps -> rrsets (without SOA), stable order."""
    rr = [{"name": ZONE, "type": "NS", "ttl": TTL, "records": [{"content": n, "disabled": False} for n in NAMESERVERS]}]
    for group, names in (("dev", dev), ("srv", srv)):
        for name in sorted(names):
            rr.append({"name": f"{name}.{group}.{ZONE}", "type": "A", "ttl": TTL, "records": [{"content": names[name], "disabled": False}]})
    return rr


def desired(nodes, services, static, inventory=({}, {})):
    sdev, ssrv = static
    idev, isrv = inventory
    dev = {**sdev, **idev, **from_nodes(nodes)}
    srv = {**ssrv, **isrv, **from_services(services)}
    return build_rrsets(dev, srv)


def sync(nodes, services, static, inventory=({}, {})):
    return zonesync.put_zone(ZONE, desired(nodes, services, static, inventory), HASH_KIND, f"{NAMESERVERS[0]} {SOA_RNAME} 1 {SOA_TIMERS}")


def main():
    if not loader.API_KEY:
        sys.exit("API_KEY is not set")
    last = None
    while True:
        try:
            nodes = k8s_get("/api/v1/nodes")
            if not nodes:
                raise RuntimeError("the Kubernetes API listed no nodes")
            sync(nodes, k8s_get("/api/v1/services"), load_static(), load_names(INVENTORY))
            last = None
        except Exception as e:
            if str(e) != last:
                loader.log(f"sync failed: {e}")
            last = str(e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
