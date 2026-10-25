# CRDs (`resources/crds/`)

CustomResourceDefinitions that are vendored as plain manifests, applied by the `crds` Flux Kustomization ([../../clusters/vmd1/crds.yaml](../../clusters/vmd1/crds.yaml)) after `namespaces` and before `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [cnpg/](cnpg/README.md) | The 9 CloudNativePG CRDs (`clusters.postgresql.cnpg.io`, `backups`, `poolers`, ...). |
| [edgesite/](edgesite/README.md) | `EdgeSite` CRD for the edge-services platform. |
| [oci-port-controller/](oci-port-controller/README.md) | `OCIPortRule` CRD used by the `nodes` layer. |

## Design Decisions

- **Never pruned**: [kustomization.yaml](kustomization.yaml) annotates every CRD `kustomize.toolkit.fluxcd.io/prune: disabled`. Deleting a CRD deletes every object of that kind; for CNPG that is every database `Cluster`. Remove a CRD by hand once nothing uses it.
- **Chart CRDs stay with their charts**: cert-manager, Longhorn, Traefik, Tailscale and redis-operator install their CRDs from their HelmCharts in [../operators/](../operators/README.md). k3s's helm-controller applies those, so Flux does not order or wait on them.

## Related

- [../README.md](../README.md): layer order.
