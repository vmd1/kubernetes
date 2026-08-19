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
- **SSO for Download UI**: The download manager UI is gated behind Authentik (`authentik-auth`), whereas Jellyfin relies on its native user credentials.

## Dependencies

- **Authentik**: Authentik namespace middleware `authentik-auth` is required to protect the `download-agent` UI route.
- **Private Image Registry**: The `download-agent` uses an image pull secret `registry-kmnet-creds` to retrieve the container from the local registry.

## Services & Routers

- **Services**:
  - `jellyfin` (ClusterIP: `8096`).
  - `seerr` (ClusterIP: `80` targeting port `5055`).
  - `download-agent` (ClusterIP: `5000`).
- **Ingress Routes**:
  - `jellyfin.vmd1.homelab` -> routes to `jellyfin` on port `8096`.
  - `seerr.vmd1.homelab` -> routes to `seerr` on port `80`.
  - `download.vmd1.homelab` -> routes to `download-agent` on port `5000` (gated by Authentik).

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

- **Secret**: `registry-kmnet-creds` (registry access tokens).
- Environmental configurations (`MALLOC_TRIM_THRESHOLD_`, `DOTNET_GCDynamicAdaptationMode`) are injected directly inside deployment charts.
