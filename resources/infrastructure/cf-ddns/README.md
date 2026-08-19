# Cloudflare Dynamic DNS (cf-ddns)

This component periodically checks the public IP address of the home network and updates a Cloudflare A record (`home.d-ingress.vmd1.homelab`) accordingly. This ensures the cluster's ingress is always reachable dynamically.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Declares the `cf-ddns` Namespace, Secret containing API credentials, ConfigMap containing the bash/sh updater script, and the CronJob scheduling the checks. |

## Design Decisions

- **CronJob-based Triggering**: Leverages a K8s `CronJob` resource running every 5 minutes rather than keeping a long-running pod active, saving cluster resources.
- **Alpine & Shell Injection**: Uses a lightweight base image (`alpine:3.20`), installs runtime dependencies (`curl` and `jq`) on startup, and mounts the update logic directly via a ConfigMap.
- **Idempotency**: The shell script fetches the current value of the target DNS record and only pushes updates (via Cloudflare `PATCH` API) if the actual public IP differs from the DNS record.

## Dependencies

- **Public IP Service**: Outbound internet connectivity to `https://api.ipify.org` to detect the external IP.
- **Cloudflare API**: Outbound HTTPS connectivity to the Cloudflare client v4 API (`https://api.cloudflare.com`).

## Services & Routers

This service has no listening services or exposed ingress routes. It is an egress-only background client.

## Storage

No persistent volumes (PVCs) are declared. The execution script is mounted dynamically from the `cf-ddns-script` ConfigMap.

## Constraints & Scheduling

- **Schedule**: Run every 5 minutes (`*/5 * * * *`).
- **Scheduling Constraint**: Uses `nodeSelector` targeting `region: uk-home`. This ensures that the IP lookup reflects the home IP address of `hades-01` rather than the public IP of cloud nodes (like `zeus` or `ares`).
- **Resource Constraints**:
  - Request: `10m` CPU, `32Mi` RAM.
  - Limits: `100m` CPU, `96Mi` RAM.
- **Concurrency Policy**: Set to `Forbid` to prevent multiple execution instances from running simultaneously in case of network latency.

## Configs & Credentials

- **Secret**: `cf-ddns-secrets`
  - `CF_API_TOKEN`: Authorized Cloudflare token with DNS edit permissions.
  - `CF_ZONE_ID`: Zone identifier for `vmd1.homelab`.
  - `CF_RECORD_NAME`: `home.d-ingress.vmd1.homelab` (the target domain being dynamically updated).
- **ConfigMap**: `cf-ddns-script`
  - Mounts `update.sh` containing the validation and update routine.
