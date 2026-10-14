# EdgeSite CRD

Defines `edgesites.edge.vmd1.homelab` (`EdgeSite`, `edge.vmd1.homelab/v1alpha1`), the declarative description of a static site or Cloudflare-style Worker served by the [edge-sites](../../applications/edge-sites/README.md) platform.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [crd.yaml](crd.yaml) | The CustomResourceDefinition (namespaced, status subresource, printer columns). This is the single source of the CRD; nothing under `edge-services/` duplicates it. |

## Design Decisions

- Lives in `crds-and-operators` so the CRD exists before the operator and any `EdgeSite` objects are applied.
- `spec.serve` is the (default) inline serve config, free-form here and validated by the operator and builder against the edge-serve.yml schema.
- `status` is free-form (`x-kubernetes-preserve-unknown-fields`) and owned by the edge-operator.

## Dependencies

None.
