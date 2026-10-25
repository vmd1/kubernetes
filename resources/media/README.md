# Media (`resources/media/`)

Streaming, reading and media APIs. Applied by the `media` Flux Kustomization ([../../clusters/vmd1/media.yaml](../../clusters/vmd1/media.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [jellyfin/](jellyfin/README.md) | Jellyfin streaming (Authelia SSO). |
| [bookorbit/](bookorbit/README.md) | Digital library and reading platform (ebooks, audiobooks, comics, PDFs) with CNPG backend. |
| [cinepro/](cinepro/README.md) | Media-aggregation API backend (`cinepro-core`) with Redis caching. |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
