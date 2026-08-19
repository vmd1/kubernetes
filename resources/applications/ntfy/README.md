# Ntfy Notification Service

Ntfy (pronounced "notify") is a simple HTTP-based pub-sub notification service. It allows the sending of desktop notifications, mobile alerts, and emails from scripts or apps using simple curl POST commands.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines the Namespace `ntfy`, two PersistentVolumeClaims for cache and auth files, Deployment running `binwiederhier/ntfy:latest`, HTTP Service, `LoadBalancer` SMTP Service, and Traefik `IngressRoute`. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted ConfigMap `ntfy-server-config` containing the server configuration, SMTP relay password, WebPush private key, and ACL user credentials. |

## Design Decisions

- **State Separation**: Spreads data storage into two separate PVCs: a transient cache volume and a highly guarded authentication volume.
- **Embedded Access Control Lists (ACLs)**: Configured with `auth-default-access "deny-all"` to restrict topic access by default. Custom ACL permissions define read-only, write-only, and read-write mappings for user accounts (e.g. `admin`, `worker`, `user2`) matching specific topic patterns (like `alerts-*`, `iot-*`, `up*`).
- **SMTP Gateway**: Exposes an SMTP receiver on port `25` utilizing a `LoadBalancer` service type to process inbound emails, translating them directly to push notifications.
- **Behind Proxy Flag**: Configured with `behind-proxy true` to trust headers set by Traefik and accurately extract client remote IPs.

## Dependencies

- **SMTP2Go Relay**: Connects to SMTP2Go (`mail.smtp2go.com:587`) for outbound email notifications.
- **K3s LoadBalancer Provider**: Resolves external IP addresses for the SMTP Service.

## Services & Routers

- **Kubernetes Services**:
  - `ntfy` (ClusterIP, exposing port `2586` HTTP API).
  - `ntfy-smtp` (LoadBalancer, exposing port `25` TCP).
- **Ingress Routes**:
  - `ntfy.vmd1.homelab` on `websecure` entrypoint routing HTTP API calls directly to `ntfy` service on port `2586`.

## Storage

- **PVCs**:
  - `ntfy-cache` (`local-path` StorageClass, size `2Gi` mounted at `/var/cache/ntfy`). Stores SQLite message cache (`cache.db`), attachments (`attachments/`), and push notifications tokens (`webpush.db`).
  - `ntfy-auth` (`local-path` StorageClass, size `256Mi` mounted at `/var/lib/ntfy`). Stores SQLite user credentials database (`user.db`).

## Constraints & Scheduling

- **Deployment Strategy**: Set to `Recreate` deployment strategy. This ensures that only a single instance of the Ntfy pod runs at any time, preventing multi-pod writes/locks on SQLite databases (`cache.db`, `user.db`).
- **Resource Constraints**:
  - Request: `50m` CPU, `64Mi` RAM.
  - Limit: `500m` CPU, `512Mi` RAM.

## Configs & Credentials

- **ConfigMap**: `ntfy-server-config`
  - Mounts `server.yml` defining the base URL, ports, proxy details, WebPush public/private keys, and user authentication tables.
