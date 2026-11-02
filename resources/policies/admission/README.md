# Admission policies (`resources/policies/admission/`)

`ValidatingAdmissionPolicy` objects and their `ValidatingAdmissionPolicyBinding`s. Every binding except `vmd1-resource-limits` (advisory, `[Warn, Audit]`) is `validationActions: [Deny, Audit]` since 2026-11-02, so a violation prints a warning to the client and is recorded in the API audit log, and nothing is rejected.

## Files

| File | Applies to | Rule |
| :--- | :--- | :--- |
| [baseline.yaml](baseline.yaml) | pods in `tier=app`/`infra` | no privileged, hostNetwork/PID/IPC or extra capabilities (namespace labels `policy.vmd1.homelab/allow-host-network`, `allow-host-pid`, `allow-privileged` and `allow-capabilities` exempt a namespace) |
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

## Audit report (2026-11-02): readiness for Deny

Method: every live workload in `tier=app`/`infra` (96 distinct) was re-created as a server-side dry-run pod and the warnings counted. This is what the next rollout of each workload would have produced.

| Policy | Workloads that fail | Ready for Deny? |
| :--- | :--- | :--- |
| vmd1-baseline | 16 (node-exporter, podflow: hostPID in `monitoring`; fixed by the `allow-host-pid` namespace label added here) | After this lands: yes |
| vmd1-service-accounts | 1 (`qecomp`) | No, fix qecomp first |
| vmd1-metadata | 30 (no `app.kubernetes.io/name` pod label: bookorbit, matrix, nextcloud, vmd1-web, ...) | No, labels to add per app |
| vmd1-app-hardening | essentially every `tier=app` workload (runAsNonRoot, readOnlyRootFilesystem, seccomp, pinned tags) | No: flipping it would block each app at its next restart |
| vmd1-rbac-roles, vmd1-rbac-bindings | 54 and 16 evaluations failed since the API server started (operator ClusterRoles with wildcards, cluster-admin bindings outside the list) | No: would block Flux applying operator RBAC |
| vmd1-storage, vmd1-namespace-tier, vmd1-resource-limits | none seen / Warn permanently | storage and namespace-tier: yes after a re-check |

Update 2026-11-02, later the same day: home-assistant and collabora got `seccompProfile: RuntimeDefault`, qecomp's `migrate` init container got `runAsNonRoot`, `tailnet-admins` was added to the cluster-admin allow-list, a re-audit of live pods, CronJob templates and every Flux-rendered object came back clean, and all bindings except `resource-limits` were flipped to `[Deny, Audit]`. Roll-back: see the comment at the top of [bindings.yaml](bindings.yaml).

## Exemptions and fixes (app-hardening)

Legacy namespaces are exempted by label, owned in `resources/namespaces/namespaces.yaml`; each label is tracked debt: `policy.vmd1.homelab/allow-root` (runAsNonRoot), `allow-writable-rootfs` (readOnlyRootFilesystem), `allow-privilege-escalation` (nextcloud for Collabora, home-assistant). Nothing drops capabilities: the fixes set only `seccompProfile: RuntimeDefault`, `allowPrivilegeEscalation: false`, the `app.kubernetes.io/name` pod label, and `runAsNonRoot` plus the same `runAsUser` for the five workloads that already run as a fixed uid (cinepro 1001, gossip 1000, headlamp 100, qecomp 1000, edge-operator 65534). Collabora and home-assistant (file capabilities, extra caps) get the label only. Merging rolls every touched workload once.

## Related

- [../README.md](../README.md) — the policies layer.
