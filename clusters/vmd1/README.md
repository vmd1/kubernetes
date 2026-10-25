# Cluster `vmd1` (`clusters/vmd1/`)

This folder is the **Flux entrypoint for the `vmd1` k3s cluster**. It declares the GitOps reconciliation layers as Flux `Kustomization` resources. Flux reconciles the cluster by applying this folder; each layer below points at a sub-tree of [resources/](../../resources/README.md).

## Table of Contents

- [Flux Bootstrap (`flux-system/`)](flux-system/README.md)
- [Reconciliation Layers](#reconciliation-layers)
- [Layer Dependency Chain](#layer-dependency-chain)
- [Files](#files)
- [Related](#related)

## Reconciliation Layers

The cluster is split into eight layers, plus Flux managing its own install:

| Flux Kustomization | Path | `dependsOn` | Purpose |
| :--- | :--- | :--- | :--- |
| [node-labels.yaml](node-labels.yaml) | `./resources/node-labels` | — | Labels on the eight Nodes (no taints). `wait: false`. |
| [namespaces.yaml](namespaces.yaml) | `./resources/namespaces` | — | Every Namespace except `default`, `kube-*` and `flux-system` |
| [crds.yaml](crds.yaml) | `./resources/crds` | `namespaces` | Vendored CRDs (CNPG, EdgeSite, OCIPortRule), never pruned |
| [operators.yaml](operators.yaml) | `./resources/operators` | `crds`, `node-labels` | Operators and charts (cert-manager, CNPG, Longhorn, Traefik, Multus, OCI controllers, Redis, Kube-VIP) |
| [nodes.yaml](nodes.yaml) | `./resources/nodes` | `operators` | `OCIPortRule` instances that open firewall ports on ingress nodes |
| [infrastructure.yaml](infrastructure.yaml) | `./resources/infrastructure` | `nodes` | Cluster infrastructure (Tailscale, Traefik middleware/LB, Longhorn UI + backup target, registry, lldap, cf-ddns, OCI reboot) |
| [applications.yaml](applications.yaml) | `./resources/applications` | `infrastructure` | User-facing applications (Authelia, Matrix, Media, Monitoring, Nextcloud, etc.) |
| [edge.yaml](edge.yaml) | `./resources/edge` | `operators` | DaemonSets on the ingress nodes (PowerDNS, GeoIP updater, edge-sites, error pages, podflow, node-exporter, promtail) |
| [flux-system/](flux-system/README.md) | `./clusters/vmd1/flux-system` | — | Flux's own components and sync, applied by the `flux-system` Kustomization itself |

## Layer Dependency Chain

```
node-labels ─┐
namespaces ──► crds ──► operators ──► nodes ──► infrastructure ──► applications
                            │
                            └──► edge   (nothing depends on edge)
```

- **Node labels** and **namespaces** come first, so no layer has to create the namespace it deploys into and every pod can find the nodes it selects.
- **CRDs** come next, so the custom resources in later layers (e.g. `OCIPortRule`, `Cluster`, `EdgeSite`) always have their types. Chart-installed CRDs (Traefik `IngressRoute`, cert-manager) still come from their HelmCharts in `operators`.
- **Operators** run the controllers for those CRDs.
- **Nodes** creates the `OCIPortRule` instances consumed by `oci-port-controller`.
- **Infrastructure** provides ingress, auth, storage, and registry primitives that applications depend on.
- **Applications** is reconciled last on the main chain.
- **Edge** holds every Flux-applied DaemonSet that runs on the 1 GB ingress nodes. Nothing depends on it, so a NotReady ingress node only marks `edge` NotReady instead of stalling infrastructure and applications.

## Files

| File | Description |
| :--- | :--- |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint; references `flux-system/` and the eight Flux Kustomization manifests. |
| [node-labels.yaml](node-labels.yaml) | Flux `Kustomization` for `./resources/node-labels` (`wait: false`, 2m timeout). |
| [namespaces.yaml](namespaces.yaml) | Flux `Kustomization` for `./resources/namespaces` (2m timeout). |
| [crds.yaml](crds.yaml) | Flux `Kustomization` for `./resources/crds` (2m timeout). |
| [operators.yaml](operators.yaml) | Flux `Kustomization` for `./resources/operators`, with SOPS decryption. |
| [nodes.yaml](nodes.yaml) | Flux `Kustomization` for `./resources/nodes`, with SOPS decryption. |
| [infrastructure.yaml](infrastructure.yaml) | Flux `Kustomization` for `./resources/infrastructure`, with SOPS decryption. |
| [applications.yaml](applications.yaml) | Flux `Kustomization` for `./resources/applications`, with SOPS decryption. |
| [edge.yaml](edge.yaml) | Flux `Kustomization` for `./resources/edge`, with SOPS decryption. |
| [flux-system/](flux-system/README.md) | Flux bootstrap manifests (components + GitRepository sync), now reconciled by Flux. |

> Every layer uses `interval: 10m` and `prune: true`; all but `node-labels` use `wait: true`. Objects that must never be deleted by a prune (Namespaces, CRDs, Nodes) carry `kustomize.toolkit.fluxcd.io/prune: disabled`.

## Related

- [flux-system/README.md](flux-system/README.md) — how Flux itself is bootstrapped and synced to this repository.
- [../../resources/README.md](../../resources/README.md) — the layered manifest tree these Kustomizations point at.
- [../../../cluster-info.md](../../../cluster-info.md) — cluster inventory, node labels, and helm chart versions.
