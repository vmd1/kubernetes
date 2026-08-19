# Nextcloud & Collabora Online Stack

Self-hosted productivity, cloud storage, and office suite configured with Backblaze B2 S3 as primary object storage, CloudNativePG PostgreSQL backend, Redis HA caching/locking, Collabora Online (CODE), and Traefik edge ingress.

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
