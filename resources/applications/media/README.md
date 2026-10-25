# Media Stack (Jellyfin)

This directory manages Jellyfin, the homelab streaming server. Seerr (request management) and the download agent were removed; they can be restored from git history.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [jellyfin.yaml](jellyfin.yaml) | Deploys Jellyfin via a K3s HelmChart CRD, defining config paths, resources, and dotnet runtime properties. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` for `jellyfin.vmd1.homelab`. |

## Design Decisions

- **Node Co-location**: Jellyfin is pinned to node `hades-01` via `nodeSelector` so it can mount the local media host path (`/mnt/huge/media`) without network overhead.
- **Resource Tuning**: Dotnet garbage collection (`DOTNET_GCDynamicAdaptationMode=1`, `MALLOC_TRIM_THRESHOLD_=100000`) is tuned to minimize inactive memory consumption.
- **SSO**: Jellyfin signs in through Authelia using the SSO Authentication plugin (see [Jellyfin SSO](#jellyfin-sso)).
- **Removed workloads**: Seerr (`seerr.vmd1.homelab`) and the download agent (`download.vmd1.homelab`) are gone, along with the `registry-kmnet-creds` pull secret. The `seerr-config` PVC is not deleted by Flux and must be removed by hand if the data is no longer wanted.

## Services & Routers

- **Services**: `jellyfin` (ClusterIP: `8096`).
- **Ingress Routes**: `jellyfin.vmd1.homelab` -> `jellyfin` on port `8096`.

## Storage

- **Core Media Storage**: direct host path mapping (`/mnt/huge/media`) to eliminate virtualization disk overhead when streaming multi-gigabyte media.
- **Jellyfin Config Storage**: PVC on the `local-path` class (size `5Gi`) holding server metadata, images, and user progress databases.

## Constraints & Scheduling

- **Node Selectors**: pinned to node `hades-01` via `kubernetes.io/hostname: hades-01`.
- **Resource Limits**: request `250m` CPU, `512Mi` RAM; limit `2` CPU, `4Gi` RAM.

## Jellyfin SSO

Jellyfin uses the SSO Authentication plugin (4.0.0.4, from the `https://raw.githubusercontent.com/9p4/jellyfin-plugin-sso/manifest-release/manifest.json` plugin repository) against the cluster-wide Authelia. The configuration is stored in the Jellyfin config volume, not in this repo:

- **Provider `authelia`** (`/config/plugins/configurations/SSO-Auth.xml`): issuer `https://identity.vmd1.homelab`, client ID `jellyfin` (registered in Authelia with `client_secret_post`), role claim `groups`, allowed roles `jellyfin` and `jellyfin_admin`, admin role `jellyfin_admin`, scheme override `https`, pushed authorization disabled. The client secret is in that file (plaintext counterpart: `jellyfin_oidc_client_secret` in the Authelia Secret).
- **Login button**: added through Dashboard > General > Branding (login disclaimer HTML plus a CSS line) with the Authelia logo; it links to `https://jellyfin.vmd1.homelab/sso/OID/start/authelia`.
- **LDAP removed**: the LDAP-Auth plugin is disabled. Existing users created through LDAP keep their accounts; they sign in through Authelia, which matches by username. A local administrator (`vivaan_local`) remains as a fallback. Accounts that must use a password (for example shared TV devices) need a local password set under Dashboard > Users.
- **Changing config**: edit the plugin's configuration and restart Jellyfin; the plugin reads it at startup.
