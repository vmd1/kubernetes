# Monitoring Stack

The monitoring namespace deploys log aggregation (`loki` + `promtail`), metrics collection (`prometheus` + `node-exporter` + `kube-state-metrics`), and visualization (`grafana`).

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Comprehensive deployment manifest containing Loki (and configmaps/volumes), Promtail DaemonSet (for Traefik namespace log forwarding), Prometheus (metrics server), Node Exporter, Grafana Server (with CNPG backend connection details), services, and IngressRoutes. |
| [kube-state-metrics.yaml](kube-state-metrics.yaml) | Configuration deployment file setting up the Kube-State-Metrics broker agent to expose low-level cluster object metrics to Prometheus. |
| [dashboards.yaml](dashboards.yaml) | Pre-configured dashboard payloads to load default views into Grafana (Node details, Longhorn, Postgres CNPG, Prometheus internals, Traefik traffic). |
| [traefik-loki.json](traefik-loki.json) | Grafana dashboard config matching Loki structured logs emitted by Traefik. |
| [example-not-working-traefik-dash.json](example-not-working-traefik-dash.json) | Backup archive of a non-functional dashboard version preserved for debugging purposes. |
| [download-dashboards.ps1](download-dashboards.ps1) | PowerShell script used to fetch the latest production dashboards from public Grafana APIs. |
| [download-ksm.ps1](download-ksm.ps1) | PowerShell script to download the target Kube-State-Metrics deployment templates. |

## Design Decisions

- **PostgreSQL-backed Grafana**: Grafana is configured to use the high-availability CloudNativePG PostgreSQL database cluster instead of sqlite. This ensures dashboard edits and user profiles persist across restarts.
- **Log Retention & Scrape Filtering**:
  - Loki retention is configured to `720h` (30 days) to bound disk growth.
  - Prometheus `scrape_interval` and `evaluation_interval` are set to `30s` to minimize API server CPU load on `hades-01`.
  - Promtail is deployed as a DaemonSet but relabeled to only ingest and forward logs from the `traefik` namespace. This keeps the Loki log database small and performant.
- **Scrape Targets**: Prometheus scrapes metrics from Node Exporter, Kubelet, CoreDNS, Cert-Manager, Longhorn, CNPG, Redis, Etcd, and local Kubernetes service pods.

## Dependencies

- **Database**: CloudNativePG PostgreSQL cluster (`pg-cluster-rw.cnpg.svc.cluster.local:5432`) is required by Grafana.
- **Host mount access**: Promtail and Node Exporter require access to host directories (`/var/log`, `/proc`, `/sys`, and `/`) to extract metrics and logs.

## Services & Routers

- **Kubernetes Services**:
  - `loki` (ClusterIP, port `3100`).
  - `prometheus` (ClusterIP, port `9090`).
  - `grafana` (ClusterIP, port `80` mapping to container port `3000`).
  - `node-exporter` (Headless/None, port `9101`).
- **Ingress Routes**:
  - `grafana.vmd1.homelab` on `websecure` entrypoint routing to service `grafana` on port `80`.

## Storage

- **Loki storage**: PVC `loki-pvc` (size `10Gi`, class `longhorn-single-replica`) mounted at `/loki`. Holds active and compacted chunks.
- **Prometheus Storage**: PVC `prometheus-pvc` (size `30Gi`, class `longhorn-single-replica`) mounted at `/prometheus` to store long-term time-series databases.

## Constraints & Scheduling

- **Loki/Prometheus/Grafana scheduling**: All three deployments are hard-pinned via `nodeSelector` to `topology.kubernetes.io/zone: uk-home` (i.e. `hades-01` or `hades-02` only), plus a soft `preferredDuringSchedulingIgnoredDuringExecution` node affinity toward `hades-02` (weight 100) to keep memory pressure off `hades-01` (control-plane/etcd/db/storage). The zone pin is a hard requirement; the `hades-02` preference is not — the scheduler can still place them on `hades-01` if `hades-02` lacks capacity. PVCs are `longhorn-single-replica` (network-attached via Longhorn), so relocation doesn't require any data migration.
- **Tolerations**: Promtail DaemonSet tolerates all node taints (`NoSchedule`, `NoExecute`) to run logs forwarding on every node in the cluster.
- **Resource Constraints**:
  - **Loki**: Request `10m` CPU, `128Mi` RAM. Limit `500m` CPU, `512Mi` RAM.
  - **Prometheus**: Request `100m` CPU, `512Mi` RAM. Limit `1500m` CPU, `3Gi` RAM.
  - **Grafana**: Request `50m` CPU, `128Mi` RAM. Limit `500m` CPU, `512Mi` RAM.
  - **Promtail**: Request `10m` CPU, `32Mi` RAM. Limit `100m` CPU, `80Mi` RAM.

## Configs & Credentials

- **ConfigMaps**:
  - `loki-config`: Defines server configurations and compactor retention parameters.
  - `promtail-config`: Specifies the relabeling and discovery rules targeting only the `traefik` namespace.
  - `prometheus-config`: Dictates scraping jobs, metrics paths, and evaluation metrics.
- **Secret**: `grafana-db-secret` (SOPS-encrypted in [secrets.sops.yaml](secrets.sops.yaml), stores Postgres credentials).
