# OCI (`resources/oci/`)

Oracle Cloud node management: the reboot watchdog and the firewall port rules for the ingress nodes. oci-port-controller itself and its CRD are in [../operators/](../operators/README.md) and [../crds/](../crds/README.md). Applied by the `oci` Flux Kustomization ([../../clusters/vmd1/oci.yaml](../../clusters/vmd1/oci.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [oci-reboot/](oci-reboot/README.md) | Watchdog controller that force-reboots unresponsive OCI nodes via the Oracle API. |
| [port-rules/](port-rules/README.md) | `OCIPortRule` instances (web 80/443, DNS 53 tcp/udp, DoT 853, Tailscale WireGuard 41641-41642) that oci-port-controller opens on the ingress nodes' OCI security lists and host firewalls. |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
