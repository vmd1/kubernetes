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
│   └── vmd1/                     <- Primary cluster definition & reconciliation layers
│       ├── flux-system/          <- Flux bootstrap manifests
│       ├── crds-and-operators.yaml
│       ├── nodes.yaml
│       ├── infrastructure.yaml
│       └── applications.yaml
├── resources/                    <- Manifests reconciled by Flux across 4 layers
│   ├── crds-and-operators/       <- CRDs, operators, controllers
│   ├── nodes/                    <- Node firewall & port rules
│   ├── infrastructure/           <- Cluster-wide infrastructure & internal services
│   └── applications/             <- User-facing applications and workloads
└── _scripts/                     <- Standalone helper scripts (SOPS secret helper, load tests)
```

## Clusters

See [clusters/README.md](clusters/README.md) and [clusters/vmd1/README.md](clusters/vmd1/README.md) for details on cluster bootstrapping and Kustomization entrypoints.

## Resources

See [resources/README.md](resources/README.md) for details on the four deployment layers and their dependency chain:
1. [crds-and-operators/](resources/crds-and-operators/README.md)
2. [nodes/](resources/nodes/README.md)
3. [infrastructure/](resources/infrastructure/README.md)
4. [applications/](resources/applications/README.md)

## Scripts

See [_scripts/README.md](_scripts/README.md) for standalone operational scripts.

## Related

- [../cluster-info.md](../cluster-info.md) — machine-readable cluster inventory.
- [../.sops.yaml](../.sops.yaml) — SOPS encryption configuration.
- [../README.md](../README.md) — root repository documentation.
