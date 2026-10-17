# Authelia (`resources/applications/authelia/`)

Authelia is the cluster-wide OpenID Connect 1.0 provider, served at `identity.vmd1.homelab`. It replaces the former Authentik deployment and the former QEComp-only Authelia instance. Authelia's own ForwardAuth is **not** used: Traefik forward-auth is handled by [oauth2-proxy](../oauth2-proxy/README.md), which is an OIDC client of this instance. Apps with native OIDC support are registered as their own clients (see [OIDC Clients](#oidc-clients)). This is separate from the QEComp-only Authelia in [qecomp](../qecomp/README.md).

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Services & Routers](#services--routers)
- [Constraints & Scheduling](#constraints--scheduling)
- [Configs & Credentials](#configs--credentials)
- [Custom Theme](#custom-theme)
- [OIDC Clients](#oidc-clients)
- [Manual Setup Steps](#manual-setup-steps)

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Namespace `authelia`, ConfigMap `authelia-config`, Deployment `authelia` (2 replicas), ClusterIP Service on `:9091`. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` for `identity.vmd1.homelab` (covered by the `*.vmd1.homelab` wildcard certificate). |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `authelia-secrets`. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint. |

## Design Decisions

- **lldap backend**: users and groups come from lldap (`implementation: lldap`, base DN `dc=kmnet,dc=uk`), so passwords and group membership are shared with everything else that uses lldap. Authelia holds no user database of its own.
- **Stateless pods**: storage is PostgreSQL (CNPG) and sessions are in Redis (database index `5`), so both replicas are interchangeable and there is no PVC.
- **Config templating**: `X_AUTHELIA_CONFIG_FILTERS=template` lets the config read the SMTP username and the OIDC signing key from the mounted Secret instead of embedding them in the ConfigMap.
- **Authorization policies**: each oauth2-proxy client has its own policy (`domain_<slug>`) that allows only members of the matching lldap group `Domain: <domain>` (`two_factor`, deny everyone else), so access to one domain never implies another. Every other client has its own policy named `<app>_users` that allows only members of specific lldap groups (see the table below); Grafana requires `two_factor`, the rest `one_factor`. Vaultwarden uses the built-in `one_factor` policy (any lldap user). Tighten or loosen per client in `identity_providers.oidc.authorization_policies`.
- **Claims policy**: the `default` claims policy puts `email`, `email_verified`, `preferred_username`, `groups` and `name` into the ID token, which oauth2-proxy reads for headers.
- **`enableServiceLinks: false`**: the Service is named `authelia`, so Kubernetes would otherwise inject `AUTHELIA_*` variables that collide with Authelia's env-based config and crash-loop the pod (same issue as the qecomp instance).
- **Token endpoint auth method matters**: Authelia rejects a client that authenticates with a method other than the one registered (`invalid_client`, "Client authentication failed"). Nextcloud, BookOrbit, Jellyfin and Home Assistant use `client_secret_post`; the others use `client_secret_basic`. If a new app fails at the token exchange, read the Authelia log: it names the method the app actually used.
- **Config changes need a restart**: the ConfigMap is mounted as a file, so after Flux applies a change run `kubectl -n authelia rollout restart deploy/authelia`.
- **Image pinned** to `authelia/authelia:4.39.28`.

## Dependencies

- **lldap**: `ldap://lldap.lldap.svc.cluster.local:3890`, bind user `uid=authelia,ou=people,dc=kmnet,dc=uk`.
- **CloudNativePG**: `pg-cluster-rw.cnpg.svc.cluster.local:5432`, database and role `authelia`.
- **Redis**: `redis-master.redis.svc.cluster.local:6379`, database index `5`.
- **SMTP2GO**: `submission://mail-eu.smtp2go.com:587` for password reset and 2FA enrolment email (sender `authelia@noreply.vmd1.homelab`, which must be a verified sender in SMTP2GO).

## Services & Routers

- **Service**: `authelia` (ClusterIP, `9091`).
- **IngressRoute**: `identity.vmd1.homelab` with `rate-limit-auth`, `edge-retry` (`vmd1-web`), `compress`, `security-headers`, `nativeLB: true`.

## Constraints & Scheduling

- 2 replicas, `RollingUpdate` (`maxUnavailable: 0`), `nodeSelector` `topology.kubernetes.io/zone: uk-home`, soft preference for `hades-02`, and a **hard** spread across hostnames (`DoNotSchedule`, `maxSkew: 1`, `matchLabelKeys: pod-template-hash`, `nodeTaintsPolicy: Honor`) so the replicas never share a node. If one node is down, the other node can still run both.
- Requests `50m` / `64Mi`, limits `500m` / `256Mi`.

## Configs & Credentials

- **ConfigMap `authelia-config`**: the full `configuration.yml`, including client definitions with pbkdf2 hashed secrets (hashes are not sensitive).
- **Secret `authelia-secrets`**: `jwt_secret`, `session_secret`, `storage_encryption_key`, `oidc_hmac_secret`, `oidc_issuer_private_key.pem` (RSA 4096), `postgres_password`, `ldap_password`, `smtp_username`, `smtp_password`, and `<app>_oidc_client_secret` for `vaultwarden`, `nextcloud`, `jellyfin`, `bookorbit` and `home_assistant` (plaintext handoff for configuring each app; Authelia itself only stores the pbkdf2 hash in the ConfigMap). Grafana's plaintext secret lives in the monitoring Secret `grafana-db-secret` (`oidc_client_secret`).

## Custom Theme

The login UI is restyled to match vmd1.homelab (black background, frosted-glass cards, zinc palette, Inter). Authelia has no stylesheet setting and its CSP only allows same-origin resources, so a small nginx sidecar (`theme-proxy`, in the Authelia pods) does the work:

- **[theme.yaml](theme.yaml)**: ConfigMap `authelia-theme` (`theme.css` and the `inter.woff2` font) and ConfigMap `authelia-nginx` (`nginx.conf`).
- **How it works**: nginx listens on `:8080`, proxies everything to Authelia on `localhost:9091`, adds `<link rel="stylesheet" href="/custom/theme.css?v=1">` before `</head>` (`sub_filter`), and serves `/custom/*` from the ConfigMap. Forwarded headers from Traefik pass through unchanged.
- **Routing**: Service `authelia-web` (`:8080`) is used only by the IngressRoute. The `authelia` Service (`:9091`) still goes straight to Authelia, so in-cluster clients are unaffected. To switch the theme off, point the IngressRoute back at `authelia:9091`.
- **Editing the theme**: change `theme.css` in [theme.yaml](theme.yaml) and bump `?v=` in `nginx.conf` (browsers and the edge cache the stylesheet for an hour); the pods need a restart for the `nginx.conf` change. Authelia's UI is built on shadcn-style CSS variables (`--background`, `--card`, `--primary`, ...), so most restyling means changing those variables. Selectors that target Authelia's markup (cards, OTP boxes, the timer) may need adjusting after an Authelia upgrade.
- **Font**: Inter (variable, latin) from `@fontsource-variable/inter`, SIL OFL 1.1.

## OIDC Clients

| Client ID | Redirect URI | Policy |
| :--- | :--- | :--- |
| `oauth2-proxy-kmnet-uk` | `https://secure.vmd1.homelab/oauth2/callback` | `domain_*` (group `Domain: <domain>`) |
| `oauth2-proxy-vmd1-dev` | `https://secure.vmd1.homelab/oauth2/callback` | `domain_*` (group `Domain: <domain>`) |
| `oauth2-proxy-010356-xyz` | `https://secure.vmd1.homelab/oauth2/callback` | `domain_*` (group `Domain: <domain>`) |
| `oauth2-proxy-848226-xyz` | `https://secure.vmd1.homelab/oauth2/callback` | `domain_*` (group `Domain: <domain>`) |
| `qecomp` | `https://tmtools.vmd1.homelab/auth/callback` (and the `http://` variant QEComp currently sends) | `qecomp_users` (lldap `qecomp-*` groups, `one_factor`) |
| `vaultwarden` | `https://vault.vmd1.homelab/identity/connect/oidc-signin` | `one_factor` |
| `grafana` | `https://grafana.vmd1.homelab/login/generic_oauth` | `grafana_users` (lldap `grafana-admin`, `grafana-editor`, `grafana-viewer`; `two_factor`) |
| `nextcloud` | `https://cloud.vmd1.homelab/apps/user_oidc/code` | `nextcloud_users` (lldap `nextcloud_users`, `nextcloud_admins`) |
| `jellyfin` | `https://jellyfin.vmd1.homelab/sso/OID/redirect/authelia` | `jellyfin_users` (lldap `jellyfin`, `jellyfin_admin`) |
| `bookorbit` | `https://read.vmd1.homelab/oauth2-callback` and `bookorbit://oauth2-callback` | `bookorbit_users` (lldap `family`) |
| `home-assistant` | `https://home.vmd1.homelab/auth/oidc/callback` | `home_assistant_users` (lldap `homeassistant_user`, `homeassistant_admin`) |
| `continuwuity` | `https://matrix.vmd1.homelab/_continuwuity/oidc/complete` | `continuwuity_users` (lldap `synapse-users`). **Not in use yet**: Matrix has not been switched to OIDC. |

Each app is wired up differently; see its own README (Grafana, Vaultwarden, QEComp and BookOrbit through manifests or in-app settings; Nextcloud, Jellyfin and Home Assistant through settings stored in the app, not in this repo).

Authelia matches redirect URIs exactly (no wildcards), which is why oauth2-proxy uses one fixed `secure.<domain>` callback host per domain.

## Manual Setup Steps

Authelia will crash-loop until these exist:

1. **Database** (as the CNPG primary, using the `postgres_password` from the Secret):
   ```sql
   CREATE ROLE authelia LOGIN PASSWORD '<postgres_password>';
   CREATE DATABASE authelia OWNER authelia;
   ```
2. **lldap bind user**: create user `authelia` in the lldap UI with the `ldap_password` from the Secret, and add it to the `lldap_strict_readonly` group (read users/groups) and the `lldap_password_manager` group (required for Authelia's password reset/change, which writes to LDAP; without it, set `authentication_backend.password_reset.disable` and `password_change.disable` to `true`). See the [lldap Authelia guide](https://github.com/lldap/lldap/blob/main/example_configs/authelia.md).
3. **SMTP2GO sender**: verify `authelia@noreply.vmd1.homelab` (or the `vmd1.homelab` domain) as a sender, or change `notifier.smtp.sender`.

Read a secret value without printing the whole file:

```bash
sops -d resources/applications/authelia/secrets.sops.yaml | grep ldap_password
```
