# FirewallRule and OCIPortRule CRDs (`crds/oci-port-controller/`)

| File | Description |
| :--- | :--- |
| [firewallrule-crd.yaml](firewallrule-crd.yaml) | `firewallrules.network.vmd1.homelab` (cluster-scoped, short name `fr`). `spec.type` is `OCI` or `Host`; only `OCI` is enforced today (Phase F adds `Host`). Reconciled by [../../operators/oci-port-controller/](../../operators/oci-port-controller/README.md); instances live in [../../oci/firewall/](../../oci/firewall/README.md). |
| [crd.yaml](crd.yaml) | `ociportrules.network.vmd1.homelab`. **Deprecated**, replaced by `FirewallRule`. The controller still reconciles any leftover object as an implicit `FirewallRule` of type OCI and adds a `Deprecated` condition. After one clean reconcile cycle with no `OCIPortRule` objects left, delete the CRD by hand (`kubectl delete crd ociportrules.network.vmd1.homelab`; CRDs are `prune: disabled`) and then remove `crd.yaml` from here. |
