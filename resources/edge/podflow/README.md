# podflow (`edge/podflow/`)

| File | Description |
| :--- | :--- |
| [podflow.yaml](podflow.yaml) | ServiceAccount, ClusterRole/Binding and the host-network `podflow` DaemonSet (every node, `TAILNET=true` for Tailscale exit-node attribution). |

Design, metrics and dashboards are documented with the monitoring stack: [../../applications/monitoring/README.md](../../applications/monitoring/README.md) and [PODFLOW-PLAN.md](../../applications/monitoring/PODFLOW-PLAN.md). Source: [controllers/podflow/](../../../../controllers/podflow/).
