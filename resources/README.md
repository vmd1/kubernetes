# Resources (`resources/`)

This directory contains all the Kubernetes manifests that Flux reconciles into the `vmd1` cluster, organized into four foundation layers and eleven purpose groups. Each layer is pointed at by a Flux `Kustomization` defined in [clusters/vmd1/](../clusters/vmd1/README.md) and is applied in a strict dependency order.

## Table of Contents

- [Layers](#layers)
- [Reconciliation Order](#reconciliation-order)
- [Secrets](#secrets)
- [Related](#related)

## Layers

| Layer | Flux Path | Contents |
| :--- | :--- | :--- |
| [node-labels/](node-labels/README.md) | `./resources/node-labels` | Labels on each Node (no taints), Flux pruning disabled. |
| [namespaces/](namespaces/README.md) | `./resources/namespaces` | Every Namespace the cluster uses (except `default`, `kube-*`, `flux-system`), with Flux pruning disabled. |
| [crds/](crds/README.md) | `./resources/crds` | Vendored CRDs: CloudNativePG, EdgeSite, OCIPortRule. Never pruned. |
| [operators/](operators/README.md) | `./resources/operators` | Operators and charts: cert-manager, CloudNativePG, Kube-VIP, Longhorn, Multus, OCI controller secrets, OCI port controller, Redis, Traefik. |
| [vpn/](vpn/README.md) | `./resources/vpn` | Tailscale operator and region controller. |
| [oci/](oci/README.md) | `./resources/oci` | OCI reboot watchdog and the ingress nodes' `OCIPortRule`s. |
| [proxy/](proxy/README.md) | `./resources/proxy` | Traefik Middlewares, TLS options, uk-home LB, dashboard and guard routes; cf-ddns. |
| [auth/](auth/README.md) | `./resources/auth` | lldap, Authelia, oauth2-proxy. |
| [platform/](platform/README.md) | `./resources/platform` | Private registry; Longhorn UI and backup target. |
| [observability/](observability/README.md) | `./resources/observability` | Loki, Prometheus, Grafana, kube-state-metrics, Uptime Kuma, ntfy, Headlamp, Homelable. |
| [home/](home/README.md) | `./resources/home` | Home Assistant, Mosquitto, UniFi. |
| [media/](media/README.md) | `./resources/media` | Jellyfin, BookOrbit, Cinepro. |
| [personal/](personal/README.md) | `./resources/personal` | Nextcloud, Obsidian, Vaultwarden, Matrix. |
| [projects/](projects/README.md) | `./resources/projects` | QEComp, Gossip. |
| [edge/](edge/README.md) | `./resources/edge` | DaemonSets on the ingress nodes: PowerDNS, GeoIP updater, edge-sites, error pages, podflow, node-exporter, promtail. |

## Reconciliation Order

```
node-labels ─┐
namespaces ──► crds ──► operators ──┬──► vpn, oci, proxy, auth, platform,
                                    │    observability, home, media, personal, projects
                                    └──► edge
```

The four foundation layers run in order. Every purpose group and `edge` depends only on `operators` (see [../clusters/vmd1/README.md](../clusters/vmd1/README.md)), so a broken group cannot hold up any other.

## Secrets

All secrets live next to their workloads as SOPS-encrypted `secrets.sops.yaml` files (Age encryption) and are decrypted in-cluster by Flux using the `sops-age` secret. See [../../.sops.yaml](../../.sops.yaml) for the encryption configuration and [../_scripts/apply-secrets.sh](../_scripts/apply-secrets.sh) for a helper to apply them manually.

## Related

- [../clusters/vmd1/README.md](../clusters/vmd1/README.md) — the Flux Kustomizations that drive these layers.
- [../../docs/manifests.md](../../docs/manifests.md) — detailed inventory of every resource in these layers.
- [../../README.md](../../README.md) — repository overview and maintenance policy.
