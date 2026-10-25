# Edge (`resources/edge/`)

Everything Flux deploys and waits on that runs on the six 1 GB OCI ingress nodes, applied by the `edge` Flux Kustomization ([../../clusters/vmd1/edge.yaml](../../clusters/vmd1/edge.yaml)).

## Why a separate layer

Every layer uses `wait: true`, and a DaemonSet is only healthy when its pod on every node is ready. When a flaky ingress node goes NotReady, the layer holding that DaemonSet times out, and every layer that `dependsOn` it stops reconciling. `edge` depends on `operators` but nothing depends on `edge`, so a bad ingress node now only marks `edge` NotReady.

Traefik is not here: Flux applies only its `HelmChart` (in [../operators/traefik/](../operators/traefik/README.md)). k3s's helm-controller creates the DaemonSet, so Flux never waits on it.

## Contents

| Folder | Description |
| :--- | :--- |
| [edge-sites/](edge-sites/README.md) | Edge serving platform: `edge-sites` DaemonSet, edge-operator, shared `vmd1-web` Middlewares, EdgeSites. |
| [error-pages/](error-pages/README.md) | Branded error pages DaemonSet, its Middleware and the catch-all IngressRoutes. |
| [geoip-updater/](geoip-updater/README.md) | Keeps the GeoLite2 databases in `/var/lib/geoip` fresh on every node. |
| [monitoring-agents/](monitoring-agents/README.md) | `node-exporter` and `promtail` DaemonSets (the rest of monitoring is in [../applications/monitoring/](../applications/monitoring/README.md)). |
| [podflow/](podflow/README.md) | Per-pod network flow agent DaemonSet. |
| [powerdns/](powerdns/README.md) | GeoIP DNS DaemonSet on the ingress nodes and the powerdns-operator. |

## Related

- [../README.md](../README.md): layer order.
