# Uptime Kuma

Uptime Kuma is a self-hosted monitoring tool that monitors service availability over HTTP/HTTPS, TCP, Ping, DNS, and other protocols.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines the Namespace `uptime-kuma`, the `longhorn-single-replica` StorageClass override, PVC, Deployment running `louislam/uptime-kuma:2`, Service, and Traefik `IngressRoute` configuration. |
| [sa.ps1](sa.ps1) | PowerShell script to configure a service account and long-lived auth token (`uptime-kuma-monitor`) to allow Uptime Kuma to query cluster APIs for Kubernetes pod/node status. |

## Design Decisions

- **Dedicated Storage Class**: Declares a custom StorageClass `longhorn-single-replica` pointing to Longhorn with replica factor of `1` to bypass default multi-replica replication. This keeps disk IO footprint low for simple sqlite operations.
- **Node Co-Location**: Pinned to home node (`hades-01` in `region: uk-home`) to monitor local devices and home server availability reliably.
- **Multiple Domain Ingress**: Exposes the status page on multiple domains (`up.vmd1.homelab`, `up.vmd1.homelab`, `up.vmd1.homelab`, `up.vmd1.homelab`, `status.vmd1.homelab`) via Traefik to allow public checking of homelab health.

## Dependencies

- **Storage Class**: Longhorn driver (`driver.longhorn.io`).
- **Cluster APIs**: Uses token created by `sa.ps1` for advanced K8s health checks.

## Services & Routers

- **Kubernetes Service**: `uptime-kuma` (ClusterIP, port `80` mapping to container port `3001`).
- **Ingress Route**:
  - Exposes the dashboard and status pages on domains `up.vmd1.homelab`, `up.vmd1.homelab`, `up.vmd1.homelab`, `up.vmd1.homelab`, and `status.vmd1.homelab`.

## Storage

- **PVC**: `uptime-kuma-pvc`
  - **Storage Class**: `longhorn-single-replica`
  - **Size**: `2Gi`
  - **Mount Point**: Mounted to `/app/data`.
  - **Data Persistence**: Stores the monitoring configuration, ping history, and server settings in a sqlite database (`kuma.db`).

## Constraints & Scheduling

- **Deployment Strategy**: Set to `Recreate` deployment strategy. This ensures only a single running replica binds to the backing volume.
- **Scheduling**: Pinned via `nodeSelector` to `region: uk-home`.
- **Resource Constraints**:
  - Request: `50m` CPU, `128Mi` RAM.
  - Limit: `500m` CPU, `512Mi` RAM.
- **Memory tuning**: Configured with `MALLOC_TRIM_THRESHOLD_=100000` to lower Node.js memory overhead.

## Configs & Credentials

- Custom service accounts are configured via the `sa.ps1` helper script.
