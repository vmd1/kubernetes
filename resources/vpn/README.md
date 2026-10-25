# VPN (`resources/vpn/`)

Tailscale: the operator and the region controller that keeps Connectors and ProxyClasses in step with node labels. Applied by the `vpn` Flux Kustomization ([../../clusters/vmd1/vpn.yaml](../../clusters/vmd1/vpn.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [tailscale/](tailscale/README.md) | Tailscale operator + region-aware connector/proxy-class automation controller. |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
