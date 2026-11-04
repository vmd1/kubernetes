# Kube-VIP Load Balancer

Kube-VIP provides virtual IP and Layer 2 ARP load balancing services for Kubernetes clusters in `uk-home` zone.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines `kubevip` ConfigMap (`XXX.XXX.XXX.XXX-XXX.XXX.XXX.XXX`), RBAC, `kube-vip-cloud-provider` Deployment, and `kube-vip-ds` DaemonSet. |

## Design Decisions

- **Control Plane VIP**: Virtual IP `XXX.XXX.XXX.XXX:6443` mapped to control plane nodes via ARP leader election.
- **Node Pinning**: Pinned exclusively to `topology.kubernetes.io/zone: uk-home` (`hades-01`, `hades-02`).
- **IP Range**: Subnet `XXX.XXX.XXX.XXX/24` allocated for `uk-home` LoadBalancer services.
- **LBClass Enforcement**: Enforces `loadBalancerClass: kube-vip` across the controller and DaemonSet.

## Known Issues

- **Stale VIPs after an unclean lease loss**: if kube-vip loses a lease without a clean shutdown (for example it panicked on `hades-02` on 2026-10-25 while the API server was unreachable), the previous holder can keep the VIP on `eth0`, so both nodes answer ARP for it. Compare `ip -4 -br addr show eth0` on both nodes with `kubectl get lease -A | grep kubevip`, and `sudo ip addr del <vip>/32 dev eth0` on the node that does not hold the lease. `XXX.XXX.XXX.XXX` (removed Minecraft service) is still left on `hades-01`.
- **VIP re-apply churn**: `hades-02` re-applies `XXX.XXX.XXX.XXX` about once a minute (`Re-applying the VIP configuration`). Each change to `eth0` makes tailscaled log `LinkChange: major` and rebind its peer connections.
