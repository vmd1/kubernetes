# BookOrbit (`resources/applications/bookorbit/`)

BookOrbit is a self-hosted digital library and reading platform for ebooks, audiobooks, comics, and PDFs.

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Services & Routers](#services--routers)
- [Storage](#storage)
- [Constraints & Scheduling](#constraints--scheduling)
- [Configs & Credentials](#configs--credentials)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Deployment of BookOrbit app (`ghcr.io/bookorbit/bookorbit:latest`), Longhorn PVCs, and ClusterIP service on port 3000. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` exposing `read.vmd1.homelab`. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `bookorbit-secrets` with database credentials, JWT secret, and bootstrap tokens. |
| [kustomization.yaml](kustomization.yaml) | Kustomize manifest for BookOrbit. |

## Design Decisions

- **PostgreSQL & pgvector Backend**: Uses shared CNPG cluster `pg-cluster` in namespace `cnpg` with `vector`, `uuid-ossp`, `pg_trgm`, and `unaccent` extensions enabled.
- **Single Replica Strategy**: Deployment uses strategy `Recreate` to ensure safe volume detachment on Longhorn RWO volumes.

## Dependencies

- **CloudNativePG (CNPG)**: Database service `pg-cluster-rw.cnpg.svc.cluster.local:5432`.
- **Longhorn**: Dynamic storage provisioning with `longhorn-single-replica`.

## Services & Routers

- **Service**: `bookorbit` (ClusterIP, port 3000).
- **IngressRoute**: `read.vmd1.homelab` on entrypoint `websecure`.

## Storage

- `bookorbit-data-pvc`: `10Gi` (StorageClass `longhorn-single-replica`) mounted at `/data`.
- `bookorbit-books-pvc`: `50Gi` (StorageClass `longhorn-single-replica`) mounted at `/books`.

## Constraints & Scheduling

- **Instance Count**: `1` replica.
- **Node Selectors**: `topology.kubernetes.io/zone: uk-home` (targets `hades-01` or `hades-02`).
- **Tolerations**: Tolerates 60s for `node.kubernetes.io/not-ready` and `node.kubernetes.io/unreachable`.

## Configs & Credentials

- **Secret**: `bookorbit-secrets` containing `POSTGRES_PASSWORD`, `DATABASE_URL`, `JWT_SECRET`, `SETUP_BOOTSTRAP_TOKEN`, and `EMAIL_ENCRYPTION_KEY`.

## Related

- [../README.md](../README.md) — Applications layer.
- [../../crds-and-operators/cnpg/README.md](../../crds-and-operators/cnpg/README.md) — CNPG PostgreSQL operator.
- [../authentik/README.md](../authentik/README.md) — Authentik SSO/Forward Auth.
