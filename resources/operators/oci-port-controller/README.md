# OCI Port Controller (`resources/operators/oci-port-controller/`)

The `oci-port-controller` opens specified TCP/UDP ports in OCI subnet security lists (and, for the legacy non-image nodes, host `iptables` over SSH) from `FirewallRule` objects of `type: OCI`.

## Table of Contents

- [Namespace](#namespace)
- [Architecture & Features](#architecture--features)
- [Files](#files)
- [FirewallRule Instances](#firewallrule-instances)
- [Related](#related)

## Namespace

`oci-controller`

## Architecture & Features

1. **Custom Resource Definition (`FirewallRule`)** ([crds/oci-port-controller](../../crds/oci-port-controller/README.md)):
   - `network.vmd1.homelab/v1alpha1`, cluster-scoped, short name `fr`. `spec.type` is `OCI` or `Host`; this controller reconciles `OCI` and ignores `Host` (Phase F).
   - `nodeSelector` (e.g. `node-role.kubernetes.io/ingress: "true"`) or `nodeName`; `ports: [{port, protocol}]`; `sources` (CIDRs, default `0.0.0.0/0`); `description`; `oci.account` overrides the node label `node.vmd1.homelab/oci-account`.
   - Status: `observedGeneration`, `conditions` (`Ready`), and per-node results in `status.nodes[]`.
   - **Deprecated `OCIPortRule`** objects are still reconciled as implicit `FirewallRule`s of type OCI (`spec.protocol` applied to every port, source `0.0.0.0/0`); their status gets a `Deprecated` condition and keeps the legacy `syncedNodes` map.

2. **OCI Subnet Security List Sync**:
   - Loads OCI API credentials from secret `oci-credentials-<region><account>` in the `oci-controller` namespace (shared with [oci-reboot](../../oci/oci-reboot/README.md)).
   - Resolves the instance, VNIC and subnet security lists with the OCI Python SDK, then adds each missing ingress rule per (port, protocol, source). It never removes rules.

3. **Node Host Firewall Sync (SSH, legacy)**:
   - Only for nodes without the `node.vmd1.homelab/image-version` annotation (none are left); uses the key in Secret `node-ssh-key` and `node.vmd1.homelab/public-ip` / `username` labels to add `iptables` rules.

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | ServiceAccount, ClusterRole & Binding (`firewallrules`, `ociportrules` and their status), and the Deployment, which runs the image `ghcr.io/vmd1/oci-port-controller` (pinned by digest, built from [`controllers/oci-port-controller`](../../../../controllers/oci-port-controller); runs as root because it reads the 0600 SSH key). Unit tests: `python3 -m unittest test_controller` in that directory. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |
| [secrets.sops.yaml](../oci-controller/secrets.sops.yaml) | Shared SOPS-encrypted secrets (`node-ssh-key`, `oci-credentials-<region>*`) — see [oci-controller/](../oci-controller/README.md). |

## FirewallRule Instances

Defined in [oci/firewall](../../oci/firewall/README.md) (reconciled after this layer): `web` (80/tcp, 443/tcp), `dns` (53/tcp, 53/udp), `tailscale-wireguard` (41641/udp, 41642/udp).

## Sample Resource

```yaml
apiVersion: network.vmd1.homelab/v1alpha1
kind: FirewallRule
metadata:
  name: web
spec:
  type: OCI
  nodeSelector:
    node-role.kubernetes.io/ingress: "true"
  ports:
    - port: 80
      protocol: TCP
    - port: 443
      protocol: TCP
```

## Related

- [oci/firewall/README.md](../../oci/firewall/README.md) — the `FirewallRule` instances this controller reconciles.
- [oci-controller/README.md](../oci-controller/README.md) — shared secrets for the `oci-controller` namespace.
- [oci/oci-reboot/README.md](../../oci/oci-reboot/README.md) — sibling controller sharing the OCI credentials.
- [../README.md](../README.md) — the CRDs & operators layer this folder belongs to.
