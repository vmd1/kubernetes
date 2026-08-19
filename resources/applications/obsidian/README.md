# Obsidian Sync Server (CouchDB)

Obsidian Sync Server provides a self-hosted database backend for Obsidian markdown notes using Apache CouchDB and the Obsidian Self-Hosted LiveSync plugin.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines the Namespace `obsidian`, Secret for CouchDB admin credentials, ConfigMap for CouchDB tuning (CORS, max document size, single node cluster), `longhorn-single-replica` PVC, Deployment running `couchdb:3.4.2`, Service, and Traefik `IngressRoute`. |

## Design Decisions

- **CORS & Obsidian LiveSync Optimization**: Custom `10-obsidian.ini` configuration enables CORS for Obsidian client apps (`app://obsidian.md`, `capacitor://localhost`, `http://localhost`), sets `max_document_size = 50000000` (50MB), enables `require_valid_user = true` for authentication security, and `require_valid_user_except_for_up = true` for health checks.
- **Init Container Configuration Injection**: An init container copies the custom `.ini` configuration into an `emptyDir` mounted at `/opt/couchdb/etc/local.d`. This allows CouchDB's entrypoint script to run cleanly without permission errors on read-only mounted ConfigMap files.
- **Single Replica & Node Co-Location**: Pinned to home node (`hades-01` in zone `uk-home`) and backed by `longhorn-single-replica` persistent volume to ensure low disk I/O latency and data persistence across pod restarts.
- **Probe Health Checks**: Liveness and readiness probes query the unauthenticated `/_up` health endpoint to ensure accurate health monitoring without storing credentials in probe manifests.

## Dependencies

- **Storage Class**: Longhorn driver (`driver.longhorn.io`).
- **Traefik Ingress**: Exposes HTTPS endpoints with automatic wildcard TLS certificate.

## Services & Routers

- **Kubernetes Service**: `obsidian-sync` (ClusterIP, port `5984` mapping to container port `5984`).
- **Ingress Route**:
  - Exposes CouchDB API on domains `obsidian.vmd1.homelab`, `obsidian.vmd1.homelab`, `obsidian-sync.vmd1.homelab`, and `obsidian-sync.vmd1.homelab`.

## Storage

- **PVC**: `obsidian-pvc`
  - **Storage Class**: `longhorn-single-replica`
  - **Size**: `10Gi`
  - **Mount Point**: Mounted to `/opt/couchdb/data`.
  - **Data Persistence**: Preserves CouchDB databases (`_users`, `_replicator`, and Obsidian sync vaults).

## Constraints & Scheduling

- **Deployment Strategy**: Set to `Recreate` strategy so only one pod instance accesses the single-replica storage.
- **Scheduling**: Pinned via `nodeSelector` to `topology.kubernetes.io/zone: uk-home`.
- **Resource Constraints**:
  - Request: `100m` CPU, `256Mi` RAM.
  - Limit: `1000m` CPU, `1Gi` RAM.

## Configs & Credentials

- **Admin Credentials**: Secret `obsidian-secrets` configures user `admin` with the requested password.
