# Docker Registry

This folder deploys a private self-hosted Docker registry (`registry:3`). It provides in-cluster storage for custom container images, authenticating users against [lldap](../lldap/README.md) through a token server ([docker_auth](https://github.com/cesanta/docker_auth)).

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Namespace `registry`, PersistentVolumeClaim, `registry` Deployment and Service (token auth), `docker-auth` ConfigMap, Deployment and Service. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` for `registry.vmd1.homelab` (registry) and `registry.vmd1.homelab/auth` (token endpoint). |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `docker-auth-secrets` (token signing key and certificate, lldap bind password). |

## Design Decisions

- **LDAP-backed token auth**: `registry:3` is configured with token authentication (`REGISTRY_AUTH=token`). `docker login` and pulls fetch a short-lived token from `docker-auth` at `https://registry.vmd1.homelab/auth`, which checks the user's lldap password and group membership. The registry verifies tokens against the signing certificate only and never sees passwords.
- **Registry v3 key IDs**: v3 checks the token `kid` against the JWK thumbprint of the signing certificate and rejects the legacy libtrust key ID with `token signed by untrusted key` (every request 401). `docker-auth` therefore runs 1.14.0 with `token.disable_legacy_key_id: true`; the older `:1` tag (1.12.0) lacks the option. Do not drop either when changing versions.
- **Group-based access**: users must be in an lldap group to get a token. `registry-admin` can push and pull; `registry-pull` can only pull. `docker-auth` binds to lldap as the read-only `registry` service account and matches groups through the `memberOf` attribute.
- **Golang Garbage Collection Tuning**: Injected `GOGC=50` environment variable to trigger garbage collection twice as fast as default. This limits memory bloat during massive parallel chunk pushes.
- **Recreate Strategy**: The deployment is configured with `Recreate` to ensure the block volume is unmounted from old pods before scheduling new ones.

## Dependencies

- **Traefik Ingress**: SSL termination and routing; `/auth` goes to `docker-auth`, everything else to the registry.
- **lldap** (`lldap.lldap.svc.cluster.local:3890`): user and group directory, including the `registry` bind account.

## Services & Routers

- **Kubernetes Services**: `registry` (ClusterIP, port `5000`) and `docker-auth` (ClusterIP, port `5001`).
- **Ingress Route**:
  - Host `registry.vmd1.homelab` on `websecure` entrypoint, routing requests to the `registry` service (token-authenticated by the registry itself).
  - Host `registry.vmd1.homelab` with path prefix `/auth` routing to the `docker-auth` service.

## Storage

- **PVC**: `registry-pvc`
  - **Storage Class**: `longhorn-single-replica`
  - **Size**: `10Gi`
  - **Mount Point**: Mounted to `/var/lib/registry`.
  - **Data Persistence**: Stores the container image blobs, manifest indices, and layers.

## Constraints & Scheduling

- **Deployment Strategy**: Set to `Recreate` deployment strategy. This ensures only a single running replica writes to the backing block storage.
- **Resource Constraints**:
  - Request: `100m` CPU, `128Mi` RAM.
  - Limit: `500m` CPU, `512Mi` RAM.

## Configs & Credentials

- **Secret**: `docker-auth-secrets`
  - `token.key` / `token.crt`: key pair `docker-auth` signs tokens with; the registry mounts only `token.crt`.
  - `ldap_password`: password of the lldap `registry` bind account.
- **Clients**: pulls from the cluster use a pull-only lldap account (`k3s-registry-pull`, member of `registry-pull`); each node's k3s `registries.yaml` must carry its credentials. Pushers need an account in `registry-admin`.
