# Kubernetes Configurations (`kubernetes/`)

This directory contains all the Kubernetes manifests, FluxCD GitOps definitions, and cluster operation scripts for the homelab cluster.

## Table of Contents

- [Directory Structure](#directory-structure)
- [Clusters](#clusters)
- [Resources](#resources)
- [Scripts](#scripts)
- [Related](#related)

## Directory Structure

```
kubernetes/
├── clusters/                     <- Flux cluster definitions and entrypoints
│   └── vmd1/                     <- Primary cluster definition: one Flux Kustomization per layer/group
│       ├── flux-system/          <- Flux bootstrap manifests (reconciled by Flux)
│       ├── node-labels.yaml, namespaces.yaml, crds.yaml, operators.yaml
│       └── <group>.yaml          <- vpn, oci, proxy, auth, platform, observability, home, media, personal, projects, edge
├── resources/                    <- Manifests reconciled by Flux
│   ├── node-labels/, namespaces/, crds/, operators/   <- foundation, applied in order
│   └── <group>/                  <- purpose groups, each depending only on operators
└── _scripts/                     <- Standalone helper scripts (SOPS secret helper, load tests)
```

## Clusters

See [clusters/README.md](clusters/README.md) and [clusters/vmd1/README.md](clusters/vmd1/README.md) for details on cluster bootstrapping and Kustomization entrypoints.

## Resources

See [resources/README.md](resources/README.md) for the layers and how they depend on each other:
- Foundation: [node-labels/](resources/node-labels/README.md), [namespaces/](resources/namespaces/README.md), [crds/](resources/crds/README.md), [operators/](resources/operators/README.md)
- Purpose groups: [vpn/](resources/vpn/README.md), [oci/](resources/oci/README.md), [proxy/](resources/proxy/README.md), [auth/](resources/auth/README.md), [platform/](resources/platform/README.md), [observability/](resources/observability/README.md), [home/](resources/home/README.md), [media/](resources/media/README.md), [personal/](resources/personal/README.md), [projects/](resources/projects/README.md), [edge/](resources/edge/README.md)

## Scripts

See [_scripts/README.md](_scripts/README.md) for standalone operational scripts.

## Related

- [../cluster-info.md](../cluster-info.md) — machine-readable cluster inventory.
- [../.sops.yaml](../.sops.yaml) — SOPS encryption configuration.
- [../README.md](../README.md) — root repository documentation.
