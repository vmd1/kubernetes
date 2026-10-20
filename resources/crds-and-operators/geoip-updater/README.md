# GeoIP Database Updater (`resources/crds-and-operators/geoip-updater/`)

Keeps the MaxMind **GeoLite2** databases up to date on every node, in one shared place, for the services that need them: PowerDNS (GeoIP-backed DNS routing) and, in a follow-up, the Traefik country lookup for requests that do not come through Cloudflare.

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Storage](#storage)
- [Constraints & Scheduling](#constraints--scheduling)
- [Configs & Credentials](#configs--credentials)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | `Namespace` `geoip` and `DaemonSet` `geoip-updater` (official `ghcr.io/maxmind/geoipupdate`, editions `GeoLite2-City` + `GeoLite2-Country`, checks every 12 h). |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted `Secret` `maxmind-credentials` (`account-id`, `license-key`). |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |

## Design Decisions

- **One updater per node, nobody owns it but itself:** PowerDNS and Traefik both consume the databases, so the updater lives in its own namespace instead of inside either of them. It runs on every node (all taints tolerated), including the uk-home nodes, because Traefik runs there too.
- **Image pinned by digest:** `ghcr.io/maxmind/geoipupdate:v8.0.0@sha256:51e70dd6...` is the multi-arch index digest (amd64, arm64, arm/v6; verified to pull and run on hades-01 arm64 and hades-02 amd64), so a moved or re-pushed tag cannot change what runs. To upgrade, resolve the new tag's index digest (`docker buildx imagetools inspect ghcr.io/maxmind/geoipupdate:<tag>`) and replace both the tag and the digest.
- **Official tool, conditional downloads:** `geoipupdate` asks MaxMind whether an edition changed (md5) and only downloads when it did (verified: a second run reports "up to date" without downloading), so the 12-hourly checks do not use MaxMind's daily download allowance. GeoLite2 is released on Tuesdays and Fridays. Needs the MaxMind **account ID** as well as the license key.
- **Two editions:** `GeoLite2-City` (~51 MB, PowerDNS needs latitude/longitude for `pickclosest`) and `GeoLite2-Country` (~3.4 MB, small enough to hold inside the Traefik plugin).
- **Shared hostPath, directory mounts:** files are written to `/var/lib/geoip` on the node (world-readable). Consumers must mount the **directory** read-only, not a single file with `subPath`: `geoipupdate` replaces files atomically, and a `subPath` mount would keep pointing at the old file.
- **PowerDNS** reads `/var/lib/geoip` (previously it only downloaded its own copy when the file was missing, so the node copy was 4 months old) and reloads itself when the file is replaced; see the [powerdns README](../powerdns/README.md).

## Dependencies

- A MaxMind account with a GeoLite2 license key (`maxmind-credentials`; the license key is the same one as in the `powerdns` namespace's `maxmind-license`).
- Outbound HTTPS to MaxMind from every node.

## Storage

- `hostPath` `/var/lib/geoip` (`DirectoryOrCreate`) holding `GeoLite2-City.mmdb`, `GeoLite2-Country.mmdb` and a lock file. A 16 MiB `emptyDir` is used for `/tmp`.

## Constraints & Scheduling

- DaemonSet on all nodes, `RollingUpdate` (`maxUnavailable: 4`), requests `5m/16Mi`, limits `100m/48Mi` (the ingress nodes are 1 GB).
- Runs as root (the hostPath is root-owned) with all capabilities dropped, a read-only root filesystem and no service account token.

## Configs & Credentials

- [secrets.sops.yaml](secrets.sops.yaml): `account-id`, `license-key` (SOPS, age). Apply with `_scripts/apply-secrets.sh`, or let Flux decrypt it.

## Related

- [../powerdns/README.md](../powerdns/README.md): DNS service that uses the City database.
- [../traefik/README.md](../traefik/README.md): ingress controller (country lookup planned).
