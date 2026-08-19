# Kube-VIP Load Balancer

Kube-VIP provides virtual IP and Layer 2 ARP load balancing services for Kubernetes clusters in `uk-home` zone.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines `kubevip` ConfigMap (`192.168.12.1-192.168.12.254`), RBAC, `kube-vip-cloud-provider` Deployment, and `kube-vip-ds` DaemonSet. |

## Design Decisions

- **Control Plane VIP**: Virtual IP `192.168.12.1:6443` mapped to control plane nodes via ARP leader election.
- **Node Pinning**: Pinned exclusively to `topology.kubernetes.io/zone: uk-home` (`hades-01`, `hades-02`).
- **IP Range**: Subnet `192.168.12.0/24` allocated for `uk-home` LoadBalancer services.
- **LBClass Enforcement**: Enforces `loadBalancerClass: kube-vip` across the controller and DaemonSet.
