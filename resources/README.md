# Resources (`resources/`)

This directory contains all the Kubernetes manifests that Flux reconciles into the `vmd1` cluster, organized into four layers. Each layer is pointed at by a Flux `Kustomization` defined in [clusters/vmd1/](../clusters/vmd1/README.md) and is applied in a strict dependency order.

## Table of Contents

- [Layers](#layers)
- [Reconciliation Order](#reconciliation-order)
- [Secrets](#secrets)
- [Related](#related)

## Layers

| Layer | Flux Path | Contents |
| :--- | :--- | :--- |
| [crds-and-operators/](crds-and-operators/README.md) | `./resources/crds-and-operators` | Custom Resource Definitions and operators: cert-manager, CloudNativePG, Kube-VIP, Longhorn, Multus, OCI controller secrets, OCI port controller, PowerDNS, Redis, Traefik. |
| [nodes/](nodes/README.md) | `./resources/nodes` | `OCIPortRule` instances (web, DNS, DoT, Tailscale WireGuard ports) targeting ingress nodes. |
| [infrastructure/](infrastructure/README.md) | `./resources/infrastructure` | Cluster services: Tailscale, Traefik middleware/LB, Longhorn UI + backup target, cf-ddns, lldap, OCI reboot controller, registry. |
| [applications/](applications/README.md) | `./resources/applications` | User-facing applications: Authentik, Cinepro, Headlamp, Home Assistant, Matrix, Media, Monitoring, MQTT, Nextcloud, Ntfy, Obsidian, UniFi, Uptime Kuma, Vaultwarden, vmd1-dev. |

## Reconciliation Order

```
crds-and-operators ──► nodes ──► infrastructure ──► applications
```

Each layer's Flux Kustomization declares `dependsOn` the previous layer (see [clusters/vmd1/](../clusters/vmd1/README.md)), so operators and CRDs exist before the custom resources that rely on them, and infrastructure primitives exist before the applications that consume them.

## Secrets

All secrets live next to their workloads as SOPS-encrypted `secrets.sops.yaml` files (Age encryption) and are decrypted in-cluster by Flux using the `sops-age` secret. See [../.sops.yaml](../.sops.yaml) for the encryption configuration and [../_scripts/apply-secrets.sh](../_scripts/apply-secrets.sh) for a helper to apply them manually.

## Related

- [../clusters/vmd1/README.md](../clusters/vmd1/README.md) — the Flux Kustomizations that drive these layers.
- [../cluster-info.md](../cluster-info.md) — detailed inventory of every resource in these layers.
- [../README.md](../README.md) — repository overview and maintenance policy.
