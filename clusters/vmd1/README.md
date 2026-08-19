# Cluster `vmd1` (`clusters/vmd1/`)

This folder is the **Flux entrypoint for the `vmd1` k3s cluster**. It declares the GitOps reconciliation layers as Flux `Kustomization` resources. Flux reconciles the cluster by applying this folder; each layer below points at a sub-tree of [resources/](../../resources/README.md).

## Table of Contents

- [Flux Bootstrap (`flux-system/`)](flux-system/README.md)
- [Reconciliation Layers](#reconciliation-layers)
- [Layer Dependency Chain](#layer-dependency-chain)
- [Files](#files)
- [Related](#related)

## Reconciliation Layers

The cluster is split into four layers, applied in dependency order:

| Flux Kustomization | Path | `dependsOn` | Purpose |
| :--- | :--- | :--- | :--- |
| [crds-and-operators.yaml](crds-and-operators.yaml) | `./resources/crds-and-operators` | — | CRDs and operators (cert-manager, CNPG, Longhorn, Traefik, Multus, OCI controllers, PowerDNS, Redis, Kube-VIP) |
| [nodes.yaml](nodes.yaml) | `./resources/nodes` | `crds-and-operators` | `OCIPortRule` instances that open firewall ports on ingress nodes |
| [infrastructure.yaml](infrastructure.yaml) | `./resources/infrastructure` | `nodes` | Cluster infrastructure (Tailscale, Traefik middleware/LB, Longhorn UI + backup target, registry, lldap, cf-ddns, OCI reboot) |
| [applications.yaml](applications.yaml) | `./resources/applications` | `infrastructure` | User-facing applications (Authentik, Matrix, Media, Monitoring, Nextcloud, etc.) |

## Layer Dependency Chain

```
crds-and-operators ──► nodes ──► infrastructure ──► applications
```

- **CRDs & operators** must exist first so that custom resources (e.g. `OCIPortRule`, `IngressRoute`, `Cluster`) can be reconciled by later layers.
- **Nodes** layer creates the `OCIPortRule` instances consumed by `oci-port-controller` (deployed in the CRDs layer).
- **Infrastructure** provides ingress, auth, storage, and registry primitives that applications depend on.
- **Applications** is reconciled last.

## Files

| File | Description |
| :--- | :--- |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint; references the four Flux Kustomization manifests below. |
| [crds-and-operators.yaml](crds-and-operators.yaml) | Flux `Kustomization` for `./resources/crds-and-operators`, with SOPS decryption. |
| [nodes.yaml](nodes.yaml) | Flux `Kustomization` for `./resources/nodes`, with SOPS decryption. |
| [infrastructure.yaml](infrastructure.yaml) | Flux `Kustomization` for `./resources/infrastructure`, with SOPS decryption. |
| [applications.yaml](applications.yaml) | Flux `Kustomization` for `./resources/applications`, with SOPS decryption. |
| [flux-system/](flux-system/README.md) | Flux bootstrap manifests (components + GitRepository sync). |

> All four layer Kustomizations use `interval: 10m`, `prune: true`, `wait: true`, and SOPS decryption via the `sops-age` secret in the `flux-system` namespace.

## Related

- [flux-system/README.md](flux-system/README.md) — how Flux itself is bootstrapped and synced to this repository.
- [../../resources/README.md](../../resources/README.md) — the layered manifest tree these Kustomizations point at.
- [../../cluster-info.md](../../cluster-info.md) — cluster inventory, node labels, and helm chart versions.
