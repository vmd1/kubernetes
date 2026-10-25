# Namespaces (`resources/namespaces/`)

Every Namespace in the `vmd1` cluster, applied by the `namespaces` Flux Kustomization ([../../clusters/vmd1/namespaces.yaml](../../clusters/vmd1/namespaces.yaml)) before any other layer. Workload manifests no longer declare their own Namespace.

## Files

| File | Description |
| :--- | :--- |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint. |
| [namespaces.yaml](namespaces.yaml) | One `Namespace` per app or operator (34 in all), including `cert-manager`, `powerdns`, `redis-operator`, `tailscale` and `traefik`, which used to be created by hand or by HelmChart `createNamespace`. |

## Design Decisions

- **Not here**: `default`, `kube-system`, `kube-public` and `kube-node-lease` belong to k3s; `flux-system` comes from [flux-system/gotk-components.yaml](../../clusters/vmd1/flux-system/gotk-components.yaml).
- **Pruning disabled**: each Namespace carries `kustomize.toolkit.fluxcd.io/prune: disabled`. Deleting a Namespace deletes everything in it, so removing one from this file leaves it in the cluster; delete it by hand once its workloads are gone.
- **Adding an app**: add its Namespace here first, then its manifests in the right layer.

## Related

- [../README.md](../README.md) — the layer order.
- [../../../cluster-info.md](../../../cluster-info.md) — cluster inventory.
