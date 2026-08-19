# OCI Port Controller (`resources/crds-and-operators/oci-port-controller/`)

The `oci-port-controller` automates opening specified TCP/UDP ports across OCI Cloud Infrastructure Subnet Security Lists and host-level OS firewalls (`iptables`).

## Table of Contents

- [Namespace](#namespace)
- [Architecture & Features](#architecture--features)
- [Files](#files)
- [OCIPortRule Instances](#ociportrule-instances)
- [Related](#related)

## Namespace

`oci-controller`

## Architecture & Features

1. **Custom Resource Definition (`OCIPortRule`)**:
   - Allows declaring open port requirements cluster-wide using `nodeSelector` (e.g. `node-role.kubernetes.io/ingress: "true"`) or `nodeName`.
   - Custom resource group: `network.vmd1.homelab/v1alpha1` (Cluster-scoped, shortname `opr`).
   - Reports per-node sync status in `.status.syncedNodes` / `.status.conditions`.

2. **OCI Subnet Security List Sync**:
   - Loads OCI API credentials from secret `oci-credentials-<region><account>` in the `oci-controller` namespace (shared with [oci-reboot](../../infrastructure/oci-reboot/README.md)).
   - Resolves the instance OCID, VNICs, and Subnet Security Lists using the OCI Python SDK (`ComputeClient` and `VirtualNetworkClient`).
   - Dynamically adds missing ingress security rules for the requested ports (`0.0.0.0/0`), supporting both TCP and UDP.

3. **Node Host Firewall Sync (SSH)**:
   - Reads the node public IP and SSH username from node labels (`node.vmd1.homelab/public-ip`, `node.vmd1.homelab/username`).
   - Uses the private SSH key stored in Secret `node-ssh-key` (namespace `oci-controller`).
   - Executes OpenSSH commands to add missing `iptables` rules and persists them with `netfilter-persistent save`.

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | CustomResourceDefinition (`ociportrules.network.vmd1.homelab`), ServiceAccount, ClusterRole & Binding, `oci-port-controller-code` ConfigMap (controller.py), and Deployment. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |
| [secrets.sops.yaml](../oci-controller/secrets.sops.yaml) | Shared SOPS-encrypted secrets (`node-ssh-key`, `oci-credentials-<region>*`) — see [oci-controller/](../oci-controller/README.md). |

## OCIPortRule Instances

The `OCIPortRule` instances consumed by this controller are defined in the [nodes/](../../nodes/README.md) layer (reconciled after this layer):

- `web-ports` — TCP 80, 443
- `dns-port` — TCP 53
- `dns-port-udp` — UDP 53
- `dot-port` — TCP 853 (DNS over TLS)
- `tailscale-wireguard` — UDP 41641, 41642

## Sample Resource

```yaml
apiVersion: network.vmd1.homelab/v1alpha1
kind: OCIPortRule
metadata:
  name: ingress-nodes-ports
spec:
  nodeSelector:
    node-role.kubernetes.io/ingress: "true"
  protocol: tcp
  ports:
    - 80
    - 443
    - 53
```

## Related

- [nodes/README.md](../../nodes/README.md) — the `OCIPortRule` instances this controller reconciles.
- [oci-controller/README.md](../oci-controller/README.md) — shared secrets for the `oci-controller` namespace.
- [infrastructure/oci-reboot/README.md](../../infrastructure/oci-reboot/README.md) — sibling controller sharing the OCI credentials.
- [../README.md](../README.md) — the CRDs & operators layer this folder belongs to.
