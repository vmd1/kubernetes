# Node Port Rules (`resources/nodes/`)

This directory contains individual `OCIPortRule` custom resource instances managed by [oci-port-controller](../crds-and-operators/oci-port-controller/README.md). It is reconciled by Flux **after** the CRDs & operators layer, so the CRD and controller exist before these instances are applied.

## Table of Contents

- [Files](#files)
- [Usage](#usage)
- [Related](#related)

## Files

| File | Ports | Protocol | Purpose |
| :--- | :--- | :--- | :--- |
| [web-ports.yaml](web-ports.yaml) | `80`, `443` | TCP | HTTP/HTTPS ingress traffic |
| [dns-port.yaml](dns-port.yaml) | `53` | TCP | DNS (TCP) |
| [dns-port-udp.yaml](dns-port-udp.yaml) | `53` | UDP | DNS (UDP) |
| [dot-port.yaml](dot-port.yaml) | `853` | TCP | DNS over TLS |
| [tailscale-wireguard.yaml](tailscale-wireguard.yaml) | `41641`, `41642` | UDP | Tailscale WireGuard |

All rules target ingress nodes via the `node-role.kubernetes.io/ingress: "true"` selector. The controller applies them to OCI Subnet Security Lists and host `iptables` firewalls.

## Usage

To view the applied rules and their per-node sync status:

```bash
kubectl get ociportrules
```

To apply or update rules manually (normally handled by Flux):

```bash
kubectl apply -k nodes/
```

## Related

- [crds-and-operators/oci-port-controller/README.md](../crds-and-operators/oci-port-controller/README.md) — the controller + CRD that consumes these instances.
- [crds-and-operators/oci-controller/README.md](../crds-and-operators/oci-controller/README.md) — shared secrets (`node-ssh-key`, `oci-credentials-<region>*`).
- [../README.md](../README.md) — the resources layer this folder belongs to.
