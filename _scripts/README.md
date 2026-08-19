# Scripts (`_scripts/`)

This folder contains standalone helper scripts used when operating the cluster or repository. They are **not** deployed into the cluster by Flux.

## Table of Contents

- [Files](#files)
- [apply-secrets.sh](#apply-secretssh)
- [load-test.js](#load-testjs)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [apply-secrets.sh](apply-secrets.sh) | Decrypts and applies SOPS-encrypted `secrets.sops.yaml` files to the cluster. |
| [load-test.js](load-test.js) | [k6](https://k6.io) load-test script that hammers the ingress edge nodes and asserts latency/error thresholds. |

## apply-secrets.sh

Helper script for working with the repository's [SOPS-encrypted secrets](../.sops.yaml).

```bash
_scripts/apply-secrets.sh --dry-run   # validate all secrets client-side (no cluster changes)
_scripts/apply-secrets.sh --diff      # show diff between SOPS secrets and live cluster state
_scripts/apply-secrets.sh --apply     # decrypt and apply to the cluster (default)
```

- Discovers every `secrets.sops.yaml` under `resources/applications` and `resources/infrastructure` and pipes the decrypted output into `kubectl`.
- Requires the Age key (`SOPS_AGE_KEY_FILE` or `~/.config/sops/age/keys.txt`) and a working `kubectl` context.
- Note: SOPS decryption happens automatically in-cluster via Flux, so this script is only needed for manual/one-off operations.

## load-test.js

A [k6](https://k6.io) load test that generates concurrent traffic against every ingress endpoint (`zeus-01/02`, `hera-01/02`, `ares-01/02`, `uk-home`) using a `Host: vmd1.homelab` override, ramping up to 400–800 VUs per target over ~14 minutes.

```bash
k6 run _scripts/load-test.js
```

Thresholds assert that p(95) latency stays under 500ms and the error rate below 1% per target.

## Related

- [../.sops.yaml](../.sops.yaml) — SOPS/Age encryption configuration (referenced by `apply-secrets.sh`).
- [../cluster-info.md](../cluster-info.md) — lists this script as the secrets helper.
- [../README.md](../README.md) — repository overview and maintenance policy.
