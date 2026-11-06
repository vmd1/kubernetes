# Tunnel Gateway

Server side of [`tunnel-agent`](../../../../tunnel-agent/README.md): a deny-by-default `wstunnel` gateway at `wss://coordination.vmd1.homelab`. An agent on a server whose network blocks Tailscale dials out to it over HTTPS, and either carries Tailscale's own control-plane/DERP traffic through it (the unprivileged secret) or, as a last resort, reaches the homelab and exposes ssh through it (the privileged secret).

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | StatefulSet `tunnel-gateway` (2 replicas, one per `uk-home` node; upstream `ghcr.io/erebe/wstunnel` pinned by digest; read-only root FS; an init container and a sidecar that copy the restrictions in place), a Service for any replica, one Service per replica, and a PodDisruptionBudget (`minAvailable: 1`). |
| [controller.yaml](controller.yaml) | The `TunnelAgent` controller (ServiceAccount, Role, Deployment). Its code, [controller/controller.py](controller/controller.py), is mounted from a ConfigMap on a pinned stock Python image: nothing to build. |
| [agents.yaml](agents.yaml) | The `TunnelAgent` objects: one per server running tunnel-agent. This is the only place an agent is added or removed. |
| [ingressroute.yaml](ingressroute.yaml) | Traefik routes on `websecure` only, priority 950000 (above the Cloudflare-only catch-all): `tunnel` (any replica), `tunnel-0` and `tunnel-1` (one replica each). |
| [controller/sync.py](controller/sync.py) | Copies the mounted restrictions Secret in place onto the file wstunnel watches. |

The CRD is in [`crds/tunnelagent`](../../crds/tunnelagent/README.md).

## How it works

- **The gateway only reads.** The controller watches `TunnelAgent` objects and renders every active agent into the Secret
  `tunnel-gateway-restrictions` (wstunnel's `--restrict-config`). Deny by default: no agents renders `restrictions: []`, which refuses everything.
- **Credentials per agent**, in Secret `agent-<name>` (owned by the object, so deleting it deletes them): three random secrets, each
  the request path prefix wstunnel matches on.
  - *via*: may only open `*.tailscale.com:443` (the Tailscale-over-tunnel pathways).
  - *agent*: outbound to the LAN/cluster ranges, and reverse tunnels on **only this agent's allocated port(s)**.
  - *client*: may only forward to **this agent's** ports on the pod's own loopback. A leaked client secret reaches one agent's ssh, not all of them.
- **Reverse tunnels are private**: the agent asks for `XXX.XXX.XXX.XXX:<port>` on the pod, so nothing is published to the internet or the cluster network.
- **No restart for changes.** wstunnel reloads its restrictions file when it is written, but not when a Secret volume updates (the kubelet swaps a
  symlink; tested). So `sync.py` rewrites the file in place; a bad or half-written file is ignored (wstunnel keeps the old config), so it
  cannot open anything up. Add, suspend, rotate or delete an agent and it takes effect within about 1-2 minutes (the kubelet's Secret refresh).
- **Two replicas, and why they have their own names.** A reverse tunnel's listener lives in the pod the agent connected to, so the client has to
  reach the same pod. The agent's `TUNNEL_URL` lists its preferred replica first and the other as a failover; `scripts/ssh-agent.sh` tries both.
  A drained or restarted replica only drops the tunnels on it; those agents reconnect to the other one.
- **Ports** (20000-20999) are allocated by the controller, unique across all agents (so a failover keeps the port) and stable (kept in `status.ports`).
- **TLS** terminates at Traefik (wildcard certificate). The hostnames are DNS-only (`dns/domains/vmd1.homelab.js`) so they work from networks that block
  Cloudflare and TLS never ends at a third party. **Port 80 is not served** (Traefik redirects it), so `ws://` cannot work here.

## Operating it

```bash
kubectl -n tunnel-gateway get ta                       # agents: Ready, gateway, ssh port, last rotation
tunnel-agent/scripts/agent-env.sh test                 # the agent's environment (add CANARY and TS_AUTHKEY)
tunnel-agent/scripts/ssh-agent.sh test ubuntu          # ssh into it through the gateway
```

- **Add an agent**: a new object in `agents.yaml` (`spec: {}` is enough; `expose:` publishes more than ssh).
- **Revoke**: `suspended: true` (reversible; its credentials are kept) or delete the object (they are destroyed).
- **Rotate now**: change `spec.rotationToken`. Automatic rotation is off by default (`rotateAfter: never`); set `rotateAfter: 90d` on an agent you redeploy on a schedule. The previous secrets keep working for
  `rotationGrace` (default 24h) so a running agent is not cut off before you put the new `agent.env` on it; `status.previousValidUntil` says until when.
- A rotation does not reach the agent by itself: re-run `agent-env.sh` and restart the agent within the grace period.

## Dependencies

- Traefik (`websecure`), the wildcard certificate, and the `tunnel`, `tunnel-0`, `tunnel-1` records in `dns/domains/vmd1.homelab.js`.
- The `tunnelagents` CRD (`crds/tunnelagent`), applied before this.
- Tailscale ACL: `tag:agent` (in `tailscale/policy.hujson`); the gateway itself needs no tailnet exposure.

## Services & Routers

- **Services**: `tunnel-gateway` (any replica), `tunnel-gateway-0`, `tunnel-gateway-1` (ClusterIP `:8080`).
- **Ingress**: Hosts `coordination.<d>`, `coordination-0.<d>`, `coordination-1.<d>` for `<d>` in vmd1.homelab, vmd1.homelab, vmd1.homelab (the wildcard certificate covers all three), `websecure`.
- **Domains**: the controller's `GATEWAY_HOST` (a template with `{i}`) and `VIA_URL` take comma lists, one entry per domain. An agent's env gets its own replica under every domain first, then the other replica; `TUNNEL_VIA_URL` is the list of `coordination.<d>` names, which the agent tries in order. DNS: `dns/domains/{vmd1.homelab,vmd1.homelab,vmd1.homelab}.js` (unproxied CNAMEs to `ingress.vmd1.homelab`).

- **Cloudflare name**: `cf-coordination.vmd1.homelab` is the only proxied name (DNS `CF_PROXY_ON`). It is routed to the any-replica (via) service only, never the per-replica reverse-tunnel routes, because Cloudflare cuts a request with no response headers after ~100s.
