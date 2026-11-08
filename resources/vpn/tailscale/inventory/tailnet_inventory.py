#!/usr/bin/env python3
"""Publishes the tailnet's devices and Tailscale Services as a ConfigMap (powerdns/tailnet-inventory) for the PowerDNS
ts.int sync (resources/edge/powerdns/primary/loader/tsint_sync.py).

Runs in the tailscale namespace because the operator's OAuth client (secret operator-oauth, mounted read-only at
/oauth) lives here; the PowerDNS API key lives in the powerdns namespace and never meets it. The ConfigMap is the only
thing that crosses: {"dev": {"<name>": "<tailnet ip>"}, "srv": {"<name>": "<tailnet ip>"}} (JSON).

  dev  every device except the operator's proxy pods (tag:k8s-operator, tag:k8s-apiserver), named by its MagicDNS label
  lab  the devices among those that carry one of LAB_TAGS (default tag:k3s): the cluster nodes, as <name>.lab
  srv  every Tailscale Service (svc:<name>), its IPv4 address
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.tailscale.com/api/v2"
OAUTH_DIR = os.environ.get("OAUTH_DIR", "/oauth")
TARGET_NS = os.environ.get("TARGET_NAMESPACE", "powerdns")
TARGET_CM = os.environ.get("TARGET_CONFIGMAP", "tailnet-inventory")
INTERVAL = int(os.environ.get("INTERVAL", "60"))
LAB_TAGS = set(os.environ.get("LAB_TAGS", "tag:k3s").split(","))
SKIP_TAGS = set(os.environ.get("SKIP_TAGS", "tag:k8s-operator,tag:k8s-apiserver").split(","))
K8S = "https://kubernetes.default.svc"
SA = "/var/run/secrets/kubernetes.io/serviceaccount"


def log(msg):
    print(msg, flush=True)


def token():
    with open(f"{OAUTH_DIR}/client_id") as f:
        cid = f.read().strip()
    with open(f"{OAUTH_DIR}/client_secret") as f:
        cs = f.read().strip()
    body = urllib.parse.urlencode({"client_id": cid, "client_secret": cs, "grant_type": "client_credentials"}).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{API}/oauth/token", data=body), timeout=20) as r:
        return json.load(r)["access_token"]


def ts_get(tok, path):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def label(name):
    """DNS label from a MagicDNS name or hostname."""
    first = name.split(".")[0].lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", first)).strip("-")


def ipv4(addrs):
    return next((a for a in addrs or [] if ":" not in a), None)


def build(devices, vip_services):
    dev, srv, lab = {}, {}, {}
    for d in devices:
        if SKIP_TAGS & set(d.get("tags") or []):
            continue
        ip = ipv4(d.get("addresses"))
        name = label(d.get("name") or d.get("hostname") or "")
        if not ip or not name:
            continue
        base, n = name, 1
        while name in dev and dev[name] != ip:  # two devices with one label: -2, -3, ...
            n += 1
            name = f"{base}-{n}"
        dev[name] = ip
        if LAB_TAGS & set(d.get("tags") or []):
            lab[name] = ip
    for s in vip_services:
        ip = ipv4(s.get("addrs"))
        name = label(s.get("name", "").removeprefix("svc:"))
        if ip and name:
            srv[name] = ip
    return {"dev": dict(sorted(dev.items())), "lab": dict(sorted(lab.items())), "srv": dict(sorted(srv.items()))}


def k8s(method, path, body=None):
    with open(f"{SA}/token") as f:
        tok = f.read().strip()
    ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(K8S + path, data=data, method=method, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
        return json.load(r)


def publish(inv):
    text = json.dumps(inv, indent=1, sort_keys=True) + "\n"
    path = f"/api/v1/namespaces/{TARGET_NS}/configmaps"
    try:
        cm = k8s("GET", f"{path}/{TARGET_CM}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        k8s("POST", path, {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": TARGET_CM, "namespace": TARGET_NS}, "data": {"inventory.json": text}})
        log(f"created {TARGET_NS}/{TARGET_CM}: {len(inv['dev'])} devices ({len(inv['lab'])} lab), {len(inv['srv'])} services")
        return True
    if (cm.get("data") or {}).get("inventory.json") == text:
        return False
    cm["data"] = {"inventory.json": text}
    k8s("PUT", f"{path}/{TARGET_CM}", cm)
    log(f"updated {TARGET_NS}/{TARGET_CM}: {len(inv['dev'])} devices ({len(inv['lab'])} lab), {len(inv['srv'])} services")
    return True


def main():
    last = None
    while True:
        try:
            tok = token()
            devices = ts_get(tok, "/tailnet/-/devices")["devices"]
            services = ts_get(tok, "/tailnet/-/services").get("vipServices", [])
            if not devices:
                raise RuntimeError("the Tailscale API listed no devices")  # never publish an empty inventory
            publish(build(devices, services))
            last = None
        except Exception as e:
            if str(e) != last:
                log(f"sync failed: {e}")
            last = str(e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
