# Uptime Kuma

Uptime Kuma is a self-hosted monitoring tool that monitors service availability over HTTP/HTTPS, TCP, Ping, DNS, and other protocols.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines `longhorn-single-replica` StorageClass override, PVC, Deployment running `louislam/uptime-kuma:2`, Service, and Traefik `IngressRoute` configuration. |

## Design Decisions

- **Dedicated Storage Class**: Declares a custom StorageClass `longhorn-single-replica` pointing to Longhorn with replica factor of `1` to bypass default multi-replica replication. This keeps disk IO footprint low for simple sqlite operations.
- **Node Co-Location**: Pinned to home node (`hades-01` in `region: uk-home`) to monitor local devices and home server availability reliably.
- **Public status vs gated host**: `up.vmd1.homelab`, `up.vmd1.homelab`, `up.vmd1.homelab` and `up.vmd1.homelab` stay public. `status.vmd1.homelab` is behind the `oauth2-proxy-kmnet-uk` middleware (Authelia) as its own route. Uptime Kuma has no OIDC support, so this is an extra gate in front of its own login.
- **Tailnet only**: the route has the `tailnet-only` middleware first ([proxy/traefik](../../proxy/traefik/README.md)), so it is reachable only with Tailscale on; everyone else gets the branded 403. Applies to `status.vmd1.homelab` only; the public `up.*` status page is unchanged. Monitors that fetch a tailnet-only URL from inside the cluster arrive from a node IP and see the 403.
- **Multiple Domain Ingress**: Exposes the status page on multiple domains (`up.vmd1.homelab`, `up.vmd1.homelab`, `up.vmd1.homelab`, `up.vmd1.homelab`, `status.vmd1.homelab`) via Traefik to allow public checking of homelab health.

## Dependencies

- **Storage Class**: Longhorn driver (`driver.longhorn.io`).

## Services & Routers

- **Kubernetes Service**: `uptime-kuma` (ClusterIP, port `80` mapping to container port `3001`).
- **Ingress Route**:
  - Exposes the dashboard and status pages publicly on `up.vmd1.homelab`, `up.vmd1.homelab`, `up.vmd1.homelab` and `up.vmd1.homelab`.
  - A separate route for `status.vmd1.homelab` adds the `oauth2-proxy-kmnet-uk` forward-auth middleware.

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
