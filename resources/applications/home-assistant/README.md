# Home Assistant

Home Assistant is a home automation platform running locally in the cluster. It integrates smart home components and runs a file manager sidecar to permit direct configuration edits.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines the namespace, deployment running `home-assistant` (with a `filebrowser` sidecar container), PVC, services, and two Traefik `IngressRoute` records. |
| [migrate.ps1](migrate.ps1) | A PowerShell migration script that waits for the seed pod, copies local configuration data via `kubectl cp` into the cluster PVC, and then scales up the Home Assistant deployment. |

## Design Decisions

- **Host Network Mode**: Runs with `hostNetwork: true` and `dnsPolicy: ClusterFirstWithHostNet`. This is crucial for local mDNS/SSDP smart home device auto-discovery (e.g. LIFX, Apple HomeKit, Google Cast) which relies on broadcast domains.
- **Embedded File Browser Sidecar**: Integrates a `filebrowser/filebrowser` container in the same pod sharing the `/config` mount. This permits secure browser-based edits of YAML configurations without needing terminal access.
- **SSO Gate on Editor**: While the primary Home Assistant dashboard (`home.vmd1.homelab`) uses its internal login system, the File Browser management dashboard (`edit-home.vmd1.homelab`) is gated behind Authentik.

## Dependencies

- **Local Discovery Network**: Requires binding directly to host network interface card on home node.
- **Authentik**: Requires `authentik-auth` middleware inside the `authentik` namespace to protect the config file editor route.

## Services & Routers

- **Kubernetes Services**:
  - `home-assistant` (ClusterIP, port `8123` routing to Home Assistant).
  - `home-assistant-filebrowser` (ClusterIP, port `80` routing to File Browser port `8082`).
- **Ingress Routes**:
  - `home.vmd1.homelab` routing to `home-assistant` on port `8123` (websecure).
  - `edit-home.vmd1.homelab` routing to `home-assistant-filebrowser` on port `80` (websecure), gated by Authentik middleware.

## Storage

- **PVC**: `home-assistant-pvc`
  - **Storage Class**: `longhorn-single-replica` (Longhorn replicated volume pinned locally).
  - **Size**: `10Gi`
  - **Mount Point**: Mounted to `/config` in both the `home-assistant` and the `filebrowser` sidecar containers.
  - **Data Persistence**: Holds all configuration state, integration caches, sqlite database history, and the File Browser database.

## Constraints & Scheduling

- **Deployment Strategy**: Enforces `Recreate` deployment strategy. This ensures that only a single instance of the Home Assistant pod runs at any time, preventing multi-pod writes/locks on the single-replica block volume.
- **Node Selectors**: Bound to `region: uk-home` nodes (`hades-01`) to reside on the physical home LAN interface for IoT device polling.
- **Network Capabilities**: Grants container permissions `NET_ADMIN` and `NET_RAW` to allow network utility access.
- **Resource Constraints**:
  - Request: `200m` CPU, `512Mi` RAM.
  - Limit: `1Gi` RAM (no CPU limit specified to allow quick startup spikes).

## Configs & Credentials

- Configurations are stored directly inside files on the persistent volume `/config` (e.g., `configuration.yaml`).
- Configured with Timezone `TZ: Europe/London`.
