# Registry cache (`resources/platform/registry-cache/`)

Pull-through cache for `docker.io` on the uk-home nodes (hades-01 arm64, hades-02 amd64), Phase R1 of the [edge node roadmap](../../../../docs/edge-node-roadmap.md). It replaces the public `mirror.gcr.io` as the `docker.io` mirror of the edge nodes. Separate from the private [registry](../registry/README.md), which holds our own images.

## Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | PVC `zot-data` (50Gi, `longhorn-single-replica`), Deployment `registry-cache` ([Zot](https://zotregistry.dev) v2.1.22, pinned by digest, `Recreate`, uk-home only, 48Mi request / 256Mi limit, non-root, read-only root) and Service `registry-cache` (:5000). |
| [config.json](config.json) | Zot config, shipped as a hash-suffixed ConfigMap so a change rolls the pod. |
| [tailscale.yaml](tailscale.yaml) | `ProxyClass` `registry-cache-uk-home` and the Tailscale `Ingress` that publishes `https://registry-cache.<tailnet>.ts.net`. |

## Design

- **Docker Hub at the root**: Zot syncs on demand from `https://index.docker.io` into `/`, so `library/nginx` and `grafana/grafana` live at the same paths as upstream. That is what a containerd mirror endpoint and `nodectl registry <node> set --mirror <url>` expect; no image change. Other upstreams (`ghcr.io`, `quay.io`, `registry.k8s.io`) come in R2 under path prefixes.
- **Read-only**: anonymous clients may read, nobody may push. Only the sync extension writes. No credentials are mounted yet (anonymous Docker Hub pulls).
- **Small**: one pod, `GOMEMLIMIT=192MiB`, dedupe on, GC daily, tags neither pulled nor fetched for 30 days (`720h`) are dropped (they are re-fetched on demand), on a 50Gi volume under a 60Gi namespace quota.
- **Tailnet only**: no `IngressRoute`, no public name. The Tailscale operator proxy (pinned to uk-home) terminates TLS with a public-CA certificate for the `*.ts.net` name, so containerd needs no insecure-registry setting. The proxy device is tagged `tag:registry-cache`.

## Manual steps (not done by Flux)

1. **Tailnet policy** (`tailscale/policy.hujson`, applied by you): add `"tag:registry-cache": ["tag:k8s-operator"]` to `tagOwners` and a grant `{"src": ["tag:k3s"], "dst": ["tag:registry-cache"], "ip": ["tcp:443"]}`. Until then the Ingress proxy cannot register and nodes just fall back to their other endpoints.
2. **Check**: `kubectl -n registry-cache get pods,ingress`; from a tailnet machine `curl -s https://registry-cache.<tailnet>.ts.net/v2/` returns `{}`; `curl -sI https://registry-cache.<tailnet>.ts.net/v2/library/alpine/manifests/3.20` fills the cache on the first call.
3. **Optional Docker Hub token** (raises the anonymous limit): create a SOPS secret `zot-sync-credentials` with `credentials.json` = `{"index.docker.io": {"username": "...", "password": "<token>"}}`, mount it and add `"credentialsFile": "/etc/zot-creds/credentials.json"` to `extensions.sync` in `config.json`.
4. **Switch nodes one at a time**, hera-02 first (canary), then the other edge nodes: `nodectl registry <node> set --mirror https://registry-cache.<tailnet>.ts.net` (replaces the `mirror.gcr.io` endpoint; the upstream registry remains the fallback). On hades-01/02, edit `/etc/rancher/k3s/registries.yaml` (hand-managed, see [host-config](../../../../docs/host-config.md)) and keep `mirror.gcr.io` as a second endpoint:

   ```yaml
   mirrors:
     docker.io:
       endpoint:
         - "https://registry-cache.<tailnet>.ts.net"
         - "https://mirror.gcr.io"
         - "https://registry-1.docker.io"
   ```

   then `sudo systemctl restart k3s` (hades-01) or `k3s-agent` (hades-02).
5. Drop `mirror.gcr.io` from the chain only after the cache has run for a month.

## Related

- [../registry/README.md](../registry/README.md) — the private registry.
- [../../vpn/tailscale/README.md](../../vpn/tailscale/README.md) — the Tailscale operator.
