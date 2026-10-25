# Resources (`resources/`)

This directory contains all the Kubernetes manifests that Flux reconciles into the `vmd1` cluster, organized into eight layers. Each layer is pointed at by a Flux `Kustomization` defined in [clusters/vmd1/](../clusters/vmd1/README.md) and is applied in a strict dependency order.

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
| [nodes/](nodes/README.md) | `./resources/nodes` | `OCIPortRule` instances (web, DNS, DoT, Tailscale WireGuard ports) targeting ingress nodes. |
| [infrastructure/](infrastructure/README.md) | `./resources/infrastructure` | Cluster services: Tailscale, Traefik middleware/LB, Longhorn UI + backup target, cf-ddns, lldap, OCI reboot controller, registry. |
| [applications/](applications/README.md) | `./resources/applications` | User-facing applications: Authelia, Cinepro, Headlamp, Home Assistant, Matrix, Media, Monitoring, MQTT, Nextcloud, Ntfy, oauth2-proxy, Obsidian, UniFi, Uptime Kuma, Vaultwarden. |
| [edge/](edge/README.md) | `./resources/edge` | DaemonSets on the ingress nodes: PowerDNS, GeoIP updater, edge-sites, error pages, podflow, node-exporter, promtail. |

## Reconciliation Order

```
node-labels ─┐
namespaces ──► crds ──► operators ──► nodes ──► infrastructure ──► applications
                            │
                            └──► edge   (nothing depends on edge)
```

Each layer's Flux Kustomization declares `dependsOn` the layer before it (see [../clusters/vmd1/README.md](../clusters/vmd1/README.md)). `edge` hangs off `operators` with nothing depending on it, so a flaky ingress node cannot stall the main chain.

## Secrets

All secrets live next to their workloads as SOPS-encrypted `secrets.sops.yaml` files (Age encryption) and are decrypted in-cluster by Flux using the `sops-age` secret. See [../../.sops.yaml](../../.sops.yaml) for the encryption configuration and [../_scripts/apply-secrets.sh](../_scripts/apply-secrets.sh) for a helper to apply them manually.

## Related

- [../clusters/vmd1/README.md](../clusters/vmd1/README.md) — the Flux Kustomizations that drive these layers.
- [../../cluster-info.md](../../cluster-info.md) — detailed inventory of every resource in these layers.
- [../../README.md](../../README.md) — repository overview and maintenance policy.
