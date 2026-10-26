# netpol-baseline

Default-deny for the namespace plus the allows every app needs.

| Policy | Effect |
| :--- | :--- |
| `default-deny-all` | denies all ingress and egress |
| `allow-egress-dns` | CoreDNS (`kube-system`, `k8s-app=kube-dns`) and node-local-dns (`NODE_LOCAL_DNS_IP`), port 53 |
| `allow-intra-namespace` | ingress and egress between pods of the same namespace (an app and its sidecars, databases, bridges) |
| `allow-ingress-traefik` | `POD_CIDR` on the app port. Traefik is hostNetwork, but its packets to pods are sourced from the node's flannel address (`10.42.N.0`, another node) or `cni0` gateway (`10.42.N.1`, same node and kubelet probes), never a Tailscale address (checked with `ip route get` on a node and from probe logs, 2026-10-26). The cost: any pod can reach the app port |
| `allow-ingress-monitoring` | the `monitoring` namespace on the scrape port |

Per-app patches set the namespace and the two ports (see [../README.md](../README.md)). Kubelet probes come from `10.42.N.1`, which `POD_CIDR` covers, on the app port.
