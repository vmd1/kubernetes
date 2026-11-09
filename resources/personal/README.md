# Personal (`resources/personal/`)

Files, notes, passwords and chat. Applied by the `personal` Flux Kustomization ([../../clusters/vmd1/personal.yaml](../../clusters/vmd1/personal.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [sftpgo/](sftpgo/README.md) | Shared-folder links on Backblaze B2 (`files.vmd1.homelab`): view, upload and download with one link. |
| [obsidian/](obsidian/README.md) | Removed server; only the retained `obsidian-pvc` volume remains. |
| [vaultwarden/](vaultwarden/README.md) | Lightweight Bitwarden-compatible password vault (PostgreSQL + Authelia SSO). |
| [matrix/](matrix/README.md) | Self-hosted Matrix stack: `continuwuity` homeserver, FluffyChat web client, and mautrix bridges. |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
