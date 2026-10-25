# Light LDAP (lldap)

Lldap is a simplified, lightweight LDAP server designed for user management. It provides authentication services for internal homelab tools using CNPG PostgreSQL as its database backend.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines Secrets (JWT, Seed key, Database details, and TLS certificates), Deployment (2 replicas), Services (HTTP, LDAP, LDAPS), and Traefik `IngressRoute`. |

## Design Decisions

- **Highly Available Architecture**: Configured with `replicas: 2` to distribute requests across nodes, ensuring robust identity resolution even if one instance fails.
- **External SQL Database**: Rather than storing users in a local SQLite file, Lldap stores its data in the cluster's CloudNativePG PostgreSQL database cluster.
- **LDAPS Support**: Deploys native SSL/TLS encryption for LDAP queries (using static certificates mounted via `lldap-certs` Secret) to protect credentials over transit.

## Dependencies

- **Database**: CloudNativePG PostgreSQL Service (`pg-cluster-rw.cnpg.svc.cluster.local:5432`).
- **TLS certs**: Relies on `lldap-certs` secret for loading `cert.pem` and `key.pem` files for LDAPS communication.

## Services & Routers

- **Kubernetes Services**:
  - `lldap` (ClusterIP, exposing port `17170` HTTP, `3890` LDAP, and `6360` LDAPS).
- **Ingress Route**:
  - Host `lldap.vmd1.homelab` on `websecure` entrypoint routing to service port `17170` (management console), gated by the `oauth2-proxy-kmnet-uk` forward-auth middleware (Authelia SSO). Because the UI is behind SSO, API clients can no longer call `/auth/simple/login` or the GraphQL API on this host from outside the cluster; in-cluster clients use the LDAP service directly.

## Storage

- **Data Persistence**: Because Lldap offloads user/group records to the external Postgres cluster, the container's local directory `/data` is backed by a transient `emptyDir: {}` volume.
- **Certificates**: Mounted read-only from the `lldap-certs` secret into `/certs`.

## Constraints & Scheduling

- Runs 2 replicas with standard cluster scheduling policies.
- **Resource Constraints**:
  - Request: `10m` CPU, `16Mi` RAM.
  - Limit: `1000m` CPU, `64Mi` RAM. The CPU limit is deliberately generous: password binds are CPU-bound (about 1 s each when throttled at `100m`, about 150 ms now), and Authelia does several per sign-in.

## Configs & Credentials

- **Secret**: `lldap-certs`
  - Mounts `cert.pem` and `key.pem` to secure LDAPS queries.
- **Secret**: `lldap-secrets`
  - `LLDAP_JWT_SECRET`: signing token key.
  - `LLDAP_KEY_SEED`: key generation seed.
  - `LLDAP_DATABASE_URL`: URI detailing connection strings to the Postgres server.
- **Configuration Variables**: Base DN configured to `dc=kmnet,dc=uk`, and system timezone mapped to `Europe/London`.

## Groups used for access control

Beyond the standard lldap groups, these groups gate access in other apps (create them in the lldap UI; membership is managed there):

| Group | Used by |
| :--- | :--- |
| `Domain: <domain>` | oauth2-proxy forward-auth per domain (see [oauth2-proxy](../../applications/oauth2-proxy/README.md)) |
| `grafana-admin`, `grafana-editor`, `grafana-viewer` | Grafana role mapping and access (see [monitoring](../../applications/monitoring/README.md)) |
| `registry-admin`, `registry-pull` | Registry push/pull (see [registry](../registry/README.md)) |
| `nextcloud_users`, `nextcloud_admins`, `jellyfin`, `jellyfin_admin`, `homeassistant_user`, `homeassistant_admin`, `family`, `qecomp-*`, `synapse-users` | Per-app Authelia authorization policies |

Service accounts: `authelia` (Authelia's bind user), `registry` (docker-auth's read-only bind user), and `k3s-registry-pull` (pull-only registry account for the nodes and image-pull secrets).
