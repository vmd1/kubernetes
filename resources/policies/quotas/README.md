# Quotas (`resources/policies/quotas/`)

One `ResourceQuota` named `default-quota` in every `tier=app` and `tier=infra` namespace (30 of them).

## Files

| File | Description |
| :--- | :--- |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint. |
| [quotas.yaml](quotas.yaml) | The quotas: `pods`, `persistentvolumeclaims` and `requests.storage`. |

## Design Decisions

- **Sizing rule** (usage on 2026-10-25): `pods = max(10, 3 x running)`, `persistentvolumeclaims = max(3, 2 x PVCs + 2)`, `requests.storage = max(20Gi, 2 x requested + 10Gi)`, each rounded up to 5. Raise a value in the same PR as the app that grows.
- **No cpu/memory quota and no LimitRange**: a compute quota rejects every pod that omits requests, and a LimitRange injects default limits into running apps. Neither can run in a warn-only mode, so they are out of this layer.
- **Existing usage fits**: no namespace is above its quota today, so nothing is evicted or blocked. A new object beyond the quota is refused (this is the only enforcing part of PR 1).
- **Guarded by CI**: `check-policies.sh` fails when a `tier=app`/`infra` namespace has no quota.

## Related

- [../README.md](../README.md) — the policies layer.
