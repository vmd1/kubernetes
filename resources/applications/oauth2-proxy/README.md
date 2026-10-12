# oauth2-proxy (`resources/applications/oauth2-proxy/`)

oauth2-proxy provides Traefik ForwardAuth for every protected domain, using [Authelia](../authelia/README.md) (`identity.vmd1.homelab`) as the OIDC provider. It replaces the `authentik-auth` middleware.

## Table of Contents

- [Files](#files)
- [Design Decisions](#design-decisions)
- [Dependencies](#dependencies)
- [Services & Routers](#services--routers)
- [Using the Middleware](#using-the-middleware)
- [Constraints & Scheduling](#constraints--scheduling)
- [Configs & Credentials](#configs--credentials)

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Namespace `oauth2-proxy`; per domain a Deployment (2 replicas), ClusterIP Service on `:4180`, and a Traefik `forwardAuth` Middleware. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` exposing `/oauth2/` on each `secure.<domain>` host. |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `oauth2-proxy-secrets` (client secret and cookie secret per domain). |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint. |

## Design Decisions

- **One instance per domain**: each Deployment has a fixed `--redirect-url=https://secure.<domain>/oauth2/callback`, `--cookie-domain=.<domain>` and `--whitelist-domain=.<domain>`. Authelia matches redirect URIs exactly, so a fixed callback host per domain keeps Authelia at four registered callbacks, and a new protected host needs no Authelia change.
- **`static://202` upstream**: unauthenticated requests get a redirect to Authelia (`--skip-provider-button`); authenticated requests get `202` plus `X-Auth-Request-*` headers, which is what Traefik's `forwardAuth` needs. `--reverse-proxy` makes oauth2-proxy derive the return URL from `X-Forwarded-*`.
- **Stateless cookie sessions** (`--session-cookie-minimal`, 12h expiry, no refresh): replicas are interchangeable and no session store is needed. A shared cookie secret per domain is used by both replicas.
- **PKCE S256** is enabled and required by the matching Authelia client.
- **Group gate**: each instance also sets `--allowed-group=Domain: <domain>` (lldap group, from the ID token `groups` claim) as a second check behind Authelia's per-client policy.
- **Only `/oauth2/*` is routed** on the `secure.<domain>` hosts; everything else there 404s.
- **Hardened pods**: non-root, read-only root filesystem, all capabilities dropped.
- **Home-only for now**: pods run in `uk-home`; nothing is scheduled on the ingress/edge nodes.

## Dependencies

- **Authelia** at `https://identity.vmd1.homelab` (OIDC discovery runs at startup via the public hostname; pods will not become ready if it is unreachable).
- **Traefik** for the `IngressRoute` and `Middleware` CRDs.
- DNS: the `*.vmd1.homelab`, `*.vmd1.homelab`, `*.vmd1.homelab` and `*.vmd1.homelab` wildcard CNAMEs already resolve `secure.<domain>` to the ingress; the wildcard certificate covers them.

## Services & Routers

| Domain | Service / Middleware | Callback host | Client ID |
| :--- | :--- | :--- | :--- |
| `vmd1.homelab` | `oauth2-proxy-kmnet-uk` | `secure.vmd1.homelab` | `oauth2-proxy-kmnet-uk` |
| `vmd1.homelab` | `oauth2-proxy-vmd1-dev` | `secure.vmd1.homelab` | `oauth2-proxy-vmd1-dev` |
| `vmd1.homelab` | `oauth2-proxy-010356-xyz` | `secure.vmd1.homelab` | `oauth2-proxy-010356-xyz` |
| `vmd1.homelab` | `oauth2-proxy-848226-xyz` | `secure.vmd1.homelab` | `oauth2-proxy-848226-xyz` |

## Using the Middleware

Reference the middleware for the route's domain from any `IngressRoute`:

```yaml
middlewares:
  - name: oauth2-proxy-kmnet-uk
    namespace: oauth2-proxy
```

## Constraints & Scheduling

- 2 replicas per domain, `RollingUpdate` (`maxUnavailable: 0`), `nodeSelector` `topology.kubernetes.io/zone: uk-home`, soft preference for `hades-02`.
- Requests `10m` / `32Mi`, limits `250m` / `128Mi` per pod. Image pinned to `quay.io/oauth2-proxy/oauth2-proxy:v7.15.5`.

## Configs & Credentials

- **Secret `oauth2-proxy-secrets`**: `client-secret-<domain-slug>` (plaintext counterpart of the hash in Authelia's config) and `cookie-secret-<domain-slug>` (32-byte url-safe base64) for `kmnet-uk`, `vmd1-dev`, `010356-xyz`, `848226-xyz`.
