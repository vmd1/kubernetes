# Projects (`resources/projects/`)

Project backends. Applied by the `projects` Flux Kustomization ([../../clusters/vmd1/projects.yaml](../../clusters/vmd1/projects.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [qecomp/](qecomp/README.md) | OIDC-authenticated app with Redis leader-election HA, CNPG backend, signing in through the cluster-wide Authelia (lldap `qecomp-*` groups). |
| [gossip/](gossip/README.md) | Gossip WebSocket relay and website (`gossip.vmd1.homelab`), single in-memory instance. |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
