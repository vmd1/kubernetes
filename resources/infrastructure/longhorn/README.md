# Longhorn UI & Backup Target (`resources/infrastructure/longhorn/`)

This folder complements the [Longhorn operator](../../crds-and-operators/longhorn/README.md) with the **Longhorn UI ingress route** and the **S3 backup target** configuration. The operator chart itself, recurring backup jobs, and the backup credential secret live in [crds-and-operators/longhorn/](../../crds-and-operators/longhorn/README.md).

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Services & Routers](#services--routers)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [allow-prometheus.yaml](allow-prometheus.yaml) | `NetworkPolicy` letting the monitoring `prometheus` pod reach `longhorn-manager` on `:9500` (Longhorn 1.12 NetworkPolicies otherwise refuse the metrics scrape). |
| [manifest.yaml](manifest.yaml) | `IngressRoute` for the Longhorn UI (`longhorn.vmd1.homelab`) and the `BackupTarget` (`default`) pointing at Backblaze B2 S3. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |

## Design Decisions

- **Backups to Backblaze B2**: The `BackupTarget` stores volume backups in the `homelab-longhorn` bucket of `eu-central-003` (`s3://homelab-longhorn@eu-central-003/`), authenticating with the `longhorn-backup-secret` (SOPS-encrypted in [crds-and-operators/longhorn/secrets.sops.yaml](../../crds-and-operators/longhorn/secrets.sops.yaml)). The target is polled every 5 minutes.
- **UI Protected Behind Authelia SSO**: The Longhorn management UI is exposed only on `websecure` and chained through `oauth2-proxy-kmnet-uk` (Authelia SSO), plus `rate-limit`, `edge-retry`, `compress`, and `security-headers` middlewares.

## Dependencies

- **Longhorn operator**: Must be running (see [crds-and-operators/longhorn](../../crds-and-operators/longhorn/README.md)) for the `BackupTarget` CRD and `longhorn-frontend` service to exist.
- **oauth2-proxy**: `oauth2-proxy-kmnet-uk` middleware from the `oauth2-proxy` namespace gates the UI.
- **Backblaze B2**: Outbound S3 access to `eu-central-003` for backup uploads.

## Services & Routers

- **Ingress Route**: `longhorn.vmd1.homelab` on `websecure` → service `longhorn-frontend` port `80`, wrapped in the middleware chain above.

## Related

- [../../crds-and-operators/longhorn/README.md](../../crds-and-operators/longhorn/README.md) — operator chart, recurring jobs, and backup secret.
- [../../crds-and-operators/multus/README.md](../../crds-and-operators/multus/README.md) — the `storage-macvlan-eth0` network used by Longhorn storage traffic.
- [../README.md](../README.md) — the infrastructure layer this folder belongs to.
