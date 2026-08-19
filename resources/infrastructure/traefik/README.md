# Traefik Ingress Helpers (`resources/infrastructure/traefik/`)

This folder holds the **Traefik custom resources** that sit on top of the Traefik controller: shared middlewares (rate limiting, security headers, compression), TLS options, the admin dashboard route, and the `uk-home` LoadBalancer service. The Traefik controller itself (HelmChart, DaemonSet, host network) is deployed from [crds-and-operators/traefik/](../../crds-and-operators/traefik/README.md).

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Services & Routers](#services--routers)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [dashboard.yaml](dashboard.yaml) | `IngressRoute` exposing the Traefik admin dashboard at `traefik.vmd1.homelab` (gated by Authentik) plus a `redirectRegex` middleware (`traefik-dashboard-redirect`) that sends `/` to `/dashboard/`. |
| [compress.yaml](compress.yaml) | `Middleware` `compress` enabling Gzip/Brotli response compression. |
| [security-headers.yaml](security-headers.yaml) | `Middleware` `security-headers` setting HSTS (preload, includeSubdomains), XSS filter, nosniff, frame deny, and `referrer-policy: same-origin`. |
| [rate-limit.yaml](rate-limit.yaml) | `Middleware` `rate-limit` with `average: 300`, `burst: 150` requests/second. |
| [tls-option.yaml](tls-option.yaml) | `TLSOption` `default` enforcing a minimum TLS version of 1.2 cluster-wide. |
| [lb-uk-home.yaml](lb-uk-home.yaml) | `LoadBalancer` Service `traefik-uk-home-lb` (IP `192.168.12.20` via Kube-VIP) exposing ports 80/443 on the home network. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |

## Design Decisions

- **Reusable Middleware Chain**: The `rate-limit`, `compress`, and `security-headers` middlewares are attached to most public `IngressRoute`s across the cluster (e.g. Longhorn UI, Grafana, dashboard).
- **Dashboard Behind SSO**: `traefik.vmd1.homelab` routes to `api@internal` and is protected by the `authentik-auth` middleware plus the standard chain.
- **Home Network LB**: `traefik-uk-home-lb` uses `loadBalancerClass: kube-vip.io/kube-vip-class` with `externalTrafficPolicy: Local` to preserve client source IPs and expose the ingress on the `192.168.12.0/24` LAN.

## Dependencies

- **Traefik controller** in [crds-and-operators/traefik](../../crds-and-operators/traefik/README.md) (provides the CRDs and `api@internal`).
- **Kube-VIP** in [crds-and-operators/kube-vip](../../crds-and-operators/kube-vip/README.md) (allocates `192.168.12.20`).
- **Authentik** (for the dashboard SSO gate).

## Services & Routers

- **Kubernetes Service**: `traefik-uk-home-lb` (LoadBalancer, `192.168.12.20:80`/`:443`).
- **Ingress Route**: `traefik.vmd1.homelab` → `api@internal` (dashboard).

## Related

- [../../crds-and-operators/traefik/README.md](../../crds-and-operators/traefik/README.md) — the Traefik controller chart.
- [../../crds-and-operators/kube-vip/README.md](../../crds-and-operators/kube-vip/README.md) — the load balancer providing `192.168.12.20`.
- [../README.md](../README.md) — the infrastructure layer this folder belongs to.
