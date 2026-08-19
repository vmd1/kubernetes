# Clusters (`clusters/`)

This directory holds the **FluxCD GitOps cluster definitions** for this repository. Each subfolder represents a single Kubernetes cluster and contains the Flux `Kustomization` resources that tell Flux which parts of the repository to reconcile, in what order, and with which settings (e.g. SOPS decryption).

## Contents

| Path | Description |
| :--- | :--- |
| [vmd1/](vmd1/README.md) | The `vmd1` k3s homelab cluster definition — the only cluster managed by this repository. |

## How It Fits Together

```
clusters/vmd1/  <- Flux entrypoint for the vmd1 cluster (see vmd1/README.md)
└── flux-system/          <- Bootstrap manifests (Flux components + GitRepository sync)
```

Flux watches this repository via the `flux-system` GitRepository (defined in [vmd1/flux-system/gotk-sync.yaml](vmd1/flux-system/gotk-sync.yaml)) and applies everything under `clusters/vmd1/`. The actual workload manifests live in the layered [resources/](../resources/README.md) tree, which the Flux Kustomizations in `clusters/vmd1/` point at.

## Related

- [vmd1/README.md](vmd1/README.md) — cluster-level configuration and the four reconciliation layers.
- [../resources/README.md](../resources/README.md) — the manifest layers Flux reconciles (CRDs & operators, nodes, infrastructure, applications).
- [../../README.md](../../README.md) — repository overview, secrets management, and maintenance policy.
- [../../cluster-info.md](../../cluster-info.md) — machine-readable cluster inventory (nodes, helm charts, namespaces).
