# Proxy (`resources/proxy/`)

Traefik helpers shared by every route (the controller chart is in [../operators/traefik/](../operators/traefik/README.md)) and the home dynamic-DNS updater. Applied by the `proxy` Flux Kustomization ([../../clusters/vmd1/proxy.yaml](../../clusters/vmd1/proxy.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [traefik/](traefik/README.md) | Traefik middlewares (rate-limit, security-headers, compress, TLS options), dashboard route, and the `uk-home` LoadBalancer. (Controller chart lives in [operators/traefik](../operators/traefik/README.md).) |
| [cf-ddns/](cf-ddns/README.md) | CronJob updating the home gateway's Cloudflare A record with its dynamic public IP. |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
