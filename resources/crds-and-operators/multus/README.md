# Multus CNI (`resources/crds-and-operators/multus/`)

This folder deploys the **Multus CNI meta-plugin** (via the `rke2-multus` Helm chart) plus the network attachment definitions that enable secondary interfaces for cluster workloads.

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Usage](#usage)
- [Related](#related)

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | HelmChart for `rke2-multus` (with `whereabouts` IPAM enabled) and the `NetworkAttachmentDefinition` `storage-macvlan-eth0` in `longhorn-system`. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint for this folder. |

## Design Decisions

- **Multus Meta-Plugin**: Deployed as a DaemonSet via the `rke2-multus` chart from the RKE2 charts repo, so pods can attach multiple network interfaces.
- **K3s-Specific CNI Paths**: The chart is configured with the K3s CNI directories (`/var/lib/rancher/k3s/agent/etc/cni/net.d` and `/var/lib/rancher/k3s/data/cni/`) plus `multusAutoconfigDir`, which is required for `rke2-multus` >= v4.2.202 on K3s.
- **Restricted to `uk-home`**: Both the Multus and Whereabouts DaemonSets are pinned via `nodeSelector` to `topology.kubernetes.io/zone: uk-home` (i.e. `hades-01`, `hades-02`).
- **Whereabouts IPAM**: Enables dynamic IP allocation for secondary interfaces.
- **Storage Network for Longhorn**: The `storage-macvlan-eth0` `NetworkAttachmentDefinition` creates a macvlan on `eth0` (bridge mode) with a Whereabouts IP range of `192.168.11.0/24` (excluding infrastructure reservations). Pods attach to it via the annotation `k8s.v1.cni.cncf.io/networks: storage-macvlan-eth0` — used by Longhorn's `storageNetwork` setting so storage traffic bypasses the Tailscale overlay.

## Dependencies

- **K3s**: The chart assumes the K3s CNI directory layout.
- **Longhorn**: The `storage-macvlan-eth0` network is referenced by the Longhorn operator (`defaultSettings.storageNetwork`) in [crds-and-operators/longhorn/manifest.yaml](../longhorn/manifest.yaml).

## Usage

To attach a pod to the storage network:

```yaml
metadata:
  annotations:
    k8s.v1.cni.cncf.io/networks: storage-macvlan-eth0
```

## Related

- [../longhorn/README.md](../longhorn/README.md) — Longhorn operator that consumes `storage-macvlan-eth0`.
- [../README.md](../README.md) — the CRDs & operators layer this folder belongs to.
- [../../../cluster-info.md](../../../cluster-info.md) — cluster inventory.
