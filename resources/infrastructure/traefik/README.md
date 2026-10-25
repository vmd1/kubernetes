# Traefik Ingress Helpers (`resources/infrastructure/traefik/`)

This folder holds the **Traefik custom resources** that sit on top of the Traefik controller: shared middlewares (rate limiting, security headers, compression), TLS options, the admin dashboard route, and the `uk-home` LoadBalancer service. The Traefik controller itself (HelmChart, DaemonSet, host network) is deployed from [operators/traefik/](../../operators/traefik/README.md).

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Services & Routers](#services--routers)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [dashboard.yaml](dashboard.yaml) | `IngressRoute` exposing the Traefik admin dashboard at `traefik.vmd1.homelab` (gated by oauth2-proxy (Authelia)) plus a `redirectRegex` middleware (`traefik-dashboard-redirect`) that sends `/` to `/dashboard/`. |
| [compress.yaml](compress.yaml) | `Middleware` `compress` enabling Gzip/Brotli response compression. |
| [security-headers.yaml](security-headers.yaml) | `Middleware` `security-headers` setting HSTS (preload, includeSubdomains), nosniff, `X-Frame-Options: DENY`, `referrer-policy: same-origin`, a restrictive `Permissions-Policy` (payment/usb/serial/bluetooth/interest-cohort only), `X-XSS-Protection: 0` and `X-Permitted-Cross-Domain-Policies: none`. |
| [rate-limit.yaml](rate-limit.yaml) | `Middleware` `rate-limit` (`average: 300`, `burst: 150` requests/second) and the stricter `rate-limit-auth` (`average: 30`, `burst: 60`) used by `identity.vmd1.homelab` and the `secure.<domain>/oauth2/` routes. |
| [tls-option.yaml](tls-option.yaml) | `TLSOption` `default`: minimum TLS 1.2 with ECDHE+AEAD cipher suites only and X25519/P-256/P-384 curves, cluster-wide. `sniStrict` stays `false` so bare-IP clients can still be shown the direct-IP page. |
| [geo-country.yaml](geo-country.yaml) | `Middleware` `geo-country` (plugin `vmd1geo`): makes the `CF-IPCountry` header trustworthy. Cloudflare requests keep their validated country; direct requests get a GeoLite2-Country lookup in Cloudflare's format (`XX` when unknown) and `X-Vmd1-Geo-Source` says which. **Not attached to any entrypoint yet** (separate change). |
| [../../edge/error-pages/error-pages.yaml](../../edge/error-pages/error-pages.yaml) (edge layer) | Branded error pages: `DaemonSet` `error-pages` (nginx-unprivileged on every node, pages fetched at pod start from a pinned commit of [vmd1/error-pages](https://github.com/vmd1/error-pages)), `Service` `error-pages`, `Middleware` `error-pages` (replaces Traefik-generated 429/502/503/504), and two lowest-priority catch-all `IngressRoute`s (`catchall-direct-ip`, `catchall-not-found`). |
| [cloudflare-only.yaml](cloudflare-only.yaml) | `IngressRoute` `vmd1-dev-cloudflare-only` (priority 900000): any `vmd1.homelab` / `*.vmd1.homelab` request whose TCP peer is not a Cloudflare range (or loopback, pod/service CIDRs, tailnet) is answered with the generic 404 from `error-pages`. |
| [trace.yaml](trace.yaml) | `Middleware` `vmd1-trace` (config for the `vmd1trace` plugin: node name → region map) and `IngressRoute` `vmd1-trace` serving `/.vmd1/trace` on every domain. |
| [lb-uk-home.yaml](lb-uk-home.yaml) | `LoadBalancer` Service `traefik-uk-home-lb` (IP `192.168.12.20` via Kube-VIP) exposing ports 80/443 on the home network. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |

## Design Decisions

- **Reusable Middleware Chain**: The `rate-limit`, `compress`, and `security-headers` middlewares are attached to most public `IngressRoute`s across the cluster (e.g. Longhorn UI, Grafana, dashboard).
- **Dashboard Behind SSO**: `traefik.vmd1.homelab` routes to `api@internal` and is protected by the `oauth2-proxy-kmnet-uk` middleware plus the standard chain.
- **Home Network LB**: `traefik-uk-home-lb` uses `loadBalancerClass: kube-vip.io/kube-vip-class` with `externalTrafficPolicy: Local` to preserve client source IPs and expose the ingress on the `192.168.12.0/24` LAN.

- **Connection Trace on Every Domain**: `Path(`/.vmd1/trace`)` with no `Host()` and priority `1000000` beats all site routes. Browsers (Accept: text/html) get an HTML page in the same design as the error pages (including a dotted world map with an animated path from the visitor's `CF-IPCountry` to the serving region; no JavaScript, no external requests), everything else gets plain `key=value` text; `?format=text|html|json` forces a format. It is answered by the `vmd1trace` local plugin (served from `noop@internal`, nothing is proxied), which reports `h`, `ip`, `visit_scheme`, `uag`, `resp-reg`, `http`, `req-reg`, `tls`, `sni` and `node-name` as `key=value` lines. TLS/HTTP version and SNI are the ones seen by Traefik, so behind Cloudflare they describe the Cloudflare→origin hop. `req-reg` comes from `CF-IPCountry` and is only believed when the TCP peer is a Cloudflare address (built-in list, same as the entrypoints' `trustedIPs`; optional middleware config key `cloudflareCIDRs` overrides it), otherwise it is `unknown`: any client can send that header to a node directly (`curl -H 'CF-IPCountry: KP'` used to be believed). A node missing from the `regions` map reports `resp-reg=unknown`.

- **Branded Error Pages**: the `error-pages` `errors` middleware is attached to the whole `websecure` entrypoint (controller HelmChart argument), and only covers statuses Traefik generates itself (429 from `rate-limit`, 502/503/504 from the proxy) so apps keep their own 4xx/500 bodies (JSON APIs, Matrix, registry). Traefik's built-in 404 for unmatched requests bypasses entrypoint middlewares, so two catch-all routers handle it: `catchall-direct-ip` (priority 2; Host is a bare IPv4/IPv6 address) returns `404` with the "Direct IP access forbidden" page, and `catchall-not-found` (priority 1) returns `404` with the normal 404 page for everything else, including unknown domains. Each page's footer has a "Click to view IP" toggle (`<details>`, no JavaScript); nginx fills in the visitor IP with SSI from the first `X-Forwarded-For` entry (IP characters only, `unknown` if absent). To roll out new page content, bump `ERROR_PAGES_REF` (a commit SHA of vmd1/error-pages) in `error-pages.yaml`.
- **Country for Every Request**: the `vmd1geo` plugin (HelmChart values) is a pure-stdlib GeoLite2-Country reader (no mmap or dependencies, because Traefik's Yaegi interpreter cannot use them; checked against MaxMind's reference library on ~7.8k addresses incl. IPv6, 0 mismatches). The shared state (database, per-IP cache, file watcher) is a process-wide singleton because Traefik builds one middleware instance per router. A direct request's `CF-IPCountry` is always overwritten from the lookup (a forged value never survives), a Cloudflare request's is validated; unknown is `XX`, as Cloudflare does. The database file is re-read when it changes. It fails open. The trace page uses `X-Vmd1-Geo-Source` and shows `req-reg-src`.
- **Rate-limit Source**: `rateLimit` buckets requests by the connecting address by default, which for Cloudflare-proxied hosts is the Cloudflare edge IP (all users behind one PoP share a bucket). Using `sourceCriterion.ipStrategy.excludedIPs` to recover the client IP was tested on the cluster and puts every direct (non-Cloudflare) client into one shared bucket, so it is not used. A proper fix needs Cloudflare and direct traffic split onto separate routers or entrypoints.
- **Cloudflare-only Origin for vmd1.homelab**: every HTTP-serving vmd1.homelab name is proxied by Cloudflare, so `cloudflare-only.yaml` drops direct-to-node requests that carry a vmd1.homelab `Host`. `ClientIP()` matches the TCP peer (never `X-Forwarded-For`/`CF-Connecting-IP`), so it cannot be spoofed. Priority 900000 is below `/.vmd1/trace` (1000000) and above every site route. LAN ranges are intentionally not allowed (split-horizon DNS for vmd1.homelab would need `192.168.0.0/16` added). The Cloudflare list must match the entrypoint `trustedIPs` in the Traefik HelmChart. `/health` is exempt because PowerDNS probes `https://vmd1.homelab/health` on every ingress IP (`ifurlup`) from the nodes' own public addresses. Other domains (vmd1.homelab, vmd1.homelab, vmd1.homelab) are not restricted. To verify after a rollout: `curl -sk --resolve vault.vmd1.homelab:443:<node-ip> https://vault.vmd1.homelab/` must return 404 while `https://vault.vmd1.homelab/` still works.

## Dependencies

- **Traefik controller** in [operators/traefik](../../operators/traefik/README.md) (provides the CRDs and `api@internal`).
- **Kube-VIP** in [operators/kube-vip](../../operators/kube-vip/README.md) (allocates `192.168.12.20`).
- **oauth2-proxy** (`oauth2-proxy-kmnet-uk` middleware, for the dashboard SSO gate).

## Services & Routers

- **Kubernetes Service**: `traefik-uk-home-lb` (LoadBalancer, `192.168.12.20:80`/`:443`).
- **Ingress Route**: `traefik.vmd1.homelab` → `api@internal` (dashboard).
- **Catch-all routes**: `catchall-direct-ip` and `catchall-not-found` (websecure, lowest priority) → `error-pages` (nginx, nativeLB).

## Related

- [../../operators/traefik/README.md](../../operators/traefik/README.md) — the Traefik controller chart.
- [../../operators/kube-vip/README.md](../../operators/kube-vip/README.md) — the load balancer providing `192.168.12.20`.
- [../README.md](../README.md) — the infrastructure layer this folder belongs to.
