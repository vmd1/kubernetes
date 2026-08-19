# Authentik

Authentik is an open-source Identity Provider (IdP) focused on flexibility and versatility. It acts as the centralized authentication service for various applications in this cluster, integrating with Traefik via forward authentication middleware.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Full K8s manifest containing Namespace, ServiceAccount, RBAC Roles/Bindings, Secrets, ConfigMaps, PVCs, Deployments (Server & Worker), Services, IngressRoutes, and Middleware. |

## Design Decisions

- **Architecture**: Separated into a web-facing `server` deployment and an asynchronous background task `worker` deployment, both using the `ghcr.io/goauthentik/server:2026.5.4` image.
- **Resource Tuning**: Tuned database/worker parameters via env variables such as `MALLOC_TRIM_THRESHOLD_=100000`, `AUTHENTIK_WEB__WORKERS=1`, and limited threads (`AUTHENTIK_WEB__THREADS=2`, `AUTHENTIK_WORKER__THREADS=2`) to reduce RAM overhead in a resource-constrained cluster.
- **Forward Authentication**: Employs Traefik's `ForwardAuth` middleware (`authentik-auth`) to intercept incoming traffic to secure cluster subdomains and redirect unauthenticated users to the login flow.

## Dependencies

- **Database**: CloudNativePG PostgreSQL Cluster (`pg-cluster-rw.cnpg.svc.cluster.local`).
- **Cache**: Redis Cluster master instance (`redis-master.redis.svc.cluster.local`).
- **Ingress Controller**: Traefik (utilizes Traefik custom resource definitions like `IngressRoute` and `Middleware`).

## Services & Routers

- **Kubernetes Service**: `authentik` (ClusterIP, exposing port `9000` for HTTP and `9443` for HTTPS).
- **Ingress Routes**:
  - `authentik.vmd1.homelab` matching `websecure` entrypoint, routing traffic directly to `authentik` service on port `9000`.
  - Regular expression match `HostRegexp('{subdomain:[a-z0-9-]+}.vmd1.homelab')` combined with `PathPrefix('/outpost.goauthentik.io/')` for Authentik Outpost proxy routing.
- **Middleware**: `authentik-auth` (ForwardAuth configuration pointing to `http://authentik.authentik.svc.cluster.local:9000/outpost.goauthentik.io/auth/traefik` with mapped header attributes).

## Storage

- **PVCs**:
  - `authentik-media` (`longhorn-single-replica` storage class, requested size: `2Gi`, mounted at `/media` on ReadWriteMany / RWX basis). Holds custom logo designs, media files, and avatars, shared across replicas.
  - `authentik-templates` (`longhorn-single-replica` storage class, requested size: `1Gi`, mounted at `/templates` on ReadWriteMany / RWX basis). Holds customizable login or email blueprints, shared across replicas.

## Constraints & Scheduling

- **Deployment Strategy**: Both `authentik` and `authentik-worker` use the `Recreate` deployment strategy. This ensures that only a single pod is active during updates to prevent SQLite lockups or concurrent write issues on local-path PVCs.
- **Resources**:
  - **Server**: CPU requests `100m` (limit `1000m`), Memory requests `384Mi` (limit `1.5Gi`).
  - **Worker**: CPU requests `100m` (limit `1000m`), Memory requests `384Mi` (limit `1Gi`).
- **Security Context**: Both pods run non-root (`runAsUser: 1000`, `runAsGroup: 1000`), disallow privilege escalation, and drop all Linux kernel capabilities to ensure low privilege limits.

## Configs & Credentials

- **ConfigMap**: `authentik-config`
  - Defines DB names, users, log level (`trace`), disable checks/analytics flags, and environment worker threads.
- **Secret**: `authentik-secrets`
  - Contains `AUTHENTIK_SECRET_KEY` (secret token signing key) and `AUTHENTIK_POSTGRESQL__PASSWORD` (credentials for DB access).
