# Gossip Relay

WebSocket relay for the Gossip apps, served at `wss://gossip.vmd1.homelab`. The website at `/` is served separately by the [edge-sites](../../edge/edge-sites/README.md) platform (`EdgeSite/gossip`, built from `site/` of `vmd1/gossip`); this app only handles the relay endpoints below.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Deployment `gossip-relay` (`ghcr.io/vmd1/gossip/relay`, pinned tag, nodeSelector zone `uk-home`, read-only root FS) and ClusterIP Service on `:8080`. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` for the relay paths of `gossip.vmd1.homelab` (`/connect`, `/healthz`, `/abuse`, `/.well-known/security.txt`; priority 100; TLS from the `*.vmd1.homelab` wildcard). |

## Design Decisions

- **Single replica, `Recreate`**: topics and bans are in memory; a restart drops connections and clients rejoin automatically.
- **`RELAY_ORIGIN=wss://gossip.vmd1.homelab`**: signed into every join; must match exactly what clients use.
- **Proxy trust**: `TRUSTED_PROXY=true` with `TRUSTED_PROXY_HEADER=cf-connecting-ip`, as the DNS record is Cloudflare-proxied.
- **Updates**: bump the image tag (`sha-<short>`; `:dev` also exists, `:latest` only after main).

## Endpoints

`/connect` WebSocket, `/healthz`, `/abuse`, `/.well-known/security.txt` (relay, via this IngressRoute); `/` and all other paths are the static website from the EdgeSite.

## Constraints & Scheduling

Pinned to `topology.kubernetes.io/zone=uk-home`. No persistent storage (optional `BAN_FILE`/`KILL_SWITCH_FILE` would need a volume).

## Network policy

Enrolled in `netpol-baseline` only: inbound HTTP 8080 from Traefik and Prometheus, DNS out, nothing else. See [policies/components](../../policies/components/README.md).
