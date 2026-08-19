# Matrix Stack (continuwuity + bridges)

This directory hosts the self-hosted Matrix federation setup, utilizing the highly-tuned `continuwuity` homeserver implementation along with multiple bridges (WhatsApp, Discord, Google Chat, Google Messages, LinkedIn, EmailDawg) and a FluffyChat Web client.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Contains the deployments for `continuwuity`, `fluffychat`, and 6 `mautrix` bridge containers, along with ConfigMaps (continuwuity and fluffychat configs), services, and IngressRoutes. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `matrix-db-secret` and ConfigMaps for each mautrix bridge (`mautrix-whatsapp-config`, `mautrix-discord-config`, `mautrix-googlechat-config`, `mautrix-gmessages-config`, `mautrix-linkedin-config`, `mautrix-meta-config`). |
| [migrate.ps1](migrate.ps1) | A migration automation script to copy files from local directories into the cluster's Persistent Volumes via `kubectl cp` and then trigger the application of `manifest.yaml`. |

## Design Decisions

- **Performance-Oriented Homeserver**: Employs `continuwuity` (built on the lightweight matrix spec) using the `:latest-maxperf` tags, optimized to run with low memory overhead while preserving federated capability.
- **Dedicated Bridge Pods**: Spawns independent `mautrix-{whatsapp,discord,googlechat,gmessages,linkedin,emaildawg}` agent containers to link external messaging networks to Matrix rooms.
- **Federation and Client Ingress Routing**:
  - Exposes the client-server APIs on `matrix.vmd1.homelab`.
  - Exposes standard server-to-server federation on `federation.vmd1.homelab` (exposing port `8448` over SSL).
  - Routes requests matching `/.well-known/matrix` directly to provide correct client/server discovery mappings.

## Dependencies

- **Database**: Connects to the CNPG PostgreSQL cluster for relational storage of messages, users, and rooms state.
- **DNS Records**: Requires public DNS configuration pointing `matrix.vmd1.homelab`, `federation.vmd1.homelab`, and `chat.vmd1.homelab` to the cluster ingress nodes.

## Services & Routers

- **Kubernetes Services**: Exposes 8 separate services for `continuwuity`, `fluffychat`, and the 6 individual bridges.
- **Ingress Routes**:
  - `continuwuity`: Matches domains `matrix.vmd1.homelab`, `federation.vmd1.homelab`, and path `/.well-known/matrix`.
  - `fluffychat`: Exposes FluffyChat web client at `chat.vmd1.homelab`.
  - `bridges`: Handles API bridge calls at `api.vmd1.homelab/v1/bridges/*` matching stripPrefix middleware rules.

## Storage

- **Continuwuity Storage**: PVC `continuwuity-data` (Longhorn storage, `20Gi`, ReadWriteOnce) containing homeserver keys, database local states, media caches, and runtime details.
- **Bridges Storage**: Individual bridge data folders are allocated `2Gi` volumes using the Longhorn `longhorn-single-replica` storage class to persist bridge sessions, encryption keys, and SQLite cache databases.

## Constraints & Scheduling

- **Migration Constraint**: Data must be seeded before the main application deployments start to prevent DB errors or unconfigured starts.
- **Replica Constraint**: Standard single-replica deployments across all bridge instances to prevent multi-instance sessions or session hijack blockages on external chat platforms.

## Configs & Credentials

- ConfigMaps contain `continuwuity-config` and individual `mautrix-*` config and registration files.
- Credentials and private keys are embedded in configuration files inside the persistent volumes.
