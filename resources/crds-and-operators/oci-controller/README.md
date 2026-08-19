# OCI Controller Secrets (`resources/crds-and-operators/oci-controller/`)

This folder holds the **shared SOPS-encrypted secrets** for the `oci-controller` namespace. It contains no workloads itself — the controllers that consume these secrets are [oci-reboot](../../infrastructure/oci-reboot/README.md) and [oci-port-controller](../oci-port-controller/README.md).

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

Per [cluster-info.md](../../../cluster-info.md), the encrypted file contains:

| Secret | Purpose |
| :--- | :--- |
| `node-ssh-key` | Private SSH key used by `oci-port-controller` to reach node host firewalls. |
| `oci-credentials-<region>` | OCI API credentials for the UK London (`zeus-01`, `zeus-02`) region. |
| `oci-credentials-<region>` | OCI API credentials for the India West (`ares-01`, `ares-02`) region. |
| `oci-credentials-<region>` | OCI API credentials for the EU Marseille (`hera-01`, `hera-02`) region. |

## Consumers

| Consumer | Location | Uses |
| :--- | :--- | :--- |
| [oci-port-controller](../oci-port-controller/README.md) | `resources/crds-and-operators/oci-port-controller/` | `node-ssh-key` + all `oci-credentials-<region>*` for security list / firewall sync. |
| [oci-reboot](../../infrastructure/oci-reboot/README.md) | `resources/infrastructure/oci-reboot/` | `oci-credentials-<region>*` for OCI instance resets (via the `oci-account` node label). |

## Related

- [../oci-port-controller/README.md](../oci-port-controller/README.md) — the port-opening controller.
- [../../infrastructure/oci-reboot/README.md](../../infrastructure/oci-reboot/README.md) — the reboot watchdog controller.
- [../../nodes/README.md](../../nodes/README.md) — the `OCIPortRule` instances reconciled by `oci-port-controller`.
