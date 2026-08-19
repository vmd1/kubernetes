# K3s Homelab Cluster Configuration

This repository houses the configuration manifests, deployment scripts, and automation pipelines for the `vmd1` k3s-based Kubernetes homelab cluster. The cluster spans physical home-hosted hardware (`hades-01`/`hades-02`) and multiple cloud-based edge ingress nodes (Oracle Cloud Infrastructure) connected via Tailscale.

## Table of Contents

- [Repository Layout](#repository-layout)
- [Secrets Management](#secrets-management)
- [GitOps Architecture (FluxCD)](#gitops-architecture-fluxcd)
- [Components](#components)
- [Maintenance Policy](#maintenance-policy)

## Repository Layout

| Path | Description |
| :--- | :--- |
| [clusters/](clusters/README.md) | Flux cluster definitions. [vmd1/](clusters/vmd1/README.md) holds the Flux `Kustomization` entrypoint and reconciliation layers; [flux-system/](clusters/vmd1/flux-system/README.md) holds the Flux bootstrap manifests. |
| [resources/](resources/README.md) | The manifests Flux reconciles, organized in four layers: [crds-and-operators/](resources/crds-and-operators/README.md) → [nodes/](resources/nodes/README.md) → [infrastructure/](resources/infrastructure/README.md) → [applications/](resources/applications/README.md). |
| [_scripts/](_scripts/README.md) | Helper scripts (SOPS secret application, k6 load testing). |
| [cluster-info.md](cluster-info.md) | Machine-readable cluster inventory (nodes, helm charts, namespaces, labels). |
| [.sops.yaml](.sops.yaml) | SOPS/Age encryption configuration for `secrets.sops.yaml` files. |

## Secrets Management

All secrets in this repository and cluster are managed using **[SOPS](https://github.com/getsops/sops)** encrypted with **[Age](https://github.com/FiloSottile/age)** public-key encryption:
- **Configuration**: Root [.sops.yaml](.sops.yaml)
- **Secrets Naming Convention**: `**/secrets.sops.yaml`
- **Helper Script**: [_scripts/apply-secrets.sh](_scripts/apply-secrets.sh) (Supports `--dry-run`, `--diff`, and `--apply`)
- **In-Cluster Decryption**: Flux decrypts secrets automatically using the `sops-age` secret in `flux-system`.

## GitOps Architecture (FluxCD)

The cluster manifests are organized for continuous deployment via **[FluxCD v2](https://fluxcd.io/)** (v2.9.4):

```
clusters/vmd1/                    <- Flux entrypoint (applied by flux-system bootstrap)
├── kustomization.yaml
├── crds-and-operators.yaml       -> ./resources/crds-and-operators
├── nodes.yaml                    -> ./resources/nodes            (dependsOn crds-and-operators)
├── infrastructure.yaml           -> ./resources/infrastructure   (dependsOn nodes)
├── applications.yaml             -> ./resources/applications     (dependsOn infrastructure)
└── flux-system/                  <- gotk-components + gotk-sync (bootstrap)
```

- **Cluster Definition**: [clusters/vmd1/](clusters/vmd1/README.md)
- **Bootstrap**: [clusters/vmd1/flux-system/](clusters/vmd1/flux-system/README.md) — `gotk-sync.yaml` creates the `GitRepository` (this repo, branch `main`) and the root `Kustomization`.
- **Reconciliation Order**: `crds-and-operators` → `nodes` → `infrastructure` → `applications`, each declared via `dependsOn`.
- **Decryption**: In-cluster automated SOPS decryption via the `sops-age` secret in `flux-system`.

## Components

### Core Infrastructure & Security
* [Tailscale](resources/infrastructure/tailscale/README.md) — Tailnet overlay networking and region-aware proxy connector reconciliation.
* [Traefik Controller](resources/crds-and-operators/traefik/README.md) — DaemonSet ingress controller, reverse proxy, SSL termination (chart).
* [Traefik Helpers](resources/infrastructure/traefik/README.md) — Middlewares (rate-limit, security-headers, compress), TLS options, dashboard, and the `uk-home` LoadBalancer.
* [Cert-Manager](resources/crds-and-operators/cert-manager/README.md) — Automated TLS wildcard certificate provisioning via ACME Let's Encrypt and Cloudflare DNS-01.
* [PowerDNS](resources/crds-and-operators/powerdns/README.md) — GeoIP-backed authoritative DNS routing clients to the closest healthy edge ingress node.
* [Cloudflare DDNS](resources/infrastructure/cf-ddns/README.md) — Cron-based updater maintaining the dynamic home gateway IP.
* [Multus CNI](resources/crds-and-operators/multus/README.md) — Secondary network interfaces, including the Longhorn storage network.
* [Kube-VIP](resources/crds-and-operators/kube-vip/README.md) — Layer 2 virtual IP load balancing on the `uk-home` zone.

### Identity & Infrastructure Services
* [Authentik](resources/applications/authentik/README.md) — Centralized Identity Provider (IdP) and single sign-on (SSO) forward auth middleware.
* [Light LDAP (lldap)](resources/infrastructure/lldap/README.md) — High-availability LDAP directory server for user management.
* [Vaultwarden](resources/applications/vaultwarden/README.md) — Lightweight, secure Bitwarden-compatible password vault.
* [Docker Registry](resources/infrastructure/registry/README.md) — Private container image repository with basic auth gates.

### Databases & Persistent Storage
* [CloudNativePG](resources/crds-and-operators/cnpg/README.md) — High-availability PostgreSQL database operator with WAL archiving.
* [Redis HA Cluster](resources/crds-and-operators/redis/README.md) — Master-Replica cache cluster with Redis Sentinel failover and HAProxy routing.
* [Longhorn](resources/crds-and-operators/longhorn/README.md) — Distributed block storage operator with recurring backups (UI + backup target in [infrastructure/longhorn](resources/infrastructure/longhorn/README.md)).

### Networking & OCI Automation
* [OCI Port Controller](resources/crds-and-operators/oci-port-controller/README.md) — Opens ports on OCI security lists and host firewalls via `OCIPortRule` resources ([instances](resources/nodes/README.md)).
* [OCI Reboot Controller](resources/infrastructure/oci-reboot/README.md) — Watchdog controller resetting stuck cloud hypervisors via the Oracle API.

### Application Services
* [Home Assistant](resources/applications/home-assistant/README.md) — Home automation core running on the local subnet with config file editors.
* [MQTT Mosquitto](resources/applications/mqtt/README.md) — IoT message broker and telemetry bus.
* [Matrix Stack](resources/applications/matrix/README.md) — Decentralized chat server (continuwuity), FluffyChat client, and chat bridges.
* [Media Stack](resources/applications/media/README.md) — Jellyfin streaming, Overseerr request portal, and local download brokers.
* [Edge Web Services](resources/applications/vmd1-dev/README.md) — Developer portal and personal websites hosted on edge nodes.
* [Cinepro](resources/applications/cinepro/README.md) — Metadata query API with Redis cache support.
* [Headlamp UI](resources/applications/headlamp/README.md) — Kubernetes cluster management frontend and user dashboard.
* [Obsidian Sync Server](resources/applications/obsidian/README.md) — Self-hosted CouchDB database backend for Obsidian Self-Hosted LiveSync.
* [Nextcloud](resources/applications/nextcloud/README.md) — Cloud storage and productivity platform with Backblaze B2 S3 primary storage, CNPG PostgreSQL, and Redis caching.
* [UniFi](resources/applications/unifi/README.md) — UniFi Network Application for managing UniFi networking hardware.

### Operations & Monitoring
* [Monitoring Stack](resources/applications/monitoring/README.md) — Promtail log shippers, Loki log DB, Prometheus metrics, and Grafana.
* [Uptime Kuma](resources/applications/uptime-kuma/README.md) — Service uptime and latency monitoring boards.
* [Ntfy Alerts](resources/applications/ntfy/README.md) — Pub-sub push notification gateway and SMTP ingress endpoints.

## Maintenance Policy

> [!IMPORTANT]
> To ensure the cluster documentation remains accurate, any modifications to Kubernetes manifests, `cluster-info.md`, or service parameters **MUST** be accompanied by an update to the corresponding service `README.md` and this root Table of Contents. Every folder in this repository is expected to ship a `README.md` describing its contents; when adding a new component, create its folder README and link it from the relevant layer README and this ToC.
