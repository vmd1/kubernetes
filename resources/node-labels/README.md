# Node Labels (`resources/node-labels/`)

One `Node` manifest per node carrying the labels workloads select on, applied by the `node-labels` Flux Kustomization ([../../clusters/vmd1/node-labels.yaml](../../clusters/vmd1/node-labels.yaml)).

## Files

| File | Description |
| :--- | :--- |
| [kustomization.yaml](kustomization.yaml) | Lists the eight node files. |
| `<node>.yaml` | Labels for that node: `node-role.kubernetes.io/*`, `topology.kubernetes.io/*`, `node.vmd1.homelab/*`, `storage.vmd1.homelab/*`, `node-type`, Longhorn. |

## Design Decisions

- **Labels only, no taints**: `Node.spec.taints` is an atomic list, so Flux would own all of it and remove the `node.kubernetes.io/unreachable` / `not-ready` taints the node controller adds. Taints stay in each node's k3s flags.
- **`node.vmd1.homelab/public-ip` left out**: a script keeps it current (it changes on the home connection), and Flux would fight it.
- **k3s-owned labels left out**: `kubernetes.io/*`, `node.kubernetes.io/*`, `k3s.io/*` and the control-plane / etcd role labels.
- **Never pruned**: each Node is annotated `kustomize.toolkit.fluxcd.io/prune: disabled`, so removing a file can never delete a Node. Removing a label from a file does remove that label from the node.
- **`wait: false`**: Flux does not health-check Nodes here, so a NotReady node never stalls this layer.
- **New node**: join it, then add its file. Flux only patches existing Nodes; a file for a node that has not joined creates an empty Node object, so do not add one early.

## Related

- [../README.md](../README.md): layer order.
- [../../../cluster-info.md](../../../cluster-info.md): node inventory.
