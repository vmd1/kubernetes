# Platform (`resources/platform/`)

Shared platform services: the private registry and Longhorn's UI and backup target (the Longhorn chart is in [../operators/longhorn/](../operators/longhorn/README.md)). Applied by the `platform` Flux Kustomization ([../../clusters/vmd1/platform.yaml](../../clusters/vmd1/platform.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [registry/](registry/README.md) | Private Docker registry with lldap-backed token auth (docker_auth) behind Traefik. |
| [longhorn/](longhorn/README.md) | Longhorn UI `IngressRoute` and the S3 `BackupTarget` (Backblaze B2). (Operator chart lives in [operators/longhorn](../operators/longhorn/README.md).) |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
