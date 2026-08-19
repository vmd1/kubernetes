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
| [manifest.yaml](manifest.yaml) | `IngressRoute` for the Longhorn UI (`longhorn.vmd1.homelab`) and the `BackupTarget` (`default`) pointing at Backblaze B2 S3. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |

## Design Decisions

- **Backups to Backblaze B2**: The `BackupTarget` stores volume backups in the `homelab-longhorn` bucket of `eu-central-003` (`s3://homelab-longhorn@eu-central-003/`), authenticating with the `longhorn-backup-secret` (SOPS-encrypted in [crds-and-operators/longhorn/secrets.sops.yaml](../../crds-and-operators/longhorn/secrets.sops.yaml)). The target is polled every 5 minutes.
- **UI Protected Behind Authentik**: The Longhorn management UI is exposed only on `websecure` and chained through `authentik-auth` (SSO), plus `rate-limit`, `edge-retry`, `compress`, and `security-headers` middlewares.

## Dependencies

- **Longhorn operator**: Must be running (see [crds-and-operators/longhorn](../../crds-and-operators/longhorn/README.md)) for the `BackupTarget` CRD and `longhorn-frontend` service to exist.
- **Authentik**: `authentik-auth` middleware from the `authentik` namespace gates the UI.
- **Backblaze B2**: Outbound S3 access to `eu-central-003` for backup uploads.

## Services & Routers

- **Ingress Route**: `longhorn.vmd1.homelab` on `websecure` → service `longhorn-frontend` port `80`, wrapped in the middleware chain above.

## Related

- [../../crds-and-operators/longhorn/README.md](../../crds-and-operators/longhorn/README.md) — operator chart, recurring jobs, and backup secret.
- [../../crds-and-operators/multus/README.md](../../crds-and-operators/multus/README.md) — the `storage-macvlan-eth0` network used by Longhorn storage traffic.
- [../README.md](../README.md) — the infrastructure layer this folder belongs to.
