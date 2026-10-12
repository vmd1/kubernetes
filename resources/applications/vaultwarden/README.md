# Vaultwarden (Bitwarden Server)

Vaultwarden is an alternative Bitwarden server API implementation written in Rust. It provides a lightweight backend compatible with official Bitwarden clients, integrating with CNPG PostgreSQL and Authelia for SSO.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines Namespace `vaultwarden`, Deployment running `vaultwarden/server:latest`, Service, and Traefik `IngressRoute`. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `vaultwarden-secrets` (stores `DATABASE_URL` and `ADMIN_TOKEN`), Secret `vaultwarden-keys` (RSA signing key), and ConfigMap `vaultwarden-config` (`config.json` with SSO credentials, admin token, and SMTP credentials). |

## Design Decisions

- **PostgreSQL Database Backend**: Configured with `DATABASE_URL` pointing to the cluster's CloudNativePG cluster. This ensures that all login credentials, vaults, and configuration records are fully replicated and backed up off-instance, allowing Vaultwarden to operate as a stateless workload.
- **SSO Integration**: Configured with OIDC authentication pointing to the [Authelia](../authelia/README.md) OIDC authority (`https://identity.vmd1.homelab`, client `vaultwarden`) to permit Single Sign-On (SSO) login.
- **Strict Registration Limits**: Disables new signups (`"signups_allowed": false`) to prevent unauthorized public registrations, while leaving organization invitations open (`"invitations_allowed": true`).
- **SMTP relaying**: Connects to SMTP2Go using encrypted STARTTLS over port 587 for dispatching secure 2FA tokens, organizational invitations, and vault sharing emails.

## Dependencies

- **Database**: CloudNativePG PostgreSQL Cluster (`pg-cluster-rw.cnpg.svc.cluster.local`).
- **OIDC Identity Provider**: [Authelia](../authelia/README.md) (`identity.vmd1.homelab`).
- **Mail Relay**: Outbound access to SMTP2Go (`mail-eu.smtp2go.com:587`).

## Services & Routers

- **Kubernetes Service**: `vaultwarden` (ClusterIP, port `80`).
- **Ingress Route**:
  - Host `vault.vmd1.homelab` on `websecure` entrypoint routing to service port `80`.

## Storage

- **Two replicas in different regions**: the Deployment runs 2 replicas with a *required* pod anti-affinity on `topology.kubernetes.io/region`, so they always land in different regions (`united-kingdom` = `uk-home` + `uk-cloud`, `france` = `eu-cloud`, `india` = `in-cloud`). With 3 regions available a surge pod always has a free region, so the rolling update uses `maxSurge: 1` / `maxUnavailable: 0` and a readiness probe on `/alive`. If only one region is available the second replica stays Pending. Replicas are interchangeable because all state is in PostgreSQL and the RSA key and `config.json` come from the same Secret and ConfigMap.
- **Zone-local routing**: the Service sets `trafficDistribution: PreferClose` and the IngressRoute uses `nativeLB: true`, so Traefik sends to the Service ClusterIP and kube-proxy prefers a replica in the caller's zone. It only knows "same zone" (not distance): from a zone without a replica, requests go to either replica.
- **Attachments disabled**: `USER_ATTACHMENT_LIMIT=0` and `ORG_ATTACHMENT_LIMIT=0` turn off attachment uploads, because `/data` is a per-pod `emptyDir` and an attachment would only exist on one replica. Send *files* are also stored under `/data`, so they have the same limitation. WebSocket push notifications only reach clients connected to the same replica; normal sync is unaffected.
- **Stateless Volume Setup**: Because user accounts, passwords, and vaults are stored inside the PostgreSQL database cluster, the local `/data` mount is backed by a transient `emptyDir: {}` volume.
- **Static Configurations**: ConfigMap `vaultwarden-config` (`config.json`) and Secret `vaultwarden-keys` (`rsa_key.pem`) are projected as read-only subPath files into `/data` at start.

## Constraints & Scheduling

- **Tolerations**: Exists (tolerates all node taints).
- **Resource Constraints**:
  - Request: `100m` CPU, `128Mi` RAM.
  - Limit: `300m` CPU, `384Mi` RAM.

## Configs & Credentials

- **ConfigMap**: `vaultwarden-config`
  - Mounts `config.json` containing authority scopes, client IDs, secrets, SMTP relay credentials, and password iterations.
- **Secret**: `vaultwarden-keys`
  - Holds private RSA key for signing JWT login tokens.
- **Secret**: `vaultwarden-secrets` (Stores `DATABASE_URL` and `ADMIN_TOKEN`).
