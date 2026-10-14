# EdgeSite CRD

Defines `edgesites.edge.vmd1.homelab` (`EdgeSite`, `edge.vmd1.homelab/v1alpha1`), the declarative description of a static site or Cloudflare-style Worker served by the [edge-sites](../../applications/edge-sites/README.md) platform.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [crd.yaml](crd.yaml) | The CustomResourceDefinition (namespaced, status subresource, printer columns). Source of truth is [`edge-services/crd/edgesite-crd.yaml`](../../../../edge-services/crd/edgesite-crd.yaml); keep the two identical. |

## Design Decisions

- Lives in `crds-and-operators` so the CRD exists before the operator and any `EdgeSite` objects are applied.
- `status` is free-form (`x-kubernetes-preserve-unknown-fields`) and owned by the edge-operator.

## Dependencies

None.
