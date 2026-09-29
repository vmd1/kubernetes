# QEComp (`resources/applications/qecomp/`)

QEComp is an OIDC-authenticated app (API + SPA served same-origin) with Redis-backed leader election for HA, fronted at `qecomp.vmd1.homelab`. Authelia — a dedicated production OIDC provider for this app — runs alongside it in the same namespace, fronted at `auth.vex.vmd1.homelab`.

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
| [manifest.yaml](manifest.yaml) | Namespace `qecomp`, ConfigMap `qecomp-config`, Deployment `qecomp` (`ghcr.io/qerobotics/vex-tm-tools:backend`, private image), ClusterIP Service on port 8000. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` for `qecomp.vmd1.homelab` (QEComp) and `auth.vex.vmd1.homelab` (Authelia), plus the dedicated `Certificate` for the Authelia host. |
| [authelia.yaml](authelia.yaml) | Authelia `Deployment`, `Service`, `ConfigMap` (OIDC provider config), and `PersistentVolumeClaim` for its SQLite storage. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secrets: `qecomp-secrets`, `ghcr-pull-secret` (private image pull), `authelia-secrets`, `authelia-users`. |
| [kustomization.yaml](kustomization.yaml) | Kustomize manifest for QEComp + Authelia. |

## Design Decisions

- **Leader-election HA**: QEComp scales via `kubectl scale deployment/qecomp -n qecomp --replicas=N` — the app handles N replicas natively via a Redis leader-election lock (only one pod is ever "active"; the rest serve reads/HA passively). Pod anti-affinity is declared up front so it takes effect automatically once scaled past 1 replica.
- **Dedicated Authelia instance**: Authelia here is scoped to QEComp only (not the cluster-wide Authentik SSO used elsewhere) — a separate OIDC provider, file-backed auth, SQLite storage, singular replica.
- **`enableServiceLinks: false` on the Authelia pod**: Kubernetes auto-injects `<SERVICE_NAME>_*` env vars for every Service in a pod's namespace. Since the Service is named `authelia`, this collided with Authelia's own `AUTHELIA_`-prefixed config env vars (the injected `AUTHELIA_PORT` conflicted with the explicit `server.address` setting) and crash-looped the pod on startup. Confirmed live during deployment — disabling service-link injection was the fix, not renaming the Service.
- **Two-level subdomain TLS**: the shared `cluster-wildcard-tls` (`*.vmd1.homelab`) only covers one DNS label, so it doesn't reach `auth.vex.vmd1.homelab`. A dedicated `Certificate` (`authelia-vex-tls`) is issued for it via the existing `letsencrypt-cloudflare` ClusterIssuer. `qecomp.vmd1.homelab` needs no explicit `tls:` block, like the other `vmd1.homelab` apps.
- **`edge-retry` middleware referenced explicitly**: this middleware only actually exists in namespace `vmd1-web` (created outside git); other apps in this repo reference it with no namespace, which silently resolves to their own namespace and never resolves. QEComp/Authelia reference it as `namespace: vmd1-web` so it actually works.

## Dependencies

- **CloudNativePG (CNPG)**: Database service `pg-cluster-rw.cnpg.svc.cluster.local:5432`, database/role `qecomp` created out-of-band via `psql` exec (not the CNPG `Database` CRD).
- **Redis**: `redis-master.redis.svc.cluster.local:6379` (no auth), shared with `cinepro`.
- **Backblaze B2**: S3-compatible object storage, bucket `qecomp` (private) in region `eu-central-003`.
- **GHCR**: private image `ghcr.io/qerobotics/vex-tm-tools:backend`, pulled via `ghcr-pull-secret`.

## Services & Routers

- **Service**: `qecomp` (ClusterIP, port 80 → 8000), `authelia` (ClusterIP, port 9091).
- **IngressRoute**: `qecomp.vmd1.homelab` (QEComp), `auth.vex.vmd1.homelab` (Authelia, explicit TLS via `authelia-vex-tls`).

## Storage

- `authelia-data`: `1Gi` (StorageClass `longhorn-single-replica`) mounted at `/config/data` — holds Authelia's SQLite DB and filesystem notifier output.

## Constraints & Scheduling

- **Instance Count**: `1` replica for both QEComp and Authelia (Authelia is file+SQLite backed and not designed for >1 replica).
- **Node Selectors**: `topology.kubernetes.io/zone: uk-home`.

## Configs & Credentials

- **Secret `qecomp-secrets`**: `POSTGRES_DSN`, `REDIS_URL`, `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `ADMIN_LOCAL_PASSWORD`, `SECRET_KEY`, `ENCRYPTION_KEY`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`.
- **Secret `ghcr-pull-secret`**: `kubernetes.io/dockerconfigjson` for pulling the private QEComp image.
- **Secret `authelia-secrets`**: `jwt_secret`, `session_secret`, `storage_encryption_key`, `oidc_hmac_secret`, `oidc_issuer_private_key.pem`.
- **Secret `authelia-users`**: `users_database.yml` — bcrypt-hashed local admin account (`admin`, groups `qecomp-admin`/`admins`).
- **Known follow-up**: Authelia's notifier is filesystem-based (no SMTP configured) — password reset/2FA enrollment links are written inside the pod and are not retrievable in production. Replace with a real `smtp:` block before relying on that flow.
- `role_permissions` is already seeded with a wildcard (`*`) permission for `qecomp-admin` by the app's own Alembic migrations (`b2c3d4e5f6a7`) — no manual DB seed needed, confirmed live post-deploy.

## Related

- [../README.md](../README.md) — Applications layer.
- [../../crds-and-operators/cnpg/README.md](../../crds-and-operators/cnpg/README.md) — CNPG PostgreSQL operator.
- [../../crds-and-operators/redis/README.md](../../crds-and-operators/redis/README.md) — Redis operator/cluster.
