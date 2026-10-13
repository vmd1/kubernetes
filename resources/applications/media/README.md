# Media Stack (Jellyfin, Seerr, Download Agent)

This directory manages the homelab media stack. It aggregates media ingestion (`download-agent`), request management (`seerr`), and streaming playback (`jellyfin`).

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [00-namespace-and-storage.yaml](00-namespace-and-storage.yaml) | Declares the namespace `media`. |
| [jellyfin.yaml](jellyfin.yaml) | Deploys Jellyfin via a K3s HelmChart CRD, defining config paths, resources, and dotnet runtime properties. |
| [jellyfin-ingressroute.yaml](jellyfin-ingressroute.yaml) | Traefik `IngressRoute` configuration for public media access. |
| [seerr.yaml](seerr.yaml) | Deploys Overseerr (`seerr`) via an OCI-sourced HelmChart CRD, managing media request pipelines. |
| [seerr-ingressroute.yaml](seerr-ingressroute.yaml) | Traefik `IngressRoute` configuration for request management endpoints. |
| [download-agent.yaml](download-agent.yaml) | Deployment, Service, and IngressRoute resources for a custom download service. |

## Design Decisions

- **Node Co-location**: All components (`jellyfin`, `seerr`, and `download-agent`) are pinned to node `hades-01` via `nodeSelector`. This allows mounting a common local storage host path (`/mnt/huge/media`) without network overhead or latency.
- **Resource Tuning**: Dotnet garbage collection (`DOTNET_GCDynamicAdaptationMode=1`) and Node.js garbage collection optimizations (`MALLOC_TRIM_THRESHOLD_=100000`) are applied to minimize inactive memory consumption.
- **Low Idle Overhead**: Download Agent is configured with an explicit low CPU request (`30m`) so Kubernetes doesn't reserve excessive headroom on `hades-01` at rest.
- **Download Agent and Seerr are switched off**: neither is in use any more. `download-agent` has `replicas: 0` in [download-agent.yaml](download-agent.yaml), and the Seerr StatefulSet was scaled to 0 by hand (the chart has no replica setting; it persists unless the Helm chart is re-applied). Their manifests, ingress routes and volumes are kept so they can be brought back. The Seerr Authelia client was removed; re-add it if Seerr returns. Set `replicas: 1` (and scale the StatefulSet up) to restore.
- **SSO**: Jellyfin signs in through Authelia using the SSO Authentication plugin (see [Jellyfin SSO](#jellyfin-sso)). The download manager UI (when running) is gated by oauth2-proxy + Authelia (`oauth2-proxy-kmnet-uk`).

## Dependencies

- **oauth2-proxy**: oauth2-proxy namespace middleware `oauth2-proxy-kmnet-uk` is required to protect the `download-agent` UI route.
- **Private Image Registry**: The `download-agent` uses an image pull secret `registry-kmnet-creds` to retrieve the container from the local registry.

## Services & Routers

- **Services**:
  - `jellyfin` (ClusterIP: `8096`).
  - `seerr` (ClusterIP: `80` targeting port `5055`).
  - `download-agent` (ClusterIP: `5000`).
- **Ingress Routes**:
  - `jellyfin.vmd1.homelab` -> routes to `jellyfin` on port `8096`.
  - `seerr.vmd1.homelab` -> routes to `seerr` on port `80`.
  - `download.vmd1.homelab` -> routes to `download-agent` on port `5000` (gated by oauth2-proxy (Authelia)).

## Storage

- **Core Media Storage**: Direct host path mapping (`/mnt/huge/media`) is used by both `jellyfin` and `download-agent` to eliminate virtualization disk overhead when processing multi-gigabyte media streams.
- **Jellyfin Config Storage**: PVC mapping to `local-path` class (size `5Gi`) to keep server metadata, images, and user progress databases intact.
- **Overseerr Config Storage**: PVC `seerr-config` (size `2Gi`, StorageClass `longhorn-single-replica`) to persist requesting histories, caches, and sync configs.

## Constraints & Scheduling

- **Node Selectors**: Pinned to node `hades-01` via `kubernetes.io/hostname: hades-01`.
- **Resource Limits**:
  - **Jellyfin**: Request `250m` CPU, `512Mi` RAM. Limit `2` CPU, `4Gi` RAM.
  - **Seerr**: Request `100m` CPU, `256Mi` RAM. Limit `512Mi` RAM.
  - **Download-agent**: Request `30m` CPU. Limit `1.5` CPU.

## Configs & Credentials

- **Secret**: `registry-kmnet-creds` (image-pull secret for `registry.vmd1.homelab`, holds the credentials of the pull-only lldap account `k3s-registry-pull`, a member of `registry-pull`).
- Environmental configurations (`MALLOC_TRIM_THRESHOLD_`, `DOTNET_GCDynamicAdaptationMode`) are injected directly inside deployment charts.

## Jellyfin SSO

Jellyfin uses the SSO Authentication plugin (4.0.0.4, from the `https://raw.githubusercontent.com/9p4/jellyfin-plugin-sso/manifest-release/manifest.json` plugin repository) against the cluster-wide Authelia. The configuration is stored in the Jellyfin config volume, not in this repo:

- **Provider `authelia`** (`/config/plugins/configurations/SSO-Auth.xml`): issuer `https://identity.vmd1.homelab`, client ID `jellyfin` (registered in Authelia with `client_secret_post`), role claim `groups`, allowed roles `jellyfin` and `jellyfin_admin`, admin role `jellyfin_admin`, scheme override `https`, pushed authorization disabled. The client secret is in that file (plaintext counterpart: `jellyfin_oidc_client_secret` in the Authelia Secret).
- **Login button**: added through Dashboard > General > Branding (login disclaimer HTML plus a CSS line) with the Authelia logo; it links to `https://jellyfin.vmd1.homelab/sso/OID/start/authelia`.
- **LDAP removed**: the LDAP-Auth plugin is disabled. Existing users created through LDAP keep their accounts; they sign in through Authelia, which matches by username. A local administrator (`vivaan_local`) remains as a fallback. Accounts that must use a password (for example shared TV devices) need a local password set under Dashboard > Users.
- **Changing config**: edit the plugin's configuration and restart Jellyfin; the plugin reads it at startup.
