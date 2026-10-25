# EdgeSite CRD

Defines `edgesites.edge.vmd1.homelab` (`EdgeSite`, `edge.vmd1.homelab/v1alpha1`), the declarative description of a static site or Cloudflare-style Worker served by the [edge-sites](../../edge/edge-sites/README.md) platform.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [crd.yaml](crd.yaml) | The CustomResourceDefinition (namespaced, status subresource, printer columns). This is the single source of the CRD; nothing under `edge-services/` duplicates it. |

## Design Decisions

- Lives in `operators` so the CRD exists before the operator and any `EdgeSite` objects are applied.
- `spec.serve` is the (default) inline serve config, free-form here and validated by the operator and builder against the edge-serve.yml schema.
- `spec.auth` (whole site, or `paths` prefixes) is turned into oauth2-proxy/Authelia-gated routes by the operator; see the edge-sites README.
- `status` is free-form (`x-kubernetes-preserve-unknown-fields`) and owned by the edge-operator.

## Dependencies

None.
