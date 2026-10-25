# Auth (`resources/auth/`)

Identity: the lldap directory, the Authelia OIDC provider and the per-domain oauth2-proxy ForwardAuth middlewares. Applied by the `auth` Flux Kustomization ([../../clusters/vmd1/auth.yaml](../../clusters/vmd1/auth.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [lldap/](lldap/README.md) | Lightweight LDAP user directory backed by the CNPG PostgreSQL cluster. |
| [authelia/](authelia/README.md) | Cluster-wide OIDC provider (`identity.vmd1.homelab`) backed by lldap, CNPG and Redis; native OIDC clients for Grafana, Nextcloud, Jellyfin, BookOrbit, Home Assistant, QEComp and Vaultwarden. |
| [oauth2-proxy/](oauth2-proxy/README.md) | Per-domain Traefik ForwardAuth middlewares authenticating against Authelia. |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
