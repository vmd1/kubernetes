# Policies (`resources/policies/`)

Admission policies and namespace quotas for the `vmd1` cluster, applied by the `policies` Flux Kustomization ([../../clusters/vmd1/policies.yaml](../../clusters/vmd1/policies.yaml)). Nothing depends on this layer, so a broken policy cannot hold up an app group. Part of the cluster hardening plan (`kubernetes/HARDENING-PLAN.md`, added by the plan PR), PR 1 of 3.

## Files

| Path | Description |
| :--- | :--- |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint: `admission/` and `quotas/`. |
| [admission/](admission/README.md) | Eight `ValidatingAdmissionPolicy` objects, their bindings (Warn + Audit only) and the parameter ConfigMaps. |
| [quotas/](quotas/README.md) | A `ResourceQuota` in every `tier=app` and `tier=infra` namespace. |

## Design Decisions

- **Select by label, not by name**: bindings pick namespaces with `vmd1.homelab/tier` (set in [../namespaces/](../namespaces/README.md)); exemptions are namespace labels (`policy.vmd1.homelab/allow-*`) owned in Git, never labels on a pod.
- **Warn and Audit only**: PR 1 denies nothing. `failurePolicy` is `Ignore` so a policy that cannot evaluate never blocks a pod. PR 3 flips bindings to `Deny` once the audit log is clean.
- **Built-ins only**: `ValidatingAdmissionPolicy` is GA in Kubernetes 1.35; no policy engine is installed.
- **Guarded by CI**: [../../../.github/scripts/check-policies.sh](../../../.github/scripts/check-policies.sh) fails a PR when a namespace lacks a tier, a tier=app/infra namespace lacks a quota, a Namespace is declared outside [../namespaces/](../namespaces/README.md), or an IP/CIDR literal appears here.

## Related

- `kubernetes/HARDENING-PLAN.md` — the plan and rollout (added by the plan PR).
- [../README.md](../README.md) — the layer order.
