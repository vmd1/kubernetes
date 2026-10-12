# Authelia (`resources/applications/authelia/`)

Authelia is the cluster-wide OpenID Connect 1.0 provider, served at `identity.vmd1.homelab`. It replaces [Authentik](../authentik/README.md). Authelia's own ForwardAuth is **not** used: Traefik forward-auth is handled by [oauth2-proxy](../oauth2-proxy/README.md), which is an OIDC client of this instance. This is separate from the QEComp-only Authelia in [qecomp](../qecomp/README.md).

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Services & Routers](#services--routers)
- [Constraints & Scheduling](#constraints--scheduling)
- [Configs & Credentials](#configs--credentials)
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
- **Authorization policies**: each oauth2-proxy client has its own policy (`domain_<slug>`) that allows only members of the matching lldap group `Domain: <domain>` (`two_factor`, deny everyone else), so access to one domain never implies another. `everyone_one_factor` guards Vaultwarden. Tighten or loosen per client in `identity_providers.oidc.authorization_policies`.
- **Claims policy**: the `default` claims policy puts `email`, `email_verified`, `preferred_username`, `groups` and `name` into the ID token, which oauth2-proxy reads for headers.
- **`enableServiceLinks: false`**: the Service is named `authelia`, so Kubernetes would otherwise inject `AUTHELIA_*` variables that collide with Authelia's env-based config and crash-loop the pod (same issue as the qecomp instance).
- **Image pinned** to `authelia/authelia:4.39.28`.

## Dependencies

- **lldap**: `ldap://lldap.lldap.svc.cluster.local:3890`, bind user `uid=authelia,ou=people,dc=kmnet,dc=uk`.
- **CloudNativePG**: `pg-cluster-rw.cnpg.svc.cluster.local:5432`, database and role `authelia`.
- **Redis**: `redis-master.redis.svc.cluster.local:6379`, database index `5`.
- **SMTP2GO**: `submission://mail-eu.smtp2go.com:587` for password reset and 2FA enrolment email (sender `authelia@noreply.vmd1.homelab`, which must be a verified sender in SMTP2GO).

## Services & Routers

- **Service**: `authelia` (ClusterIP, `9091`).
- **IngressRoute**: `identity.vmd1.homelab` with `rate-limit`, `edge-retry` (`vmd1-web`), `compress`, `security-headers`, `nativeLB: true`.

## Constraints & Scheduling

- 2 replicas, `RollingUpdate` (`maxUnavailable: 0`), `nodeSelector` `topology.kubernetes.io/zone: uk-home`, soft preference for `hades-02`, soft spread across hostnames.
- Requests `50m` / `64Mi`, limits `500m` / `256Mi`.

## Configs & Credentials

- **ConfigMap `authelia-config`**: the full `configuration.yml`, including client definitions with pbkdf2 hashed secrets (hashes are not sensitive).
- **Secret `authelia-secrets`**: `jwt_secret`, `session_secret`, `storage_encryption_key`, `oidc_hmac_secret`, `oidc_issuer_private_key.pem` (RSA 4096), `postgres_password`, `ldap_password`, `smtp_username`, `smtp_password`, and `vaultwarden_oidc_client_secret` (plaintext handoff for the Vaultwarden SSO config; Authelia itself only stores the hash).

## OIDC Clients

| Client ID | Redirect URI | Policy |
| :--- | :--- | :--- |
| `oauth2-proxy-kmnet-uk` | `https://secure.vmd1.homelab/oauth2/callback` | `domain_*` (group `Domain: <domain>`) |
| `oauth2-proxy-vmd1-dev` | `https://secure.vmd1.homelab/oauth2/callback` | `domain_*` (group `Domain: <domain>`) |
| `oauth2-proxy-010356-xyz` | `https://secure.vmd1.homelab/oauth2/callback` | `domain_*` (group `Domain: <domain>`) |
| `oauth2-proxy-848226-xyz` | `https://secure.vmd1.homelab/oauth2/callback` | `domain_*` (group `Domain: <domain>`) |
| `vaultwarden` | `https://vault.vmd1.homelab/identity/connect/oidc-signin` | `everyone_one_factor` |

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
