# Tailscale Integration

Tailscale integrates the local Kubernetes cluster with a secure Tailscale overlay network (tailnet). This directory manages the Tailscale operator and a custom Python controller that automates Tailscale Connector and ProxyClass provisioning based on node geographic regions.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [operator.yaml](operator.yaml) | Defines the HelmChart custom resource to deploy `tailscale-operator` version `1.104.2` into the `tailscale` namespace, with the in-process API server proxy on (`apiServerProxyConfig.mode: "true"`) so `kubectl` works over the tailnet. |
| [rbac.yaml](rbac.yaml) | `ClusterRoleBinding` `tailnet-admins`: group `tailnet-admins` (added by the tailnet policy grant `tailscale.com/cap/kubernetes` for `group:admin`) is `cluster-admin`. Group names come from the policy, so this is the only place that decides what a tailnet identity may do in the cluster. |
| [apiserver-proxyclass.yaml](apiserver-proxyclass.yaml) | `ProxyClass` `k8s-api-uk-home`: pins the kubectl ProxyGroup's pods to `topology.kubernetes.io/zone: uk-home` and spreads them one per node (`topologySpreadConstraints` on hostname, `DoNotSchedule`), so both replicas sit on the home nodes (hades-01, hades-02) on purpose and not just because the cloud nodes are tainted. |
| [apiserver-proxygroup.yaml](apiserver-proxygroup.yaml) | `ProxyGroup` `k8s-api` (`type: kube-apiserver`, 2 replicas, tag `tag:k8s-apiserver`, hostname `k8s-api`): the dedicated kubectl proxy, advertised as a Tailscale Service so a replica can drain or fail without changing the URL. Replaces the in-process proxy in the operator pod once verified. |
| [automation.yaml](automation.yaml) | Deploys a custom controller (`tailscale-region-controller`) including RBAC ServiceAccount and the Deployment. The controller runs the image `ghcr.io/vmd1/tailscale-region-controller` (pinned by digest, built from [`controllers/tailscale-region-controller`](../../../../controllers/tailscale-region-controller)). |

## Design Decisions

- **kubectl over Tailscale**: the operator's in-process API server proxy impersonates the caller (user devices become their login, grant groups are added), so RBAC is per person and audited by Kubernetes rather than one shared kubeconfig credential. Direct `10.0.0.10:6443` stays as break-glass because the proxy is a single replica in the operator pod. Needs MagicDNS and HTTPS Certificates both enabled for the tailnet (the first request times out while the cert is issued). See [tailscale/README.md](../../../../tailscale/README.md).

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
