# Infrastructure Layer (`resources/infrastructure/`)

This layer contains **cluster infrastructure services** — networking, ingress helpers, storage management, and operator tooling — that the application layer builds on. It is reconciled by Flux after [crds-and-operators](../crds-and-operators/README.md) and [nodes](../nodes/README.md), and before [applications](../applications/README.md).

The [kustomization.yaml](kustomization.yaml) here is the Kustomize entrypoint for the layer.

## Table of Contents

| Component | Description |
| :--- | :--- |
| [cf-ddns](cf-ddns/README.md) | CronJob updating the home gateway's Cloudflare A record with its dynamic public IP. |
| [lldap](lldap/README.md) | Lightweight LDAP user directory backed by the CNPG PostgreSQL cluster. |
| [longhorn](longhorn/README.md) | Longhorn UI `IngressRoute` and the S3 `BackupTarget` (Backblaze B2). (Operator chart lives in [crds-and-operators/longhorn](../crds-and-operators/longhorn/README.md).) |
| [oci-reboot](oci-reboot/README.md) | Watchdog controller that force-reboots unresponsive OCI nodes via the Oracle API. |
| [registry](registry/README.md) | Private Docker registry with htpasswd basic auth behind Traefik. |
| [tailscale](tailscale/README.md) | Tailscale operator + region-aware connector/proxy-class automation controller. |
| [traefik](traefik/README.md) | Traefik middlewares (rate-limit, security-headers, compress, TLS options), dashboard route, and the `uk-home` LoadBalancer. (Controller chart lives in [crds-and-operators/traefik](../crds-and-operators/traefik/README.md).) |

## Notes

- Components like **Traefik** and **Longhorn** are intentionally split: the operator/controller charts live in [crds-and-operators/](../crds-and-operators/README.md), while this layer holds their routing, middleware, and storage-target resources.
- The `oci-reboot` and `oci-port-controller` controllers share the `oci-controller` namespace and its secrets (see [crds-and-operators/oci-controller](../crds-and-operators/oci-controller/README.md)).

## Related

- [../crds-and-operators/README.md](../crds-and-operators/README.md) — the operators these infrastructure resources extend.
- [../applications/README.md](../applications/README.md) — the applications that consume this layer.
- [../../clusters/vmd1/infrastructure.yaml](../../clusters/vmd1/infrastructure.yaml) — the Flux Kustomization that reconciles this layer.
- [../../cluster-info.md](../../cluster-info.md) — detailed per-component inventory.
