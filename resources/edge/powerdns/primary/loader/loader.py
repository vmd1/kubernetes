#!/usr/bin/env python3
"""Keeps the PowerDNS primary's zones equal to the rrsets JSON rendered from git (dns/shadow/render.js).

Runs next to the primary pod's pdns container and talks to its API on localhost. Every INTERVAL seconds, for each
*.rrsets.json in ZONES_DIR:

  - the zone does not exist       -> create it (kind Master) with every rrset, SOA included
  - its hash differs from the one stored in the zone's X-LOADER-HASH metadata
                                  -> one PATCH: REPLACE every desired rrset except SOA, DELETE the rest
  - otherwise nothing is sent (so the SOA serial only moves when the content does)

The SOA serial belongs to PowerDNS (soa-edit-api): the rendered SOA only seeds a new zone and is never sent again, so
a change to the SOA timers needs the zone to be recreated. Zones in the database that have no file here (e.g. ones
another writer owns) are never touched. There is no NOTIFY: the primary is a pod, its NOTIFYs would come from an
address that is not the secondaries' configured master and be refused, so the secondaries poll on the SOA refresh.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_URL = os.environ.get("API_URL", "http://XXX.XXX.XXX.XXX:8081").rstrip("/")
API_KEY = os.environ.get("API_KEY", "")
SERVER = os.environ.get("SERVER_ID", "localhost")
ZONES_DIR = os.environ.get("ZONES_DIR", "/zones")
INTERVAL = int(os.environ.get("INTERVAL", "30"))
HASH_KIND = "X-LOADER-HASH"


def log(msg):
    print(msg, flush=True)


def api(method, path, body=None, base=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request((base or API_URL) + path, data=data, method=method)
    req.add_header("X-API-Key", API_KEY)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path}: HTTP {e.code} {e.read().decode(errors='replace')[:300]}") from None


def zone_path(name, suffix=""):
    return f"/api/v1/servers/{SERVER}/zones/{urllib.parse.quote(name, safe='')}{suffix}"


def load_desired(zones_dir):
    out = []
    for fn in sorted(os.listdir(zones_dir)):
        if fn.endswith(".rrsets.json"):
            with open(os.path.join(zones_dir, fn)) as f:
                text = f.read()
            doc = json.loads(text)
            doc["_hash"] = hashlib.sha256(text.encode()).hexdigest()
            out.append(doc)
    return out


def get_metadata(zone, kind):
    try:
        got = api("GET", zone_path(zone, f"/metadata/{kind}"))
    except RuntimeError as e:
        if "HTTP 404" in str(e):
            return []
        raise
    return (got or {}).get("metadata", [])


def set_metadata(zone, kind, values):
    api("PUT", zone_path(zone, f"/metadata/{kind}"), {"kind": kind, "metadata": values})


def sync_zone(doc):
    name = doc["zone"]
    rrsets = doc["rrsets"]
    existing = None
    try:
        existing = api("GET", zone_path(name))
    except RuntimeError as e:
        if "HTTP 404" not in str(e) and "Could not find domain" not in str(e):
            raise
    changed = False
    if existing is None:
        api("POST", f"/api/v1/servers/{SERVER}/zones", {"name": name, "kind": doc.get("kind", "Master"), "nameservers": [], "rrsets": rrsets})
        log(f"{name}: created with {len(rrsets)} rrsets")
        changed = True
    elif get_metadata(name, HASH_KIND) != [doc["_hash"]]:
        desired = {(r["name"], r["type"]) for r in rrsets}
        patch = [dict(r, changetype="REPLACE") for r in rrsets if r["type"] != "SOA"]
        patch += [{"name": r["name"], "type": r["type"], "changetype": "DELETE"}
                  for r in existing.get("rrsets", []) if r["type"] != "SOA" and (r["name"], r["type"]) not in desired]
        api("PATCH", zone_path(name), {"rrsets": patch})
        log(f"{name}: updated ({len(patch)} rrset operations)")
        changed = True
    if changed:
        set_metadata(name, HASH_KIND, [doc["_hash"]])
    return changed


def run_once():
    docs = load_desired(ZONES_DIR)
    if not docs:
        raise RuntimeError(f"no *.rrsets.json in {ZONES_DIR}")
    for doc in docs:
        sync_zone(doc)


def main():
    if not API_KEY:
        sys.exit("API_KEY is not set")
    last_error = None
    while True:
        try:
            run_once()
            last_error = None
        except Exception as e:  # a failed pass is retried; the primary keeps serving what it has
            if str(e) != last_error:
                log(f"sync failed: {e}")
            last_error = str(e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
