# Edge Sites (edge-services platform)

Deploys the CRD-driven edge serving platform: the `edge-operator`, and the stateless `DaemonSet/edge-sites` that serves every `EdgeSite` (static sites and Workers) from the ingress edge nodes. Source and design live in [`edge-services/`](../../../../edge-services/README.md). It replaced the old `vmd1-dev` DaemonSet (a single baked image of `vmd1.homelab`); `vmd1.homelab` is now the `vmd1-dev` EdgeSite.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [shared.yaml](shared.yaml) | `ServersTransport/edge-transport` and the `edge-retry` / `static-cache-headers` Middlewares that most apps' IngressRoutes reference. |
| [redirects.yaml](redirects.yaml) | `www.vmd1.homelab` -> `vmd1.homelab` permanent redirect (`Middleware/www-vmd1-dev-redirect` + `IngressRoute/vmd1-dev-www-redirect`). |
| [manifest.yaml](manifest.yaml) | `DaemonSet/edge-sites` (edge-agent + nginx + workerd, amd64 nodes, all taints tolerated, `emptyDir` content store, `edge-manifest` ConfigMap volume) and `Service/edge-sites` (`PreferSameZone`). |
| [operator-rbac.yaml](operator-rbac.yaml) | ServiceAccount, namespaced Role and RoleBinding for the operator (EdgeSites, Jobs, CronJobs, ConfigMaps, Secrets, Pods, DaemonSet patch, IngressRoutes). |
| [sites/](sites) | One `EdgeSite` manifest per hosted site (listed in `kustomization.yaml`); the serve config lives inline under `spec.serve`. See [`edge-services/SITE-SETUP.md`](../../../../edge-services/SITE-SETUP.md). |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted `Secret/edge-registry-creds` (registry login for the operator, Kaniko and the edge agents). |
| [operator-deployment.yaml](operator-deployment.yaml) | `Deployment/edge-operator` (1 replica, pinned to `uk-home`). |

## Design Decisions

- **No image pulls on update:** the runtime image is fixed. The operator publishes `ConfigMap/edge-manifest` (site name, registry repo, image digest); the in-pod **edge-agent** downloads only the changed site's layer from the in-cluster registry Service over HTTP (verified by digest), validates the new nginx config, atomically swaps it in and reloads nginx. No pod restart, no kubelet pull, no bundle image. A failed update keeps serving the previous generation; the operator routes new sites only after every Ready pod reports the new version on `:9100/status` (pods on a down node do not block it).
- **Operator-owned objects (not in git):** `ConfigMap/edge-manifest`, `ConfigMap/edge-bundle-state`, `IngressRoute/edge-sites`, `Secret/edge-worker-secrets`, per-site build Jobs and Worker `CronJob`s.
- **Fast path:** plain static sites (no `install`/`command`) are built by the operator itself (clone, validate, one layer, push to the registry); no Job runs. Sites with commands, and Workers, use a build Job.
- **Strict node isolation:** build Jobs are pinned to `topology.kubernetes.io/zone=uk-home` and `kubernetes.io/arch=amd64` (so currently `hades-02` only) and never tolerate the ingress taint; the operator asserts this before creating a Job.
- **amd64 only:** the DaemonSet excludes arm64 `hades-01`.
- **Registry:** everything uses `registry.vmd1.homelab` (token auth against lldap, see [registry](../../platform/registry/README.md)). Kaniko and the operator's fast path push `edge/site-<name>`; the edge agents pull from it. The URL is configured once, in the operator's env (`REGISTRY_HOST`, `REGISTRY_URL` in [operator-deployment.yaml](operator-deployment.yaml)), and reaches the edge pods through the `registry` field of `ConfigMap/edge-manifest`. Only the runtime image is pulled by the kubelet, from public ghcr.
- **Auth (`spec.auth`):** `auth: {}` gates the whole site and `auth: {paths: ["/admin"]}` only those prefixes. The operator adds the domain's `oauth2-proxy-<domain>` Authelia middleware (first, before the backend) plus `edge-no-store` (Cloudflare caches static file types regardless of auth, and a cache hit would skip the login); path rules get `priority: 10000`. Access needs the lldap group `Domain: <domain>`. Supported domains are those with an oauth2-proxy (`EDGE_AUTH_DOMAINS`, default `vmd1.homelab, vmd1.homelab, vmd1.homelab, vmd1.homelab`). An invalid auth block marks the site `Invalid` and **removes its route** (fail closed: it is never served ungated). Edits to `auth` apply within seconds, without a rebuild.
- **Tailnet only (`spec.tailnetOnly`):** `tailnetOnly: true` puts the `tailnet-only` middleware ([proxy/traefik](../../proxy/traefik/README.md)) first on every route of the site, including the public part of a path-gated site, so only clients on the tailnet get through and everyone else sees the branded 403 before any login. It uses the live spec (no rebuild), like `auth`, and a non-boolean value marks the site `Invalid` and unrouted. DNS needs nothing per site: tailnet clients are steered to the tailnet IPs by the PowerDNS shadow zones ([edge/powerdns](../powerdns/README.md)).
- **Hostnames/TLS:** hostnames must be covered by `cluster-wildcard-tls` and DNS (`dns/domains`). A hostname must not also be routed by another IngressRoute (Traefik picks by rule length, so a longer rule elsewhere would shadow the edge route).

## Dependencies

- `edgesite` CRD ([crds/edgesite](../../crds/edgesite/README.md)); Traefik CRDs and the `edge-retry`, `static-cache-headers` (vmd1-web), `compress` (traefik) middlewares and `edge-transport` ServersTransport.
- The `registry` and `docker-auth` apps (platform group), and images `ghcr.io/vmd1/edge-{operator,builder,runtime}` built by [`.github/workflows/edge-images.yaml`](../../../../.github/workflows/edge-images.yaml) (make the ghcr packages public).

## Services & Routers

- **Service:** `edge-sites` (ClusterIP, port `80`).
- **IngressRoute:** `edge-sites` (created by the operator): one `Host(...)` rule per served `EdgeSite` -> `edge-sites:80`.

## Storage

None persistent. Edge pods keep a node-local `emptyDir` cache (content-addressed, garbage collected to the current and previous generation); the operator keeps state in a ConfigMap and EdgeSite `.status`.

## Constraints & Scheduling

- DaemonSet: RollingUpdate `maxUnavailable: 2`, requests `10m/32Mi`, limits `200m/128Mi`.
- Edge pods: `emptyDir` `/srv/edge` capped at 2Gi, container limit `128Mi`.
- Operator: `uk-home`, requests `20m/64Mi`, limits `500m/320Mi`, `/tmp` emptyDir (1Gi) for fast-path clones; set `EDGE_FAST_PATH=0` to force Jobs; at most `MAX_CONCURRENT_JOBS=1` build/bundle Job at a time (hades are ~77-79% memory).

## Configs & Credentials

- [secrets.sops.yaml](secrets.sops.yaml): `Secret/edge-registry-creds` (SOPS), the lldap account `edge-services` (member of `registry-admin`: push + pull). Keys: `username`, `password`, and `config.json` (docker auth file mounted by Kaniko). Used by the operator (env `REGISTRY_USERNAME/PASSWORD`), build Jobs (Kaniko) and the edge pods (env `EDGE_REGISTRY_USERNAME/PASSWORD`). The edge pods only need pull access, so a separate `registry-pull` account would be a safer split.
- Repo allowlist: `EDGE_REPO_ALLOWLIST` (regex list, default `^https://github\.com/vmd1/`).
- Optional per-site Secrets: `spec.repoSecretRef` (key `token`), `spec.secretRef` (Worker secrets).
