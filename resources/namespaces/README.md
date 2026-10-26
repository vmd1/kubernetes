# Namespaces (`resources/namespaces/`)

Every Namespace in the `vmd1` cluster, applied by the `namespaces` Flux Kustomization ([../../clusters/vmd1/namespaces.yaml](../../clusters/vmd1/namespaces.yaml)) before any other layer. Workload manifests no longer declare their own Namespace.

## Files

| File | Description |
| :--- | :--- |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint. |
| [namespaces.yaml](namespaces.yaml) | One `Namespace` per app or operator (34 in all), including `cert-manager`, `powerdns`, `redis-operator`, `tailscale` and `traefik`, which used to be created by hand or by HelmChart `createNamespace`; plus `default`, `kube-system`, `kube-public` and `kube-node-lease` for their labels only. |

## Design Decisions

- **Labels**: every Namespace carries `vmd1.homelab/tier` (`app`, `infra` or `system`) and the Pod Security labels (`audit` and `warn` at `restricted`). The admission policies in [../policies/](../policies/README.md) select namespaces by tier, never by name.
- **PSA `enforce=baseline`**: set on `tier=app` namespaces whose running pods pass it (checked with a server-side dry-run on 2026-10-25). `home-assistant`, `homelable`, `media` and `nextcloud` do not pass (host namespaces, hostPort, hostPath, added capabilities), so they have no `enforce` label until their pods are fixed.
- **Database namespaces**: `cnpg` and `redis` carry `vmd1.homelab/db-server=true`. The `netpol-db-client` component (see [../policies/components/](../policies/README.md)) selects database namespaces by this label, so a new database namespace needs only the label.
- **Exemptions**: `policy.vmd1.homelab/allow-host-network` and `policy.vmd1.homelab/allow-privileged` on a Namespace let the baseline admission policy skip that check there; `policy.vmd1.homelab/allow-capabilities` lists the added capabilities a namespace may use (dot-separated, e.g. `NET_ADMIN.NET_RAW`; label values cannot hold commas). Today: `home-assistant` (NET_ADMIN, NET_RAW), `homelable` (NET_RAW), `nextcloud` (Collabora: MKNOD, SYS_ADMIN, SYS_CHROOT). They live here, in Git, and never on a pod.
- **Built-ins**: `default`, `kube-system`, `kube-public` and `kube-node-lease` are created by k3s; they are listed here only so Flux can add the tier and Pod Security labels (server-side apply merges, nothing is recreated). `flux-system` comes from [flux-system/gotk-components.yaml](../../clusters/vmd1/flux-system/gotk-components.yaml) and is labelled by a patch in [flux-system/kustomization.yaml](../../clusters/vmd1/flux-system/kustomization.yaml).
- **Pruning disabled**: each Namespace carries `kustomize.toolkit.fluxcd.io/prune: disabled`. Deleting a Namespace deletes everything in it, so removing one from this file leaves it in the cluster; delete it by hand once its workloads are gone.
- **Adding an app**: add its Namespace here first, then its manifests in the right layer.

## Related

- [../README.md](../README.md) — the layer order.
- [../../../cluster-info.md](../../../cluster-info.md) — cluster inventory.
