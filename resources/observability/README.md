# Observability (`resources/observability/`)

Metrics, logs, uptime, alerts and cluster views. The node agents (node-exporter, promtail) and podflow are in [../edge/](../edge/README.md) because they run on the ingress nodes. Applied by the `observability` Flux Kustomization ([../../clusters/vmd1/observability.yaml](../../clusters/vmd1/observability.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [monitoring/](monitoring/README.md) | Loki + Promtail logs, Prometheus + Node Exporter + Kube State Metrics, and Grafana. |
| [uptime-kuma/](uptime-kuma/README.md) | Self-hosted uptime and latency monitoring. |
| [ntfy/](ntfy/README.md) | HTTP pub-sub push notification service with SMTP ingress. |
| [headlamp/](headlamp/README.md) | Kubernetes web UI dashboard with cluster-admin service account access. |
| [homelable/](homelable/README.md) | Homelab diagram app with live status monitoring and read-only Kubernetes import (`lab.vmd1.homelab`), signing in through Authelia (OIDC). |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
