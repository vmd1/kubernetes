# Monitoring Agents (`edge/monitoring-agents/`)

| File | Description |
| :--- | :--- |
| [agents.yaml](agents.yaml) | `node-exporter` DaemonSet and Service (port 9101); `promtail` ServiceAccount, ClusterRole/Binding, `promtail-config` ConfigMap and DaemonSet. |

These were part of [../../observability/monitoring/manifest.yaml](../../observability/monitoring/manifest.yaml). They moved here because they run on every node; see [../README.md](../README.md). Loki, Prometheus and Grafana stay in `observability/monitoring`.
