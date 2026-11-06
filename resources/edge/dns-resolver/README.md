# dns-resolver

A public recursive resolver (DNS-over-TLS and DNS-over-HTTPS) on every ingress edge node, with ad/tracker/category blocking that each client selects by the hostname it connects to. It replaces the pre-Flux `Infrastructure/dns-resolver`, with the same idea and a rebuilt pipeline.

## Files

| Path | Description |
| :--- | :--- |
| [daemonset.yaml](daemonset.yaml) | DaemonSet `dns-resolver` (dnsdist + unbound + sync) and Service `dns-resolver` (`internalTrafficPolicy: Local`). |
| [controller.yaml](controller.yaml) | Blocklist controller: ServiceAccount, Role, Deployment (not on edge nodes) and Service. |
| [controller/](controller/controller.py) | The controller (stdlib Python, mounted from a ConfigMap) and its offline tests (`python3 -m unittest test_controller`). |
| [config/](config/dnsdist.conf) | `dnsdist.conf`, `unbound.conf`, `sync.sh`. |
| [blocklists.yaml](blocklists.yaml) | The `Blocklist` objects (ads, trackers, senso, smoothwall, fl). |
| [certificate.yaml](certificate.yaml) | Wildcard certificate for `dns.vmd1.homelab` and `*.dns.vmd1.homelab`. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik routes: DoT (TCP passthrough, PROXY v2) and DoH. |

## How it works

- **Using it**: DoT to `<profile>.dns.vmd1.homelab:853`, DoH at `https://<profile>.dns.vmd1.homelab/dns-query`; every name also works under `dns.vmd1.homelab`. `<profile>` is `-`-separated Blocklist names (`ads-trackers`); plain `dns.vmd1.homelab` blocks nothing. Blocked names get NXDOMAIN, subdomains included. DoH also accepts `?blocklists=ads,trackers`.
- **Add a list**: apply a `Blocklist` (see [../../crds/blocklist/](../../crds/blocklist/README.md)). `kubectl -n dns-resolver get bl` shows whether it compiled.
- **Data path**: controller downloads and compiles each list once (`hosts` or plain-domain format, deduplicated, `maxEntries` cap) and serves the result over HTTP in the cluster. Each edge pod's `sync` sidecar polls the controller every minute and verifies the SHA-256; dnsdist loads a changed list in place (one list per pass), so list updates never restart a pod. A failed fetch or download keeps the last good list.
- **Traffic**: Traefik (hostNetwork) sends DoT as raw TCP with a PROXY v2 header to the pod on its own node, so dnsdist sees the real client address and the SNI; DoH is terminated at Traefik and forwarded as h2c.
- **Limits**: 50 queries/s per client (burst 200), 10 TCP connections per client, 100 queries and 120 s per connection, plus Traefik's `rate-limit` on DoH. It is an open resolver by design.

## Design Decisions

- **Why the old one failed**: lists were stuffed into a Secret (1 MiB limit, the real lists are ~2.4 MB), nodes had no memory to spare, and the dnsdist Lua used invalid actions. Now lists never touch the API server as data and are held once in dnsdist.
- **Memory**: dnsdist is the cost, about 25 MiB plus roughly 0.4 KiB per domain (the default lists are ~120k domains, ~90 MiB measured in Docker with the reload copy). Edge nodes have ~660 MiB allocatable and already run close to it, so watch `kubectl top` after the rollout and lower `maxEntries` or drop a list if a node is squeezed.
- **Not nativeLB**: Traefik would spread DoT over every node's pod; the ClusterIP with `Local` keeps a query on the node it arrived at.
- **No metrics yet**: dnsdist's web/Prometheus endpoint is not enabled.

## Operations

```bash
kubectl -n dns-resolver get blocklists
kubectl -n dns-resolver logs deploy/blocklist-controller
kubectl -n dns-resolver logs ds/dns-resolver -c dnsdist
```
