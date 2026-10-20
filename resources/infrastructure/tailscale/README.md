# Tailscale Integration

Tailscale integrates the local Kubernetes cluster with a secure Tailscale overlay network (tailnet). This directory manages the Tailscale operator and a custom Python controller that automates Tailscale Connector and ProxyClass provisioning based on node geographic regions.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [operator.yaml](operator.yaml) | Defines the HelmChart custom resource to deploy `tailscale-operator` version `1.102.3` into the `tailscale` namespace. |
| [automation.yaml](automation.yaml) | Deploys a custom controller (`tailscale-region-controller`) including RBAC ServiceAccount and the Deployment. The controller runs the image `ghcr.io/vmd1/tailscale-region-controller` (pinned by digest, built from [`controllers/tailscale-region-controller`](../../../../controllers/tailscale-region-controller)). |

## Design Decisions

- **Region-Aware Network Orchestration**:
  - The custom controller (`watcher.py`) scans Kubernetes node objects for the `region` label (e.g. `region=uk-home`, `region=uk-london-cloud`).
  - It automatically generates Tailscale `Connector` and `ProxyClass` custom resources for each distinct region.
  - Dynamically configures connection parameters, such as a custom MTU value (`1130`) to resolve OCI overlay packet fragmentation.
- **Failover Logic**:
  - Monitors the node status. If a node in a region becomes unreachable/NotReady, the controller schedules pod failovers after a 60-second grace period (`FAILOVER_GRACE_SECONDS=60`) instead of the Kubernetes default 5 minutes.
  - Maintains state tracking for deleted regions with a 1-week retention period (`REGION_GRACE_PERIOD`) to prevent deleting Tailscale device IDs during transient host maintenance windows.

## Dependencies

- **Tailscale API / Tailnet**: Requires an OAuth key or auth client credentials to authenticate the operator with the Tailscale admin console.
- **Tailscale Operator CRDs**: Relies on CRDs like `Connector` and `ProxyClass` registered by the Tailscale Operator.

## Services & Routers

This controller itself does not expose public services or ingress routes. The Tailscale Operator spawns proxy pods that route internal traffic or expose specific services to the Tailscale subnet.

## Storage

No persistent volume claims are used. The controller code is baked into the container image; nothing is mounted.

## Constraints & Scheduling

- **Resource Constraints**:
  - Request: `10m` CPU, `64Mi` RAM.
  - Limit: `100m` CPU, `128Mi` RAM.
- Tolerates scheduling constraints to observe node tables.

## Configs & Credentials

- **Image**: `ghcr.io/vmd1/tailscale-region-controller` (runs `watcher.py`, which manages the Tailscale connector objects; non-root, UID 65532).
- **Env**:
  - `RECONCILE_INTERVAL`: reconciliation frequency (default `30s`).
  - `TAILSCALE_MTU`: MTU configuration (default `1130`).
  - `FAILOVER_GRACE_SECONDS`: cluster failover threshold.
  - `REGION_GRACE_PERIOD`: how long to wait before purging defunct region endpoints.
