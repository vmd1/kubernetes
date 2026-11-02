# OCI Controller Secrets (`resources/operators/oci-controller/`)

This folder holds the **shared SOPS-encrypted secrets** for the `oci-controller` namespace. It contains no workloads itself — the controllers that consume these secrets are [oci-reboot](../../oci/oci-reboot/README.md) and [oci-port-controller](../oci-port-controller/README.md).

## Table of Contents

- [Files](#files)
- [Secrets](#secrets)
- [Consumers](#consumers)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted (Age) secrets for the `oci-controller` namespace. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint that includes `secrets.sops.yaml`. |

## Secrets

Per [docs/manifests.md](../../../../docs/manifests.md), the encrypted file contains:

| Secret | Purpose |
| :--- | :--- |
| `node-ssh-key` | Private SSH key used by `oci-port-controller` to reach node host firewalls. |
| `oci-credentials-<region>` | OCI API credentials for the UK London (`zeus-01`, `zeus-02`) region. |
| `oci-credentials-<region>` | OCI API credentials for the India West (`ares-01`, `ares-02`) region. |
| `oci-credentials-<region>` | OCI API credentials for the EU Marseille (`hera-01`, `hera-02`) region. |

## Consumers

| Consumer | Location | Uses |
| :--- | :--- | :--- |
| [oci-port-controller](../oci-port-controller/README.md) | `resources/operators/oci-port-controller/` | `node-ssh-key` + all `oci-credentials-<region>*` for security list / firewall sync. |
| [oci-reboot](../../oci/oci-reboot/README.md) | `resources/oci/oci-reboot/` | `oci-credentials-<region>*` for OCI instance resets (via the `oci-account` node label). |

## Network policy

Enrolled in the NetworkPolicy baseline (HARDENING-PLAN.md, Appendix E): baseline, egress-public, api-server. No ingress. Same-namespace traffic is allowed; everything else is denied by default.

## Related

- [../oci-port-controller/README.md](../oci-port-controller/README.md) — the port-opening controller.
- [../../oci/oci-reboot/README.md](../../oci/oci-reboot/README.md) — the reboot watchdog controller.
- [../../oci/firewall/README.md](../../oci/firewall/README.md) — the `FirewallRule` instances reconciled by `oci-port-controller`.
