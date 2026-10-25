# Error Pages (`edge/error-pages/`)

| File | Description |
| :--- | :--- |
| [error-pages.yaml](error-pages.yaml) | ConfigMap `error-pages-nginx`, DaemonSet `error-pages` (every node), Service `error-pages`, Middleware `error-pages` (attached to the `websecure` entrypoint by the Traefik HelmChart args) and the `catchall-direct-ip` / `catchall-not-found` IngressRoutes. |

Moved here from `infrastructure/traefik/` because the DaemonSet runs on the ingress nodes; see [../README.md](../README.md). The rest of the Traefik helpers are in [../../infrastructure/traefik/](../../infrastructure/traefik/README.md).
