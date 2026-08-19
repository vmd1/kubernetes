# CloudNativePG (cnpg) (`resources/crds-and-operators/cnpg/`)

CloudNativePG (CNPG) is an operator designed to manage PostgreSQL database clusters on Kubernetes. It automates replication, failover, backup, recovery, and updates for highly available Postgres deployments.

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Services & Routers](#services--routers)
- [Storage & Backups](#storage--backups)
- [Constraints & Scheduling](#constraints--scheduling)
- [Configs & Credentials](#configs--credentials)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [operator.yaml](operator.yaml) | Full deployment of the CloudNativePG Operator (v1.25.0), including CRDs, ServiceAccounts, RBAC permissions, and manager deployment. |
| [manifest.yaml](manifest.yaml) | The PostgreSQL cluster `pg-cluster`: 2 instances, tuned parameters, bootstrap settings, scheduling rules, and S3-based WAL archiving/backup rules. |
| [scheduled-backup.yaml](scheduled-backup.yaml) | `ScheduledBackup` `pg-cluster-daily-backup` running daily at 00:00 (UTC). |
| [manual-backup-trigger.yaml](manual-backup-trigger.yaml) | A `Backup` resource used to perform a one-off database backup when applied. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted `cnpg-backup-secret` (S3 credentials for backup destinations) plus additional database secrets. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |

## Design Decisions

- **Operator Pattern**: Relies on the CNPG Operator to handle rolling upgrades and master failover without manual intervention.
- **WAL Archiving to Backblaze B2**: Continuously streams WAL files via `barmanObjectStore` to `s3://homelab-cnpg/` at `https://s3.eu-central-003.backblazeb2.com` (path-style addressing) for point-in-time recovery.
- **Tuned PostgreSQL Parameters**:
  - `shared_buffers: "128MB"`: low shared memory usage fit for a homelab.
  - `max_connections: "100"`: capped to prevent RAM exhaustion.
  - `work_mem: "4MB"`: 4MB per sorting/join operation.
- **LoadBalancer for External Access**: An additional `rw` service (`pg-cluster-rw-lb`) is exposed on `192.168.12.222:5432` via Kube-VIP for external database clients.

## Dependencies

- **S3 Storage Provider**: Backblaze B2 (`s3.eu-central-003.backblazeb2.com`) for WAL logs and daily backups.
- **Kube-VIP**: Provides `192.168.12.222` for the `pg-cluster-rw-lb` LoadBalancer service.

## Services & Routers

- **Kubernetes Services** (managed by the operator):
  - `pg-cluster-rw` (ClusterIP, routing to the current writable primary instance).
  - `pg-cluster-ro` (ClusterIP, routing to read-only replicas).
  - `pg-cluster-r` (ClusterIP, routing to all instances).
  - `pg-cluster-rw-lb` (LoadBalancer `192.168.12.222:5432` via Kube-VIP).
- Internal metrics are exposed on port `9187`.

## Storage & Backups

- **Databases Storage**: `local-path` storage class, `10Gi` per instance, instantiated dynamically by the operator for each replica.
- **WAL/Backup Storage**: Offloaded to `s3://homelab-cnpg/` on Backblaze B2, with `retentionPolicy: 7d` and gzip-compressed WAL.

## Constraints & Scheduling

- **Instance Count**: `2` replicas.
- **Node Selectors**: Restricted to nodes tagged `storage.vmd1.homelab/cnpg: "true"`.
- **Anti-Affinity**: `podAntiAffinityType: required` — master and replica pods are never co-located on the same host.
- **Tolerations**: Tolerates ingress/control-plane/master taints for scheduling flexibility.
- **Resources**: Request `100m` CPU / `512Mi` RAM; limit `1000m` CPU / `1Gi` RAM.

## Configs & Credentials

- **Secret**: `cnpg-backup-secret` (SOPS-encrypted in [secrets.sops.yaml](secrets.sops.yaml)) — stores `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`, and `REGION`.
- **Env**: `BARMAN_S3_USE_PATH_STYLE: "true"` to enforce S3 path-style addressing (required by Backblaze B2).

## Related

- [../README.md](../README.md) — the CRDs & operators layer this folder belongs to.
- [infrastructure/lldap/README.md](../../infrastructure/lldap/README.md) and the applications under [applications/](../../applications/README.md) — consumers of the `pg-cluster` database.
