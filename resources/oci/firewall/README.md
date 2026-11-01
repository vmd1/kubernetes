# Firewall rules (`resources/oci/firewall/`)

`FirewallRule` objects (`network.vmd1.homelab/v1alpha1`, cluster-scoped, short name `fr`) reconciled by [oci-port-controller](../../operators/oci-port-controller/README.md). Every object here has `type: OCI`: the controller adds the ports to the OCI subnet security list of each selected node. (`type: Host`, enforced on the node, arrives in Phase F of the [edge node roadmap](../../../../docs/edge-node-roadmap.md).) Reconciled by Flux **after** the CRDs & operators layer, so the CRD and controller exist before these instances are applied. This directory replaces `oci/port-rules/` (the `OCIPortRule` objects).

## Table of Contents

- [Files](#files)
- [Usage](#usage)
- [Migration from OCIPortRule](#migration-from-ociportrule)
- [Related](#related)

## Files

| File | Ports | Purpose |
| :--- | :--- | :--- |
| [web.yaml](web.yaml) | `80/tcp`, `443/tcp` | HTTP/HTTPS ingress |
| [dns.yaml](dns.yaml) | `53/tcp`, `53/udp` | DNS |
| [tailscale-wireguard.yaml](tailscale-wireguard.yaml) | `41641/udp`, `41642/udp` | Tailscale WireGuard |

All rules target ingress nodes via the `node-role.kubernetes.io/ingress: "true"` selector and allow `0.0.0.0/0` (the `sources` default). The controller only ever adds missing security-list entries, it never removes them.

## Usage

```bash
kubectl get firewallrules      # or: kubectl get fr   (Type, Ready, Reason)
kubectl get fr web -o yaml     # status.nodes[], status.conditions, status.observedGeneration
```

Fields: `type` (`OCI`|`Host`), `ports: [{port, protocol: TCP|UDP}]`, `sources: [CIDR]` (default `0.0.0.0/0`), `nodeName` / `nodeSelector`, `description`, and `oci.account` to override the node label `node.vmd1.homelab/oci-account`.

## Migration from OCIPortRule

The five old objects (`dns-port`, `dns-port-udp`, `dot-port`, `tailscale-wireguard`, `web-ports`) became three: the tcp/udp pair was merged into `dns`, `web-ports` became `web`, and `dot-port` (853, the DoT entrypoint no longer exists) was dropped. Flux prunes the old objects. The controller still reconciles any leftover `OCIPortRule` as an implicit `FirewallRule` and marks it with a `Deprecated` condition. Once none is left, delete the CRD by hand (see [../../crds/oci-port-controller/README.md](../../crds/oci-port-controller/README.md)).

## Related

- [operators/oci-port-controller/README.md](../../operators/oci-port-controller/README.md) — the controller that consumes these objects.
- [operators/oci-controller/README.md](../../operators/oci-controller/README.md) — shared secrets (`node-ssh-key`, `oci-credentials-<region>*`).
- [../README.md](../README.md) — the resources layer this folder belongs to.
