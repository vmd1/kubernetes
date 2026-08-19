# Longhorn Storage Engine (`resources/crds-and-operators/longhorn/`)

Longhorn is a lightweight, reliable, and powerful distributed block storage system for Kubernetes. It aggregates local storage from designated nodes and provisions persistent volumes (PVCs) for applications in the cluster.

This folder holds the **operator chart, recurring backup jobs, and the backup credential secret**. The Longhorn UI `IngressRoute` and the S3 `BackupTarget` live in [infrastructure/longhorn/](../../infrastructure/longhorn/README.md).

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Storage & Backups](#storage--backups)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Namespace `longhorn-system` and the `HelmChart` custom resource deploying Longhorn from `charts.longhorn.io`, configured with node selectors, the `storage-macvlan-eth0` storage network, and the default S3 backup target. |
| [recurring-jobs.yaml](recurring-jobs.yaml) | `RecurringJob` resources: `backup-hourly`, `backup-daily`, `backup-weekly`, `snapshot-cleanup`, `snapshot-delete`, and `filesystem-trim` for volumes in the `default` and `rca-daily` groups. |
| [manual-backup-trigger.yaml](manual-backup-trigger.yaml) | Example `Snapshot` + `Backup` pair to trigger a one-off backup of a specific volume. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted `longhorn-backup-secret` (S3 credentials for the backup target). |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |

## Design Decisions

- **Node Filtering for Storage**: `createDefaultDiskLabeledNodes: true` and `systemManagedComponentsNodeSelector: "storage.vmd1.homelab/longhorn-client:true"` keep Longhorn components and disks on nodes explicitly designated for storage duties.
- **Dedicated Storage Network**: `defaultSettings.storageNetwork: "longhorn-system/storage-macvlan-eth0"` routes storage replication traffic over the dedicated `192.168.11.0/24` macvlan network (see [multus](../multus/README.md)) instead of the Tailscale overlay.
- **S3 Backups to Backblaze B2**: Backups target `s3://homelab-longhorn@eu-central-003/` (Backblaze B2), with credentials from `longhorn-backup-secret`. The `BackupTarget` CR itself is defined in [infrastructure/longhorn/manifest.yaml](../../infrastructure/longhorn/manifest.yaml).
- **Layered Recurring Backup Groups**:
  - `default` group: hourly (retain 6), daily (retain 3), weekly (retain 2) backups.
  - `rca-daily` group (used by high-churn volumes like `prometheus-pvc`/`loki-pvc`): daily + weekly only, plus nightly snapshot cleanup/delete and a weekly filesystem trim.

## Dependencies

- **Multus**: The `storage-macvlan-eth0` network attachment must exist (see [multus/README.md](../multus/README.md)).
- **OS Dependencies**: Nodes running Longhorn components require `open-iscsi` and `nfs-common` installed on the host OS.
- **Backblaze B2**: Outbound S3 access to `eu-central-003` for backup uploads.

## Storage & Backups

- **Provisioner**: Registers StorageClasses `longhorn` and `longhorn-single-replica` for dynamic volume provisioning.
- **Backup target**: `s3://homelab-longhorn@eu-central-003/` (polled every 5m — see [infrastructure/longhorn](../../infrastructure/longhorn/README.md)).
- **Recurring jobs**:
  - `backup-hourly`: minute 0, retain 6 (`default`).
  - `backup-daily`: 02:00, retain 3 (`default`, `rca-daily`).
  - `backup-weekly`: 03:00 Sundays, retain 2 (`default`, `rca-daily`).
  - `snapshot-cleanup` / `snapshot-delete`: nightly 04:00, retain 0 / 2.
  - `filesystem-trim`: Sundays 05:00.

## Configs & Credentials

- **Secret**: `longhorn-backup-secret` (SOPS-encrypted in [secrets.sops.yaml](secrets.sops.yaml)) — Garage/B2-style S3 credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, endpoint) for the backup target.

## Related

- [infrastructure/longhorn/README.md](../../infrastructure/longhorn/README.md) — UI ingress and `BackupTarget` resource.
- [multus/README.md](../multus/README.md) — the `storage-macvlan-eth0` storage network.
- [../README.md](../README.md) — the CRDs & operators layer this folder belongs to.
