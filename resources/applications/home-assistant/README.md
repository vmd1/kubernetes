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
- **SSO Gate on Editor**: The File Browser management dashboard (`edit-home.vmd1.homelab`) is gated behind oauth2-proxy (Authelia).
- **Sign-in through Authelia**: the dashboard (`home.vmd1.homelab`) uses the `hass-oidc-auth` custom component (see [Single Sign-On](#single-sign-on-authelia)). The old LLDAP command-line auth provider was removed.

## Dependencies

- **Local Discovery Network**: Requires binding directly to host network interface card on home node.
- **oauth2-proxy**: Requires `oauth2-proxy-kmnet-uk` middleware inside the `oauth2-proxy` namespace to protect the config file editor route.

## Services & Routers

- **Kubernetes Services**:
  - `home-assistant` (ClusterIP, port `8123` routing to Home Assistant).
  - `home-assistant-filebrowser` (ClusterIP, port `80` routing to File Browser port `8082`).
- **Ingress Routes**:
  - `home.vmd1.homelab` routing to `home-assistant` on port `8123` (websecure).
  - `edit-home.vmd1.homelab` routing to `home-assistant-filebrowser` on port `80` (websecure), gated by oauth2-proxy (Authelia) middleware.

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

## Single Sign-On (Authelia)

Home Assistant signs in through the cluster-wide Authelia using the [`hass-oidc-auth`](https://github.com/christiaangoossens/hass-oidc-auth) custom component (v1.2.1). Everything below lives on the `/config` volume, not in this repo:

- **Component**: installed manually into `/config/custom_components/auth_oidc` (from the release zip, not through HACS). Update it by replacing that folder and restarting.
- **`configuration.yaml`**: an `auth_oidc:` block with client `home-assistant` (confidential client; the secret is `oidc_client_secret` in `secrets.yaml`), discovery URL `https://identity.vmd1.homelab/.well-known/openid-configuration`, groups scope `groups`, username claim `preferred_username`, and roles `admin: homeassistant_admin` / `user: homeassistant_user` (users in neither group are refused). In Authelia the client uses `client_secret_post` with PKCE.
- **Auth providers kept**: `trusted_networks` for `192.168.1.0/24` and the built-in `homeassistant` login (a local backup login is also at `/?skip_oidc_redirect=true`). The LLDAP `command_line` provider and its script (`lldap-ha-auth.sh`) are no longer used; sessions that were created through it must sign in again.
- **Account linking**: `features.automatic_user_linking: true` links existing Home Assistant users to OIDC logins by username. It is meant to be temporary: once everyone has signed in once, set it to `false` and restart.
- Backups of the configuration before the change: `configuration.yaml.bak-oidc` and `secrets.yaml.bak-oidc` in `/config`.
