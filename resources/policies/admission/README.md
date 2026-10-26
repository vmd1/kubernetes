# Admission policies (`resources/policies/admission/`)

`ValidatingAdmissionPolicy` objects and their `ValidatingAdmissionPolicyBinding`s. Every binding is `validationActions: [Warn, Audit]`, so a violation prints a warning to the client and is recorded in the API audit log, and nothing is rejected.

## Files

| File | Applies to | Rule |
| :--- | :--- | :--- |
| [baseline.yaml](baseline.yaml) | pods in `tier=app`/`infra` | no privileged, hostNetwork/PID/IPC or extra capabilities (namespace labels `policy.vmd1.homelab/allow-host-network`, `allow-privileged` and `allow-capabilities` exempt a namespace) |
| [app-hardening.yaml](app-hardening.yaml) | pods in `tier=app` | `runAsNonRoot`, no privilege escalation, read-only root filesystem, seccomp profile, image pinned by digest or a non-`latest` tag |
| [service-accounts.yaml](service-accounts.yaml) | pods in `tier=app` | a dedicated ServiceAccount, or `automountServiceAccountToken: false` on the default one |
| [rbac.yaml](rbac.yaml) | cluster | `cluster-admin` only to listed subjects; no wildcard verbs/resources in roles |
| [storage.yaml](storage.yaml) | pods in `tier=app`/`infra` | `hostPath` under the allow-listed prefixes |
| [metadata.yaml](metadata.yaml) | pods in `tier=app` | `app.kubernetes.io/name` label |
| [namespace-tier.yaml](namespace-tier.yaml) | cluster | a Namespace carries `vmd1.homelab/tier` |
| [resource-limits.yaml](resource-limits.yaml) | pods in `tier=app` | cpu and memory limits (stays Warn permanently) |
| [bindings.yaml](bindings.yaml) | | one binding per policy |
| [params/hostpath-allowlist.yaml](params/hostpath-allowlist.yaml) | | the two parameter ConfigMaps (hostPath prefixes, cluster-admin subjects), in `kube-system` |

## Design Decisions

- **Pods, CREATE only**: a pod's security context cannot change after creation, and controllers re-create pods on every rollout, so every workload is re-checked at its next restart. Policies do not see Deployment templates.
- **No PVC rule**: the default StorageClass is filled in before validation, so "must name a StorageClass" could never fail.
- **Data, not CEL, for allowlists**: add a hostPath prefix or a cluster-admin subject in [params/hostpath-allowlist.yaml](params/hostpath-allowlist.yaml), in the same PR as the workload that needs it.
- **Reading the results**: warnings show on `kubectl apply`; the audit log (see [../../k3s-config/](../../k3s-config/README.md)) carries `validation.policy.admission.k8s.io/validation_failure` annotations.
- **Tested for syntax only**: the CEL compiles on the API server (server-side dry-run), but no pod has been admitted against these yet. Expect the first Warn output to reveal rules that need adjusting.

## Related

- [../README.md](../README.md) — the policies layer.
