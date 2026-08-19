# Applications Layer (`resources/applications/`)

This layer contains the **user-facing applications** deployed on the `vmd1` cluster. It is reconciled last by Flux (after [crds-and-operators](../crds-and-operators/README.md), [nodes](../nodes/README.md), and [infrastructure](../infrastructure/README.md)) because the applications depend on ingress, auth, storage, and database primitives provided by the lower layers.

The [kustomization.yaml](kustomization.yaml) here is the Kustomize entrypoint that pulls in every application subfolder below.

## Table of Contents

| Application | Description |
| :--- | :--- |
| [Authentik](authentik/README.md) | Centralized Identity Provider (IdP) with SSO forward-auth middleware for Traefik. |
| [Cinepro](cinepro/README.md) | Media-aggregation API backend (`cinepro-core`) with Redis caching. |
| [Headlamp](headlamp/README.md) | Kubernetes web UI dashboard with cluster-admin service account access. |
| [Home Assistant](home-assistant/README.md) | Home automation core on the local subnet with a filebrowser sidecar. |
| [Matrix](matrix/README.md) | Self-hosted Matrix stack: `continuwuity` homeserver, FluffyChat web client, and mautrix bridges. |
| [Media](media/README.md) | Jellyfin streaming, Overseerr (`seerr`) requests, and a download agent. |
| [Monitoring](monitoring/README.md) | Loki + Promtail logs, Prometheus + Node Exporter + Kube State Metrics, and Grafana. |
| [MQTT](mqtt/README.md) | Eclipse Mosquitto broker for IoT/Home Assistant messaging. |
| [Nextcloud](nextcloud/README.md) | Nextcloud + Collabora Online office suite with Backblaze B2 S3 primary storage. |
| [Ntfy](ntfy/README.md) | HTTP pub-sub push notification service with SMTP ingress. |
| [Obsidian](obsidian/README.md) | CouchDB backend for Obsidian Self-Hosted LiveSync. |
| [UniFi](unifi/README.md) | UniFi Network Application for managing UniFi networking hardware. |
| [Uptime Kuma](uptime-kuma/README.md) | Self-hosted uptime and latency monitoring. |
| [Vaultwarden](vaultwarden/README.md) | Lightweight Bitwarden-compatible password vault (PostgreSQL + Authentik SSO). |
| [vmd1-dev](vmd1-dev/README.md) | Personal web/developer portal DaemonSet running on ingress edge nodes. |

## Common Patterns

- **Ingress**: Applications are exposed via Traefik `IngressRoute` resources on `websecure` with the `cluster-wildcard-tls` certificate.
- **Auth**: Many admin/status UIs are gated behind the `authentik-auth` middleware from the [Authentik](authentik/README.md) namespace.
- **Storage**: Stateful applications use `longhorn-single-replica` or `local-path` StorageClasses and pin to `region: uk-home` nodes.
- **Secrets**: Credentials live in SOPS-encrypted `secrets.sops.yaml` files alongside each application.

## Related

- [kustomization.yaml](kustomization.yaml) — the Kustomize entrypoint for this layer.
- [../infrastructure/README.md](../infrastructure/README.md) — infrastructure primitives these applications depend on.
- [../../clusters/vmd1/applications.yaml](../../clusters/vmd1/applications.yaml) — the Flux Kustomization that reconciles this layer.
- [../../cluster-info.md](../../cluster-info.md) — detailed per-application inventory.
