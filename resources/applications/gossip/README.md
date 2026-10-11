# Gossip Relay

WebSocket relay for the Gossip apps, served at `wss://gossip.vmd1.homelab` (website at `/`).

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Namespace `gossip`, Deployment `gossip-relay` (`ghcr.io/vmd1/gossip/relay`, pinned tag, nodeSelector zone `uk-home`, read-only root FS) and ClusterIP Service on `:8080`. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik `IngressRoute` for `gossip.vmd1.homelab` (TLS from the `*.vmd1.homelab` wildcard). |

## Design Decisions

- **Single replica, `Recreate`**: topics and bans are in memory; a restart drops connections and clients rejoin automatically.
- **`RELAY_ORIGIN=wss://gossip.vmd1.homelab`**: signed into every join; must match exactly what clients use.
- **Proxy trust**: `TRUSTED_PROXY=true` with `TRUSTED_PROXY_HEADER=cf-connecting-ip`, as the DNS record is Cloudflare-proxied.
- **Updates**: bump the image tag (`sha-<short>`; `:dev` also exists, `:latest` only after main).

## Endpoints

`/connect` WebSocket, `/` website, `/healthz`, `/abuse`, `/.well-known/security.txt`.

## Constraints & Scheduling

Pinned to `topology.kubernetes.io/zone=uk-home`. No persistent storage (optional `BAN_FILE`/`KILL_SWITCH_FILE` would need a volume).
