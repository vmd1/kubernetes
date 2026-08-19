# Cinepro

Cinepro is a media-aggregation API backend (`cinepro-core`) connecting to external movie APIs (TMDB) and caching results using the cluster's shared Redis server.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines the namespace, deployment (running 2 replicas of `cinepro-core`), service, and Traefik `IngressRoute` configuration for routing endpoints. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `cinepro-secrets` storing `TMDB_API_KEY`. |

## Design Decisions

- **Multi-replica Setup**: Deploys `2` replicas of `cinepro-core` to provide high availability and load balancing across cluster nodes.
- **In-Memory Cache Layer**: Configured with `CACHE_TYPE=redis` linking to the main Redis master. This avoids excessive TMDB API rate-limit usage by keeping metadata local.
- **Strict Endpoint Routing**: Traefik ingress rules route only `/v1/movies` and `/v1/tv` paths on `api.vmd1.homelab` to the application, restricting access to backend management endpoints.

## Dependencies

- **Caching Server**: Requires connection to the shared Redis master service (`redis-master.redis.svc.cluster.local:6379`).
- **External API**: Outbound connectivity to The Movie Database (TMDB) API servers.

## Services & Routers

- **Kubernetes Service**: `cinepro-core` (ClusterIP, exposing port `3000`).
- **Ingress Routes**:
  - Host `api.vmd1.homelab` with PathPrefix `/v1/movies`.
  - Host `api.vmd1.homelab` with PathPrefix `/v1/tv`.

## Storage

This service is stateless and does not declare any PersistentVolumeClaims (PVCs). It relies entirely on Redis for cache storage.

## Constraints & Scheduling

- **Resource Limits**:
  - Request: `100m` CPU, `128Mi` RAM.
  - Limit: `500m` CPU, `512Mi` RAM.
- **Memory Tuning**: Defines `MALLOC_TRIM_THRESHOLD_=100000` to optimize Node.js/V8 garbage collection memory reclamation.

## Configs & Credentials

Injected via environment variables in the deployment spec:
- `TMDB_API_KEY`: API key for TMDB connectivity.
- `TMDB_CACHE_TTL`: Cache time-to-live set to `86400` seconds (24 hours).
- `REDIS_HOST` / `REDIS_PORT`: Configured to point to the shared Redis cluster master endpoint.
