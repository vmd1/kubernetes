# Edge Web Services (vmd1-dev)

This folder hosts the central personal web/developer portal (`vmd1.homelab`) and associated domains. It runs as a DaemonSet across the cluster's ingress edge nodes.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines the Namespace `vmd1-web`, DaemonSet (`edge-services`), Service, ServersTransport timeouts configuration, and Traefik `IngressRoute`. |

## Design Decisions

- **DaemonSet on Edge Nodes**: Runs as a DaemonSet to ensure the web service is co-located on every available ingress node.
- **Traffic Optimization**: Service configuration specifies `trafficDistribution: PreferSameZone` and `internalTrafficPolicy: Cluster`. The IngressRoute uses `nativeLB: true` to force Traefik to route requests via the Service ClusterIP instead of direct Pod IPs, allowing `kube-proxy` to enforce zone-aware topology routing and eliminate cross-region latency.
- **Custom Transport Parameters**: Implements a Traefik `ServersTransport` resource (`edge-transport`) specifying dial timeouts (`10s`) and idle timeouts (`30s`) to manage connections efficiently over hybrid cloud links.
- **Path Routing Split**: Splits routing rules for `vmd1.homelab` to allow direct path checks on wellness indicators (like `/.well-known` and `/health`) while enforcing custom middleware rules on others.

## Dependencies

- **Traefik Ingress**: Resolves the custom `IngressRoute` and `ServersTransport` resources.

## Services & Routers

- **Kubernetes Service**: `vmd1-dev` (ClusterIP, port `80`).
- **Ingress Routes**:
  - `vmd1.homelab` -> routes to service `vmd1-dev` port `80` (utilizing `edge-transport`).
  - Mapped auxiliary domains `vmd1.homelab`, `gcses.vmd1.homelab`, `gcse-results.vmd1.homelab`, `flix4all.cc`, and `finny.vmd1.homelab` protected by `security-headers` middleware.

## Storage

No persistent volume claims are used. The web application is stateless and is packaged inside the `ghcr.io/vmd1/vmd1.homelab:edge` container image.

## Constraints & Scheduling

- **Update Strategy**: RollingUpdate (`maxUnavailable: 4`) ensuring maximum service uptime.
- **Tolerations**: Exists (runs on all nodes).
- **Resource Constraints**:
  - Request: `100m` CPU, `128Mi` RAM.
  - Limit: `500m` CPU, `256Mi` RAM.
- **Probes**: A readiness probe polls HTTP path `/health` on port `80` every 5 seconds.

## Configs & Credentials

This deployment does not rely on configmaps or local secrets.
