# Tailscale Integration

Tailscale integrates the local Kubernetes cluster with a secure Tailscale overlay network (tailnet). This directory manages the Tailscale operator and a custom Python controller that automates Tailscale Connector, ProxyClass, and PeerRelay provisioning based on node geographic regions.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [operator.yaml](operator.yaml) | Defines the HelmChart custom resource to deploy `tailscale-operator` version `1.102.3` into the `tailscale` namespace. |
| [automation.yaml](automation.yaml) | Deploys a custom controller (`tailscale-region-controller`) including RBAC ServiceAccount, ConfigMap containing the watcher Python code, and deployment resources. |

## Design Decisions

- **Region-Aware Network Orchestration**:
  - The custom controller (`watcher.py`) scans Kubernetes node objects for the `topology.kubernetes.io/zone` label (e.g. `uk-home`, `uk-cloud`, `in-cloud`, `eu-cloud`).
  - It automatically generates Tailscale `Connector`, `ProxyClass`, and `PeerRelay` custom resources for each distinct zone.
  - Dynamically configures connection parameters, such as a custom MTU value (`1130`) to resolve OCI overlay packet fragmentation.
- **In-Cluster Peer Relays**:
  - One `PeerRelay` (`ts-peerrelay-<zone>`) is deployed per active zone, scheduled via the same per-zone `ProxyClass` (`ts-proxyclass-<zone>`) used by the zone's exit-node `Connector`.
  - Peer relays help nodes in the tailnet establish direct/relayed connections when NAT traversal fails (e.g. behind the OCI cloud nodes' CGNAT), reducing reliance on Tailscale's public DERP relays. Requires operator `>=1.102` for the `PeerRelay` CRD.
- **Failover Logic**:
  - Monitors the node status. If a node in a region becomes unreachable/NotReady, the controller schedules pod failovers after a 60-second grace period (`FAILOVER_GRACE_SECONDS=60`) instead of the Kubernetes default 5 minutes.
  - Maintains state tracking for deleted regions with a 1-week retention period (`REGION_GRACE_PERIOD`) to prevent deleting Tailscale device IDs during transient host maintenance windows.

## Dependencies

- **Tailscale API / Tailnet**: Requires an OAuth key or auth client credentials to authenticate the operator with the Tailscale admin console.
- **Tailscale Operator CRDs**: Relies on CRDs like `Connector` and `ProxyClass` registered by the Tailscale Operator.

## Services & Routers

This controller itself does not expose public services or ingress routes. The Tailscale Operator spawns proxy pods that route internal traffic or expose specific services to the Tailscale subnet.

## Storage

No persistent volume claims are used. The automation scripts are mounted dynamically from the `tailscale-region-controller-code` ConfigMap.

## Constraints & Scheduling

- **Resource Constraints**:
  - Request: `10m` CPU, `64Mi` RAM.
  - Limit: `100m` CPU, `128Mi` RAM.
- Tolerates scheduling constraints to observe node tables.

## Configs & Credentials

- **ConfigMap**: `tailscale-region-controller-code`
  - Houses `watcher.py` python script managing Tailscale connector objects.
- **Env**:
  - `RECONCILE_INTERVAL`: reconciliation frequency (default `30s`).
  - `TAILSCALE_MTU`: MTU configuration (default `1130`).
  - `FAILOVER_GRACE_SECONDS`: cluster failover threshold.
  - `REGION_GRACE_PERIOD`: how long to wait before purging defunct region endpoints.
