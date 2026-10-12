# QEComp (`resources/applications/qecomp/`)

QEComp is an OIDC-authenticated app (API + SPA served same-origin) with Redis-backed leader election for HA, fronted at `tmtools.vmd1.homelab`. It signs users in through the cluster-wide [Authelia](../authelia/README.md) OIDC provider (`identity.vmd1.homelab`, users and groups from lldap).

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
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` for `tmtools.vmd1.homelab` (QEComp). |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secrets: `qecomp-secrets`, `ghcr-pull-secret` (private image pull). |
| [kustomization.yaml](kustomization.yaml) | Kustomize manifest for QEComp. |

## Design Decisions

- **Group-based permissions**: QEComp maps the OIDC `groups` claim to permissions via its own `role_permissions` table. The lldap groups must exist with exactly these names: `qecomp-admin` (all permissions), `qecomp-operator`, `qecomp-video`, `qecomp-lighting`, `qecomp-emcee`, `qecomp-viewer`. Authelia's `qecomp_users` policy only lets members of these groups sign in; everyone else is denied.
- **Leader-election HA**: QEComp scales via `kubectl scale deployment/qecomp -n qecomp --replicas=N` — the app handles N replicas natively via a Redis leader-election lock (only one pod is ever "active"; the rest serve reads/HA passively). Pod anti-affinity is declared up front so it takes effect automatically once scaled past 1 replica.
- **`edge-retry` middleware referenced explicitly**: this middleware only actually exists in namespace `vmd1-web` (created outside git); other apps in this repo reference it with no namespace, which silently resolves to their own namespace and never resolves. QEComp references it as `namespace: vmd1-web` so it actually works.

## Dependencies

- **Authelia** (`identity.vmd1.homelab`): OIDC client `qecomp` (client secret `OIDC_CLIENT_SECRET`, `client_secret_post`). Access to the client is limited to members of the lldap groups below.
- **CloudNativePG (CNPG)**: Database service `pg-cluster-rw.cnpg.svc.cluster.local:5432`, database/role `qecomp` created out-of-band via `psql` exec (not the CNPG `Database` CRD).
- **Redis**: `redis-master.redis.svc.cluster.local:6379` (no auth), shared with `cinepro`.
- **Backblaze B2**: S3-compatible object storage, bucket `qecomp` (private) in region `eu-central-003`.
- **GHCR**: private image `ghcr.io/qerobotics/vex-tm-tools:backend`, pulled via `ghcr-pull-secret`.

## Services & Routers

- **Service**: `qecomp` (ClusterIP, port 80 → 8000).
- **IngressRoute**: `tmtools.vmd1.homelab` (QEComp).

## Storage


## Constraints & Scheduling

- **Instance Count**: QEComp scales via the replica count (see Leader-election HA above); node selector below.
- **Node Selectors**: `topology.kubernetes.io/zone: uk-home`.

## Configs & Credentials

- **Secret `qecomp-secrets`**: `POSTGRES_DSN`, `REDIS_URL`, `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `ADMIN_LOCAL_PASSWORD`, `SECRET_KEY`, `ENCRYPTION_KEY`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`.
- **Secret `ghcr-pull-secret`**: `kubernetes.io/dockerconfigjson` for pulling the private QEComp image.
- **Known follow-up**: Authelia's notifier is filesystem-based (no SMTP configured) — password reset/2FA enrollment links are written inside the pod and are not retrievable in production. Replace with a real `smtp:` block before relying on that flow.
- `role_permissions` is already seeded with a wildcard (`*`) permission for `qecomp-admin` by the app's own Alembic migrations (`b2c3d4e5f6a7`) — no manual DB seed needed, confirmed live post-deploy.

## Related

- [../README.md](../README.md) — Applications layer.
- [../../crds-and-operators/cnpg/README.md](../../crds-and-operators/cnpg/README.md) — CNPG PostgreSQL operator.
- [../../crds-and-operators/redis/README.md](../../crds-and-operators/redis/README.md) — Redis operator/cluster.
