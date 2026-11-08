# SFTPGo (files.vmd1.homelab)

Shared-folder sharing over links, with Backblaze B2 (S3) storage. Replaces Nextcloud and Collabora (removed 2026-11-08 to relieve memory pressure on hades-01). Only the web interfaces are enabled; the SFTP listener is off.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | PVC `sftpgo-pvc` (2 Gi, `longhorn-single-replica`, SQLite database and host keys), Deployment `sftpgo` (`drakkan/sftpgo:v2.7.6-slim`, digest-pinned, Recreate, uid 1000, HTTP only), Service `sftpgo:80`. |
| [ingressroute.yaml](ingressroute.yaml) | `files.vmd1.homelab`: an allow-list of public paths (priority 100) and a tailnet-only catch-all for everything else, including the admin UI and the REST API. |
| [secrets.sops.yaml](secrets.sops.yaml) | `sftpgo-secrets`: default admin login, the OIDC client secret and `initial-data.json` (the owner user with the S3 filesystem: bucket, region, endpoint, key). |
| [kustomization.yaml](kustomization.yaml) | Baseline + egress-public NetworkPolicies and the admission-label patch. |

## How sharing works

You (the owner) sign in at `https://files.vmd1.homelab` with Authelia, open the folder in the web client and create a **share** with scope **Read/Write**. The link works for anyone who has it, no account: they see every file in that folder, download them (single files or a zip) and add files, all through the same link. They cannot delete, rename or create folders, and cannot see anything outside the shared folder. A **Read** share is download-only and a **Write** share is upload-only (nobody sees the files). Each share can have an expiry, a password and a maximum number of accesses. Shares stop working when the owner account is disabled or deleted.

Verified in the SFTPGo source (`internal/httpd/webclient.go`): a read/write public share sets `CanAddFiles` and `CanDownload` and never `CanDelete`, `CanRename` or `CanCreateDirs`. The OpenAPI file in the repo still lists only scopes 1 and 2.

## First run

1. Authelia needs the lldap groups `sftpgo_users` and `sftpgo_admins` (create them and add yourself).
2. The owner user in the secret is named `admin`. OIDC maps the Authelia `preferred_username` claim to the SFTPGo username, and the user must already exist: if your lldap username differs, rename the user in the admin UI (below) or change `username` in `initial-data.json` (`sops secrets.sops.yaml`).
3. Admin UI, tailnet only: `https://files.vmd1.homelab/web/admin`, login `admin` with `SFTPGO_DEFAULT_ADMIN_PASSWORD` from `sops -d secrets.sops.yaml`.
4. Web client: `https://files.vmd1.homelab/web/client` and the Authelia button. The web client password form is disabled; the OIDC client secret is `sftpgo_oidc_client_secret` in the Authelia secret.

## Design Decisions

- **Public surface**: only `/`, `/healthz`, `/web/client`, `/web/oidc`, `/static` and `/api/v2/shares` are public. The admin UI, the REST API and token endpoints are reachable from the tailnet only (tailnet clients resolve `files.vmd1.homelab` through the shadow zone, see [dns/README.md](../../../../dns/README.md)).
- **Login**: web client OIDC only (`disabled_login_methods` 168 = web client form, user token endpoint, user API keys). The defender is on.
- **Storage**: the old `vmd1-nextcloud` bucket under the `sftpgo/` prefix, so it never touches Nextcloud's `urn:oid:*` objects. Delete those once Nextcloud is confirmed gone. Metadata (users, shares) is in SQLite on the PVC: losing it loses the share links and users, not the files.
- **Initial data**: `SFTPGO_LOADDATA_MODE=0` re-applies the owner user from the secret on every start, so rotating the B2 key means editing the secret. Changes made to that user in the UI are overwritten.
- **DNS, no Cloudflare proxy**: `files` is an unproxied CNAME to `home.d-ingress.vmd1.homelab` (the home IP kept by cf-ddns), straight to uk-home. Not proxied on purpose: Cloudflare's free plan caps a request body at 100 MB and SFTPGo's web client uploads a file as one request, so big uploads would fail. The cost is that the home IP is public (it already is for `jellyfin.vmd1.homelab`) and Cloudflare's DDoS and WAF layer is not in front. Traefik terminates TLS with the cluster certificate.
- **Client IP**: `client_ip_proxy_header` `X-Forwarded-For`, depth 0 (rightmost): the name is not proxied, so Traefik (which only trusts forwarded headers from Cloudflare) sets it to the real peer address; check the IPs in the admin UI's connections page and the defender log.
- **Placement**: `uk-home`, preferring hades-02 (hades-01 is memory-starved, see [k3s-config](../../k3s-config/README.md)).

## Dependencies

[Authelia](../../auth/authelia/README.md) (`identity.vmd1.homelab`), Backblaze B2, [Traefik](../../proxy/traefik/README.md) middlewares `rate-limit`, `compress`, `security-headers`, `tailnet-only`, and the DNS record in [dns/domains/vmd1.homelab.js](../../../../dns/domains/vmd1.homelab.js).
