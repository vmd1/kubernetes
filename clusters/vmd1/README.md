# Cluster `vmd1` (`clusters/vmd1/`)

This folder is the **Flux entrypoint for the `vmd1` k3s cluster**. It declares the GitOps reconciliation layers as Flux `Kustomization` resources. Flux reconciles the cluster by applying this folder; each layer below points at a sub-tree of [resources/](../../resources/README.md).

## Table of Contents

- [Flux Bootstrap (`flux-system/`)](flux-system/README.md)
- [Reconciliation Layers](#reconciliation-layers)
- [Layer Dependency Chain](#layer-dependency-chain)
- [Files](#files)
- [Related](#related)

## Reconciliation Layers

Four foundation layers run in order; everything else is a purpose group that depends only on `operators`:

| Flux Kustomization | Path | `dependsOn` | Purpose |
| :--- | :--- | :--- | :--- |
| [node-labels.yaml](node-labels.yaml) | `./resources/node-labels` | — | Labels on the eight Nodes (no taints). `wait: false`. |
| [namespaces.yaml](namespaces.yaml) | `./resources/namespaces` | — | Every Namespace except `default`, `kube-*` and `flux-system` |
| [policies.yaml](policies.yaml) | `./resources/policies` | `namespaces` | Admission policies and quotas. Nothing depends on it. |
| [crds.yaml](crds.yaml) | `./resources/crds` | `namespaces` | Vendored CRDs (CNPG, EdgeSite, OCIPortRule), never pruned |
| [operators.yaml](operators.yaml) | `./resources/operators` | `crds`, `node-labels` | Operators and charts (cert-manager, CNPG, Longhorn, Traefik, Multus, OCI port controller, Redis, Kube-VIP) |
| [vpn.yaml](vpn.yaml) | `./resources/vpn` | `operators` | Tailscale operator and region controller |
| [oci.yaml](oci.yaml) | `./resources/oci` | `operators` | OCI reboot watchdog and the ingress nodes' `OCIPortRule`s |
| [proxy.yaml](proxy.yaml) | `./resources/proxy` | `operators` | Traefik Middlewares, TLS options, uk-home LB, dashboard and guard routes; cf-ddns |
| [auth.yaml](auth.yaml) | `./resources/auth` | `operators` | lldap, Authelia, oauth2-proxy |
| [platform.yaml](platform.yaml) | `./resources/platform` | `operators` | Private registry; Longhorn UI and backup target |
| [observability.yaml](observability.yaml) | `./resources/observability` | `operators` | Loki, Prometheus, Grafana, kube-state-metrics, Uptime Kuma, ntfy, Headlamp, Homelable |
| [home.yaml](home.yaml) | `./resources/home` | `operators` | Home Assistant, Mosquitto, UniFi |
| [media.yaml](media.yaml) | `./resources/media` | `operators` | Jellyfin, BookOrbit, Cinepro |
| [personal.yaml](personal.yaml) | `./resources/personal` | `operators` | Nextcloud, Obsidian, Vaultwarden, Matrix |
| [projects.yaml](projects.yaml) | `./resources/projects` | `operators` | QEComp, Gossip |
| [edge.yaml](edge.yaml) | `./resources/edge` | `operators` | DaemonSets on the ingress nodes (PowerDNS, GeoIP updater, edge-sites, error pages, podflow, node-exporter, promtail) |
| [flux-system/](flux-system/README.md) | `./clusters/vmd1/flux-system` | — | Flux's own components and sync, applied by the `flux-system` Kustomization itself |

## Layer Dependency Chain

```
node-labels ─┐
namespaces ──► crds ──► operators ──┬──► vpn, oci, proxy, auth, platform,
                                    │    observability, home, media, personal, projects
                                    └──► edge
```

- **Node labels** and **namespaces** come first, so no layer has to create the namespace it deploys into and every pod can find the nodes it selects.
- **CRDs** come next, so custom resources (`OCIPortRule`, `Cluster`, `EdgeSite`) always have their types. Chart-installed CRDs (Traefik `IngressRoute`, cert-manager) come from their HelmCharts in `operators`.
- **Operators** run the controllers and databases (CNPG, Redis) the groups use.
- **Purpose groups** depend only on `operators`. Links between groups (an IngressRoute using a `proxy` Middleware or the `auth` ForwardAuth, an app pulling from `platform`'s registry) are resolved at request time, not at apply time, so they are deliberately not `dependsOn`: a broken manifest in one group cannot stop another from reconciling, and `flux suspend kustomization <group>` pauses just that group.
- **Edge** holds every Flux-applied DaemonSet on the 1 GB ingress nodes, so a NotReady ingress node only marks `edge` NotReady.

## Files

| File | Description |
| :--- | :--- |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint; references `flux-system/` and the 15 Flux Kustomization manifests. |
| [node-labels.yaml](node-labels.yaml), [namespaces.yaml](namespaces.yaml), [crds.yaml](crds.yaml) | Foundation layers (no SOPS, 2m timeout; `node-labels` has `wait: false`). |
| [operators.yaml](operators.yaml) | Operators layer, with SOPS decryption. |
| `<group>.yaml` (10) and [edge.yaml](edge.yaml) | One Flux `Kustomization` per purpose group: `./resources/<group>`, `dependsOn: operators`, SOPS decryption, 5m timeout. |
| [flux-system/](flux-system/README.md) | Flux bootstrap manifests (components + GitRepository sync), reconciled by Flux. |

> Every layer uses `interval: 10m` and `prune: true`; all but `node-labels` use `wait: true`. Objects that must never be deleted by a prune (Namespaces, CRDs, Nodes) carry `kustomize.toolkit.fluxcd.io/prune: disabled`. To move objects between Kustomizations, pause pruning on the source in git first; see [docs/history/flux-layer-split-2026-10-25.md](../../../docs/history/flux-layer-split-2026-10-25.md).

## Related

- [flux-system/README.md](flux-system/README.md) — how Flux itself is bootstrapped and synced to this repository.
- [../../resources/README.md](../../resources/README.md) — the layered manifest tree these Kustomizations point at.
- [../../../cluster-info.md](../../../cluster-info.md) — cluster inventory, node labels, and helm chart versions.
