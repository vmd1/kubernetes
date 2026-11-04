# Blocklist CRD

`blocklists.dns.vmd1.homelab` (`Blocklist`, short name `bl`, namespaced, `v1alpha1`, status subresource). One object is one downloadable list of domains for the edge DNS resolver ([../../edge/dns-resolver/](../../edge/dns-resolver/README.md)); the object's name is the profile name clients use in the hostname (`ads-trackers.dns.vmd1.homelab`).

| Path | Description |
| :--- | :--- |
| [crd.yaml](crd.yaml) | The CRD: `spec.url`, `format` (`hosts` or `domains`), `refreshInterval` (default `24h`), `maxEntries` (default 200000), `suspend`; status conditions, `entries`, `contentHash`. |
| [kustomization.yaml](kustomization.yaml) | Kustomize entrypoint. |

Names must match `^[a-z0-9]{1,24}$` (the controller reports `InvalidName` otherwise). Like every CRD here it is never pruned by Flux.

```bash
kubectl -n dns-resolver get blocklists
```
