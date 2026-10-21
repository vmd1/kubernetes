# Nextcloud & Collabora Online Stack

Self-hosted productivity, cloud storage, and office suite configured with Backblaze B2 S3 as primary object storage, CloudNativePG PostgreSQL backend, Redis HA caching/locking, Collabora Online (CODE), and Traefik edge ingress.

> **Upgraded 2026-10-21:** Nextcloud went 30.0.17 -> 35.0.2 (stepwise 31/32/33/34/35 via one-off `occ upgrade` Jobs, no web exposure) on `nextcloud:35-apache` (PHP 8.5.12, patched for PHP2Shell CVE-2026-109618/109619). Pre-upgrade backups: Longhorn snapshot `nextcloud-pre-upgrade-30-0-17` on the PVC volume and a local `pg_dump` (not B2). Renovate still blocks automatic Nextcloud major bumps.

## Architecture

* **Namespace**: `nextcloud`
* **Domains**:
  * Nextcloud: `cloud.vmd1.homelab`
  * Collabora Online (CODE): `office.vmd1.homelab`
* **Storage**:
  * **Primary Object Storage**: Backblaze B2 S3 bucket `homelab-nextcloud` in `eu-central-003` (`s3.eu-central-003.backblazeb2.com`).
  * **App Directory (`/var/www/html`)**: 10 GiB PVC on `longhorn-single-replica`.
* **Database**: High-Availability CloudNativePG PostgreSQL cluster (`pg-cluster-rw.cnpg.svc.cluster.local:5432`, database `nextcloud`).
* **Cache & Locking**: High-Availability Redis Master via HAProxy (`redis-master.redis.svc.cluster.local:6379`).
* **Office Suite**: Collabora Online Development Edition (`collabora/code:latest`) integrated via `richdocuments` WOPI client.
* **Background Jobs**: Integrated `nextcloud-cron` container executing `/cron.sh` on 5-minute cycles.
* **Ingress**: Traefik `IngressRoute` with `websecure`, `cluster-wildcard-tls`, security headers, rate-limiting, and WebDAV CalDAV/CardDAV redirect middleware.
* **Placement**: Pinned to `topology.kubernetes.io/zone: uk-home` (`hades-01` / `hades-02`).

## Configuration Details

### S3 Primary Storage Configuration
Nextcloud uses native primary object storage (`\OC\Files\ObjectStore\S3`), bypassing local filesystem chunking and directly managing files as S3 objects in Backblaze B2.

### Collabora Online (Nextcloud Office)
* **WOPI Discovery URL**: `https://office.vmd1.homelab`
* **Allowlist Subnets**: `0.0.0.0/0, ::/0` (secured via signed session WOPI access tokens)
* **Container Capabilities**: `MKNOD`, `SYS_CHROOT`, `SYS_ADMIN` (enables instant bind-mount kit jail creation without slow file copying)

### Security & Optimization Settings
* **Trusted Reverse Proxies**: Cluster pod CIDR (`10.42.0.0/16`), Tailscale overlay (`100.64.0.0/10`), Home LAN (`192.168.0.0/16`).
* **Forwarded Headers**: `HTTP_X_FORWARDED_FOR`
* **Maintenance Window**: 01:00 UTC (`maintenance_window_start = 1`).
* **In-Memory Cache**: APCu for local caching, Redis for distributed cache and transactional file locking.

### Single Sign-On (Authelia)
Nextcloud signs in through the cluster-wide Authelia using the `user_oidc` app. This configuration lives in Nextcloud's database, not in this repo, so it is recorded here:

* **Provider**: `occ user_oidc:provider authelia` with client ID `nextcloud` (registered in Authelia with `client_secret_post` and PKCE), discovery URI `https://identity.vmd1.homelab/.well-known/openid-configuration`, scopes `openid profile email groups`.
* **Mappings**: user ID from `preferred_username` (`--unique-uid=0`, so it matches the existing local usernames), display name from `name`, email from `email`, groups from `groups`; group provisioning is on and limited to groups matching `^nextcloud_`.
* **Local login disabled**: `occ config:app:set user_oidc allow_multiple_user_backends --value=0` hides the password form and sends `/login` straight to Authelia. Break-glass: `https://cloud.vmd1.homelab/login?direct=1` still shows the local login. Re-enable the form by setting the value back to `1`.
* **Admin rights**: the `nextcloud_admins` lldap group becomes a plain Nextcloud group and does **not** grant admin; admin remains the Nextcloud `admin` group (managed in Nextcloud).
* **LDAP**: Nextcloud has no LDAP integration; the bundled `user_ldap` app is installed but disabled.
