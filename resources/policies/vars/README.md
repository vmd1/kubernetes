# Cluster range variables

`cluster-ranges.yaml` is the only place in `policies/` where a CIDR or cluster IP may be written. The NetworkPolicy components read it through kustomize `replacements`; the file is `local-config` and never rendered.

| Key | Value | Source (read-only, 2026-10-25) |
| :--- | :--- | :--- |
| `POD_CIDR` | `10.42.0.0/16` | node `spec.podCIDRs` are `10.42.{0..7}.0/24` |
| `SERVICE_CIDR` | `10.43.0.0/16` | Services `kubernetes` 10.43.0.1, `kube-dns` 10.43.0.10 (k3s default) |
| `TAILNET_CIDR`, `TAILNET_CIDR_V6` | `100.64.0.0/10`, `fd7a:115c:a1e0::/48` | same ranges as the `tailnet-only` middleware; all node InternalIPs are inside |
| `PRIVATE_CIDRS_1..3`, `_V6` | RFC 1918, `fc00::/7` | standard private ranges |
| `LINK_LOCAL_CIDR`, `_V6` | `169.254.0.0/16`, `fe80::/10` | standard link-local (cloud metadata) |
| `NODE_LOCAL_DNS_IP` | `169.254.20.10` | convention; node-local-dns is not deployed, the rule is dormant |
| `API_SERVER_CIDR` | `10.0.0.10/32` | `kubectl get endpoints kubernetes` (hades-01, 6443); the one node-bound value |

`POD_CIDR` and `SERVICE_CIDR` are not referenced by a component today (both sit inside `PRIVATE_CIDRS_1`); they are kept for the drift check and for the flannel-gateway fallback described in the plan's risk table. `PRIVATE_CIDRS` is split into numbered keys because a replacement fills one list item at a time.
