# CRDs & Operators Layer (`resources/crds-and-operators/`)

This layer contains the **Custom Resource Definitions (CRDs) and operators** that the rest of the cluster builds upon. It is reconciled **first** by Flux so that the custom resources (e.g. `OCIPortRule`, `IngressRoute`, `Cluster`, `HelmChart`) referenced by later layers exist and are serviced by their controllers.

The [kustomization.yaml](kustomization.yaml) here is the Kustomize entrypoint for the whole layer.

## Table of Contents

| Component | Description |
| :--- | :--- |
| [cert-manager](cert-manager/README.md) | Automated TLS certificates via Let's Encrypt ACME with Cloudflare DNS-01 validation. |
| [cnpg](cnpg/README.md) | CloudNativePG operator + `pg-cluster` high-availability PostgreSQL cluster. |
| [kube-vip](kube-vip/README.md) | Kube-VIP load balancer providing virtual IPs on the `uk-home` zone. |
| [longhorn](longhorn/README.md) | Longhorn operator chart, recurring backup jobs, and the S3 backup secret. (UI + BackupTarget live in [infrastructure/longhorn](../infrastructure/longhorn/README.md).) |
| [multus](multus/README.md) | Multus CNI meta-plugin and the `storage-macvlan-eth0` network attachment for Longhorn. |
| [oci-controller](oci-controller/README.md) | Shared SOPS secrets (`node-ssh-key`, `oci-credentials-<region>*`) for the `oci-controller` namespace. |
| [oci-port-controller](oci-port-controller/README.md) | Controller + `OCIPortRule` CRD that opens ports on OCI security lists and host firewalls. |
| [powerdns](powerdns/README.md) | PowerDNS authoritative DNS with GeoIP-backed routing to the closest healthy edge node. |
| [redis](redis/README.md) | Redis operator, master-replica replication, Sentinel, and HAProxy load balancer. |
| [traefik](traefik/README.md) | Traefik ingress controller HelmChart (DaemonSet, host network). (Middlewares/LB live in [infrastructure/traefik](../infrastructure/traefik/README.md).) |

## Notes

- Some components are **split across layers**: the Longhorn and Traefik operator charts live here, while their UI/routing/middleware resources live in [infrastructure/](../infrastructure/README.md).
- The [oci-controller](oci-controller/README.md) folder contains only secrets; the actual controllers (reboot + port) live in [infrastructure/oci-reboot](../infrastructure/oci-reboot/README.md) and here respectively.
- The `OCIPortRule` CRD instances consumed by `oci-port-controller` live in the [nodes/](../nodes/README.md) layer.

## Related

- [../nodes/README.md](../nodes/README.md) — `OCIPortRule` instances reconciled after this layer.
- [../infrastructure/README.md](../infrastructure/README.md) — companion infrastructure layer.
- [../../clusters/vmd1/crds-and-operators.yaml](../../clusters/vmd1/crds-and-operators.yaml) — the Flux Kustomization that reconciles this layer.
- [../../cluster-info.md](../../cluster-info.md) — detailed per-component inventory.
