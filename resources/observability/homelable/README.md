# Homelable (`resources/observability/homelable/`)

Homelable is a self-hosted homelab diagram app with live status monitoring and a read-only Kubernetes import. Served at `lab.vmd1.homelab`.

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | ServiceAccount, read-only ClusterRole/Binding, PVC, backend and frontend Deployments and Services. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` exposing `lab.vmd1.homelab` (frontend only; WebSockets pass through). |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `homelable-secrets`: `SECRET_KEY` and `OIDC_CLIENT_SECRET`. |
| [kustomization.yaml](kustomization.yaml) | Kustomize manifest. |

## Design Decisions

- **Prebuilt images pinned by digest** (`ghcr.io/vmd1/homelable-{backend,frontend}`; the registry only publishes `main` and `latest`, so the `main` multi-arch index digests are pinned). Bump by updating the digests.
- **Single backend replica**: SQLite is single-writer, so the backend is 1 replica with strategy `Recreate`. The frontend (nginx) is stateless and proxies `/api/`, WebSockets, `/docs` to `backend.homelable.svc:8000`.
- **SSO through Authelia**: `AUTH_MODE=oidc`, client `homelable` (`client_secret_basic`, PKCE S256), callback `https://lab.vmd1.homelab/api/v1/auth/oidc/callback`. Policy `homelable_users` allows lldap group `admin` (`one_factor`). Local password login is not used; the plaintext client secret lives only in `homelable-secrets`, the pbkdf2 hash in the Authelia ConfigMap.
- **Tailnet only**: the route has the `tailnet-only` middleware first ([proxy/traefik](../../proxy/traefik/README.md)), so it is reachable only with Tailscale on; everyone else gets the branded 403.
- **Kubernetes import** uses in-cluster config: the backend pod's ServiceAccount token and CA. RBAC is get/list on nodes, pods, services, namespaces and deployments, statefulsets, daemonsets only. No `KUBERNETES_*` env vars are set.
- **Scanner off**: `SCANNER_RANGES=[]` (pod network cannot ARP-scan the LAN, no `hostNetwork`). The backend has `NET_RAW` for ping checks.
- Runs as root in the image; no `runAsNonRoot`.

## Storage

- `homelable-data-pvc`: `1Gi` (`longhorn-single-replica`) at `/app/data` (`homelab.db`, `scan_config.json`, `uploads/`).

## Scheduling

Both Deployments pin to `topology.kubernetes.io/zone: uk-home` with the standard 60s not-ready/unreachable tolerations.

## Related

- [../authelia/README.md](../../auth/authelia/README.md) — OIDC provider.
