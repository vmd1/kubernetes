# Applications Layer (`resources/applications/`)

This layer contains the **user-facing applications** deployed on the `vmd1` cluster. It is reconciled last by Flux (after [crds-and-operators](../crds-and-operators/README.md), [nodes](../nodes/README.md), and [infrastructure](../infrastructure/README.md)) because the applications depend on ingress, auth, storage, and database primitives provided by the lower layers.

The [kustomization.yaml](kustomization.yaml) here is the Kustomize entrypoint that pulls in every application subfolder below.

## Table of Contents

| Application | Description |
| :--- | :--- |
| [Authelia](authelia/README.md) | Cluster-wide OIDC provider (`identity.vmd1.homelab`) backed by lldap, CNPG and Redis; native OIDC clients for Grafana, Nextcloud, Jellyfin, BookOrbit, Home Assistant, QEComp and Vaultwarden. |
| [BookOrbit](bookorbit/README.md) | Digital library and reading platform (ebooks, audiobooks, comics, PDFs) with CNPG backend. |
| [Cinepro](cinepro/README.md) | Media-aggregation API backend (`cinepro-core`) with Redis caching. |
| [Gossip](gossip/README.md) | Gossip WebSocket relay and website (`gossip.vmd1.homelab`), single in-memory instance. |
| [Headlamp](headlamp/README.md) | Kubernetes web UI dashboard with cluster-admin service account access. |
| [Home Assistant](home-assistant/README.md) | Home automation core on the local subnet with a filebrowser sidecar. |
| [Matrix](matrix/README.md) | Self-hosted Matrix stack: `continuwuity` homeserver, FluffyChat web client, and mautrix bridges. |
| [Media](media/README.md) | Jellyfin streaming (Authelia SSO); Overseerr (`seerr`) and the download agent are currently scaled to zero. |
| [Monitoring](monitoring/README.md) | Loki + Promtail logs, Prometheus + Node Exporter + Kube State Metrics, and Grafana. |
| [MQTT](mqtt/README.md) | Eclipse Mosquitto broker for IoT/Home Assistant messaging. |
| [Nextcloud](nextcloud/README.md) | Nextcloud + Collabora Online office suite with Backblaze B2 S3 primary storage. |
| [Ntfy](ntfy/README.md) | HTTP pub-sub push notification service with SMTP ingress. |
| [oauth2-proxy](oauth2-proxy/README.md) | Per-domain Traefik ForwardAuth middlewares authenticating against Authelia. |
| [Obsidian](obsidian/README.md) | CouchDB backend for Obsidian Self-Hosted LiveSync. |
| [QEComp](qecomp/README.md) | OIDC-authenticated app with Redis leader-election HA, CNPG backend, signing in through the cluster-wide Authelia (lldap `qecomp-*` groups). |
| [UniFi](unifi/README.md) | UniFi Network Application for managing UniFi networking hardware. |
| [Uptime Kuma](uptime-kuma/README.md) | Self-hosted uptime and latency monitoring. |
| [Vaultwarden](vaultwarden/README.md) | Lightweight Bitwarden-compatible password vault (PostgreSQL + Authelia SSO). |
| [Edge Sites](edge-sites/README.md) | CRD-driven edge serving platform (edge-operator + `edge-sites` DaemonSet) for static sites and Workers. |
| [vmd1-dev](vmd1-dev/README.md) | Personal web/developer portal DaemonSet running on ingress edge nodes. |

## Common Patterns

- **Ingress**: Applications are exposed via Traefik `IngressRoute` resources on `websecure` with the `cluster-wildcard-tls` certificate.
- **Auth**: Grafana, Nextcloud, Jellyfin, BookOrbit, Home Assistant, QEComp and Vaultwarden sign in directly through Authelia (OIDC). Many other admin/status UIs (including LLDAP, UniFi and `status.vmd1.homelab`) are gated behind the per-domain `oauth2-proxy-<domain>` middlewares from the [oauth2-proxy](oauth2-proxy/README.md) namespace (Authelia SSO).
- **Storage**: Stateful applications use `longhorn-single-replica` or `local-path` StorageClasses and pin to `region: uk-home` nodes.
- **Secrets**: Credentials live in SOPS-encrypted `secrets.sops.yaml` files alongside each application.

## Related

- [kustomization.yaml](kustomization.yaml) — the Kustomize entrypoint for this layer.
- [../infrastructure/README.md](../infrastructure/README.md) — infrastructure primitives these applications depend on.
- [../../clusters/vmd1/applications.yaml](../../clusters/vmd1/applications.yaml) — the Flux Kustomization that reconciles this layer.
- [../../cluster-info.md](../../cluster-info.md) — detailed per-application inventory.
