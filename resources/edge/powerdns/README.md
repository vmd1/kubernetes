# PowerDNS Authoritative Server

PowerDNS is configured as an Authoritative DNS server running on the ingress nodes. It acts as a GeoIP-backed primary DNS service directing client traffic (e.g. for `ingress.vmd1.homelab`) to the closest healthy edge node (UK, Europe, or India) using LUA records.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines ConfigMap (`powerdns-config`) containing python zone-generators and configurations, DaemonSet running PowerDNS (`dl010/powerdns-auth:5.0.5`), and internal volumes. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `powerdns-secrets` holding `PDNS_API_KEY`, a random 64-character hex key read by the `pdns` container via `secretKeyRef`. |
| [kustomization.yaml](kustomization.yaml) | Generates ConfigMap `powerdns-shadow-zones` from `shadow-zones/` (no name hash, so a zone edit reloads in place instead of restarting the DaemonSet). |
| [shadow-zones/](shadow-zones) | **Generated, do not edit:** `named.conf` plus one BIND zone file each for `vmd1.homelab`, `vmd1.homelab`, `vmd1.homelab`, `vmd1.homelab` and `ts.ingress.vmd1.homelab`. Rendered by [`dns/shadow/render.js`](../../../../dns/README.md#shadow-zones-for-tailnet-split-dns) from the DNSControl source. |
| [operator.yaml](operator.yaml) | ServiceAccount, RBAC and Deployment for `powerdns-operator`, which turns the nodes' `node.vmd1.homelab/public-ip` and zone labels into the `geoip-zones.yaml` ConfigMap PowerDNS reads. Runs the image `ghcr.io/vmd1/powerdns-operator` (pinned by digest, built from [`controllers/powerdns-operator`](../../../../controllers/powerdns-operator)). |

## Design Decisions

- **DaemonSet on Ingress Nodes**: PowerDNS runs with `hostNetwork: true` directly on ingress nodes (`node-type: ingress` label) to listen on port `53` and receive public traffic.
- **Dynamic GeoIP Routing**:
  - Leverages MaxMind's `GeoLite2-City.mmdb` and PowerDNS's GeoIP backend. The database is kept fresh by the [geoip-updater](../geoip-updater/README.md) DaemonSet in `/var/lib/geoip`; the pod only mounts that directory read-only (as a directory, not a `subPath`, because the updater replaces the file atomically).
  - **Reload on update:** the `config-watcher` sidecar also watches the database file (inode, mtime, size, every 10 s) and runs `pdns_control reload` when it changes. Verified: after an atomic replacement pdns keeps the old file mapped (`(deleted)`) until reloaded, and `pdns_control reload` re-opens the new one (the PowerDNS docs only mention the zones file).
  - Generates zone files dynamically at startup using a Python initContainer (`init-zone`).
  - Implements LUA `ifurlup` records to return the closest healthy node's IP to the client based on distance and health check metrics (`https://vmd1.homelab/health`).
- **No Directory Shadowing**: To avoid overlaying config folders and losing the container's default configs, generated files are placed in an `emptyDir` volume and mounted as individual files using `subPath` definitions.
- **AXFR Whitelist**: Restricts zone transfers (`PDNS_allow_axfr_ips`) strictly to Cloudflare's IP ranges to sync changes to secondary name servers.
- **No Version Disclosure**: `PDNS_version_string=anonymous` makes `version.bind`/`version.pdns` queries return REFUSED instead of the exact PowerDNS build string. Recursion and AXFR were already refused on all ingress nodes.


## Shadow zones (tailnet split DNS)

Goal: attach the `tailnet-only` middleware ([proxy/traefik](../../proxy/traefik/README.md)) to a route and the service is reachable only with Tailscale on, with no per-service DNS change.

How: PowerDNS also serves a copy of each public zone (the `bind` backend, next to `geoip`). Tailscale split DNS (admin console, below) sends tailnet clients' queries for the four domains to the PowerDNS nodes' tailnet IPs. In that copy, every name that points at `ingress.vmd1.homelab` or any name below it (`*.ingress.vmd1.homelab`, e.g. `uk-home.ingress.vmd1.homelab`; a non-tailnet source keeps the original target) is a `LUA` record that looks at the source address: a tailnet source (`100.64.0.0/10`, `fd7a:115c:a1e0::/48`) gets `CNAME ts.ingress.vmd1.homelab.`, anyone else gets `CNAME ingress.vmd1.homelab.` (apex and names that share a name with MX/TXT get the equivalent `A` records, because a CNAME cannot sit there). `ts.ingress.vmd1.homelab` is its own zone: `ifurlup('https://vmd1.homelab/health', {zeus-01, hades-01, hera-01 tailnet IPs}, selector='all')`, so a dead node drops out within a health-check interval. Traefik then sees a `100.x` peer and `tailnet-only` lets the request through; with Tailscale off, the name resolves publicly through Cloudflare and `tailnet-only` returns 403.

- **Everything else is copied verbatim** (MX, TXT, SRV, Pages CNAMEs, plain A), so a tailnet client loses no record type. Names IGNOREd by dnscontrol are not in its output: `home.d-ingress.vmd1.homelab` and `home.locations.vmd1.homelab` (dynamic home WAN IP) are defined in the shadow zones like any other ingress name (tailnet source: `ts.ingress.vmd1.homelab`; anyone else: `uk-home.ingress.vmd1.homelab`), and records that reference them are repointed at `uk-home.ingress.vmd1.homelab` the same way. Names queried directly inside `ingress.vmd1.homelab` are answered by the geoip zone as before; the rest (`_acme-challenge`, Cloudflare DKIM, `gcse-results`) are listed in `dns/shadow/config.json` `allowMissing` with the reason.
- **Source address**: PowerDNS' Lua `netmask()` uses the query's source, or the EDNS client subnet when present (`PDNS_edns_subnet_processing=yes`). Tailscale's resolver sends no ECS. Spoofing a tailnet ECS from the public internet only returns tailnet IPs, which are unroutable without the tailnet. Answers differ per client and PowerDNS does not serve them from its packet cache (checked by alternating tailnet and non-tailnet queries on one name).
- **Most specific zone wins**: `ingress.vmd1.homelab` (geoip) and `ts.ingress.vmd1.homelab` (bind) are hosted here as their own zones, so they never fall into the `vmd1.homelab` shadow zone's `*` wildcard (without them it would loop). The `ingress`/`*.ingress` NS delegations are therefore omitted from the shadow `vmd1.homelab`.
- **Reload**: the `config-watcher` sidecar notices the `powerdns-shadow-zones` ConfigMap change (`..data` symlink) and runs `pdns_control rediscover` plus `bind-reload-now <zone>`; no restart.
- **Verified in throwaway pods before merge** (image `dl010/powerdns-auth:5.0.7`, the production env incl. `geoip,bind` and a copy of the live `geoip-zones.yaml`): all zones load with 0 rejected; `app.vmd1.homelab` returns `ts.ingress.vmd1.homelab` + the three tailnet IPs for a tailnet source and `ingress.vmd1.homelab` for a non-tailnet source (via ECS); apex/MX/TXT/SRV, wildcards (`*`, `*.vmd1`), `jellyfin.vmd1.homelab` → `uk-home.ingress`, and an in-place zone reload all behave. The first query after a cold start returns one tailnet IP (health state still warming up), then all three.

### Enabling split DNS (manual, Tailscale admin console)

Nothing changes for any client until this is done, and removing it is the rollback.

1. **ACL first.** Split DNS is tailnet-wide and the queries go over the tailnet, so every member's devices must be allowed to reach the nameservers, and then the nodes' web ports (otherwise `vmd1.homelab` resolves to a tailnet IP they cannot connect to). Today only `vmodi1009@gmail.com` has `ip: *` to everything and `group:admin` only has `tag:servers:22`. Suggested grant for `tailscale/policy.hujson` (these ports are already public on the ingress nodes):
   ```
   {
     "src": ["autogroup:member"],
     "dst": ["tag:k3s"],
     "ip":  ["53", "80", "443", "853", "8448"],
   },
   ```
2. **Split DNS entries** for `vmd1.homelab`, `vmd1.homelab`, `vmd1.homelab` and `vmd1.homelab`, each with the nameservers `100.100.91.41` (zeus-01), `100.90.0.8` (hera-01) and `100.68.218.120` (ares-02; the most stable ingress node by NotReady time, ares-01 flapped during the rollout). The admin console takes one IP per entry, so use the script, which sets all three through the API: [`tailscale/split-dns.sh`](../../../../tailscale/README.md#split-dns-not-part-of-the-policy-file) (`--domains vmd1.homelab` first, `--remove` to roll back). It checks every nameserver answers before changing anything.
3. Clients need **Use Tailscale DNS settings** on. Browsers using their own secure DNS (DoH) bypass it and will hit `tailnet-only` as a non-tailnet client; turn that off or select the system resolver.
4. The cluster nodes must not accept Tailscale DNS, or they (and pods, through CoreDNS) would get tailnet answers too. Done: all 8 nodes run `tailscale set --accept-dns=false` (see [docs/host-config.md](../../../../docs/host-config.md), including the CoreDNS restart gotcha). cert-manager's self-check also uses `1.1.1.1`/`8.8.8.8` explicitly.
5. The ACL grant for `autogroup:member` to `tag:k3s` (53, 80, 443, 853, 8448) is in `tailscale/policy.hujson`.

Verify from a tailnet device: `dig app.vmd1.homelab` returns `ts.ingress.vmd1.homelab` and `100.x` addresses, and `curl -I https://<service>` works; with Tailscale off the same name resolves to Cloudflare and a `tailnet-only` route answers 403.

### Adding or removing a tailnet-only service

Add `- {name: tailnet-only, namespace: traefik}` to the route's `middlewares` (and remove it to make the service public again). No DNS change. After editing `dns/domains/*.js` or `dns/shadow/config.json`, run `node dns/shadow/render.js` and commit the generated `shadow-zones/` (CI fails otherwise).

## Dependencies

- **GeoIP Database**: the [geoip-updater](../geoip-updater/README.md) DaemonSet (namespace `geoip`, all nodes) provides `/var/lib/geoip/GeoLite2-City.mmdb`. The `wait-geoip-db` init container waits up to 10 minutes for it, then falls back to the old per-node cache. The MaxMind credentials live in `geoip/maxmind-credentials`; this namespace has no MaxMind secret any more.
- **Edge Health Checks**: Relies on `https://vmd1.homelab/health` availability for DNS-level failovers.

## Services & Routers

- **Ports**: Exposes port `53` (TCP/UDP) directly on the host interface (`hostNetwork: true`).
- **Web Server / API**: Internal admin dashboard running on `127.0.0.1:8081` with the API enabled for local use only. The API key is a random 64-character hex string in the SOPS Secret `powerdns-secrets` (it used to be the literal `changeme`). To rotate it, generate a new one (`openssl rand -hex 32`), put it in `secrets.sops.yaml` with `sops`, merge, then run `kubectl rollout restart ds/powerdns -n powerdns` (pods read the Secret only at start, so changing it does not roll them by itself).

## Storage

- **MaxMind GeoIP Database**: read from the node-level hostPath directory `/var/lib/geoip` (written by the geoip-updater). The old `/var/lib/powerdns/geoip` cache is only mounted read-only by the init container as a last-resort fallback.
- **Transient Zones File**: The zone configurations generated by python are stored in an `emptyDir: {}` volume and projected into the pdns container.

## Constraints & Scheduling

- **Node Selectors**: Pinned to nodes with label `node-type: ingress` via a DaemonSet pattern.
- **Tolerations**: Tolerates all taints to ensure DNS routing runs even during node maintenance.
- **Resource Constraints**:
  - Request: `50m` CPU, `64Mi` RAM.
  - Limit: `200m` CPU, `256Mi` RAM.

## Configs & Credentials

- **ConfigMap**: `powerdns-config`
  - `ingress-nodes.json`: Single source of truth containing geographical IP mappings for edge nodes.
  - `init-zone.sh` and `gen-zone.py`: Generator scripting to build zone rules.
- **Environment variables**: Controls launch modules, LUA activation, and AXFR policies inside the daemon.
