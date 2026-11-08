"""Shared by the controllers that own one zone on the primary (ingress_sync.py, tsint_sync.py): make a zone's rrsets
equal to a computed set through the PowerDNS API, gated by a content hash in zone metadata so the SOA serial
(soa-edit-api) only moves when the content does. Builds on loader.py's API helpers."""
import hashlib
import json

import loader


def digest(rrsets):
    return hashlib.sha256(json.dumps(rrsets, sort_keys=True).encode()).hexdigest()


def put_zone(zone, rrsets, hash_kind, soa_content):
    """Create the zone (SOA seeded from soa_content) or replace its non-SOA rrsets. Returns True when something changed."""
    want_hash = digest(rrsets)
    try:
        existing = loader.api("GET", loader.zone_path(zone))
    except RuntimeError as e:
        if "HTTP 404" not in str(e) and "Could not find domain" not in str(e):
            raise
        existing = None
    if existing is None:
        soa = {"name": zone, "type": "SOA", "ttl": 60, "records": [{"content": soa_content, "disabled": False}]}
        loader.api("POST", f"/api/v1/servers/{loader.SERVER}/zones", {"name": zone, "kind": "Master", "nameservers": [], "rrsets": [soa] + rrsets})
        loader.set_metadata(zone, hash_kind, [want_hash])
        loader.log(f"{zone}: created with {len(rrsets) + 1} rrsets")
        return True
    if loader.get_metadata(zone, hash_kind) == [want_hash]:
        return False
    want = {(r["name"], r["type"]) for r in rrsets}
    patch = [dict(r, changetype="REPLACE") for r in rrsets]
    patch += [{"name": r["name"], "type": r["type"], "changetype": "DELETE"}
              for r in existing.get("rrsets", []) if r["type"] != "SOA" and (r["name"], r["type"]) not in want]
    loader.api("PATCH", loader.zone_path(zone), {"rrsets": patch})
    loader.set_metadata(zone, hash_kind, [want_hash])
    loader.log(f"{zone}: updated ({len(patch)} rrset operations)")
    return True
