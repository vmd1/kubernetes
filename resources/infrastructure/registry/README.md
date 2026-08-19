# Docker Registry

This folder deploys a private self-hosted Docker registry (`registry:2`). It provides in-cluster storage for custom container images, securing endpoints with htpasswd basic authentication.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Full K8s manifest containing Namespace `registry`, PersistentVolumeClaim, Secret containing htpasswd strings, basicAuth Middleware, Deployment, Service, and Traefik `IngressRoute`. |

## Design Decisions

- **Secure Ingress with Middleware**: Rather than relying on registry-side basic auth configs, authentication is delegated to Traefik's `basicAuth` middleware (`registry-auth`) referencing htpasswd strings stored in `registry-auth-secret`.
- **Golang Garbage Collection Tuning**: Injected `GOGC=50` environment variable to trigger garbage collection twice as fast as default. This limits memory bloat during massive parallel chunk pushes.
- **Recreate Strategy**: The deployment is configured with `Recreate` to ensure the block volume is unmounted from old pods before scheduling new ones.

## Dependencies

- **Traefik Ingress**: Leveraged for SSL termination and basic auth middleware execution.

## Services & Routers

- **Kubernetes Service**: `registry` (ClusterIP, exposing port `5000` mapping to container port `5000`).
- **Ingress Route**:
  - Host `registry.vmd1.homelab` on `websecure` entrypoint, routing requests to `registry` service, protected by `registry-auth` basic auth middleware.

## Storage

- **PVC**: `registry-pvc`
  - **Storage Class**: `longhorn-single-replica`
  - **Size**: `10Gi`
  - **Mount Point**: Mounted to `/var/lib/registry`.
  - **Data Persistence**: Stores the container image blobs, manifest indices, and layers.

## Constraints & Scheduling

- **Deployment Strategy**: Set to `Recreate` deployment strategy. This ensures only a single running replica writes to the backing block storage.
- **Resource Constraints**:
  - Request: `100m` CPU, `128Mi` RAM.
  - Limit: `500m` CPU, `512Mi` RAM.

## Configs & Credentials

- **Secret**: `registry-auth-secret`
  - Houses the user htpasswd credentials string (User: `admin`).
