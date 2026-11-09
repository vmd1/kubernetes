# Tunnel Gateway

Server side of [`tunnel-agent`](../../../../tunnel-agent/README.md): a deny-by-default `wstunnel` gateway at `wss://coordination.vmd1.homelab`. An agent on a server whose network blocks Tailscale dials out to it over HTTPS, and either carries Tailscale's own control-plane/DERP traffic through it (the unprivileged secret) or, as a last resort, reaches the homelab and exposes ssh through it (the privileged secret).

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | StatefulSet `tunnel-gateway` (2 replicas, one per `uk-home` node; upstream `ghcr.io/erebe/wstunnel` pinned by digest; read-only root FS; an init container and a sidecar that copy the restrictions in place), a Service for any replica, one Service per replica, and a PodDisruptionBudget (`minAvailable: 1`). |
| [controller.yaml](controller.yaml) | The `TunnelAgent` controller (ServiceAccount, Role, Deployment). Its code, [controller/controller.py](controller/controller.py), is mounted from a ConfigMap on a pinned stock Python image: nothing to build. |
| [bridge-rbac.yaml](bridge-rbac.yaml) | The controller's Role in the `tunnel-bridge` namespace (Secrets, Services, Deployments of the lab bridges). |
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
- **Last seen and connection type.** The controller reads each gateway pod's wstunnel log (RBAC: `pods/log` `get` on the two pods only) and sets `status.lastSeen` and `status.connectionType` (`via` = Tailscale carried through the gateway, `agent` = the wss-tunnel reverse-tunnel pathway) from the newest "Tunnel accepted due to matched restriction" line per agent. A person's ssh (`<agent>-client`) does not count. The status is rewritten only when the type changes or the time has moved by `LAST_SEEN_RESOLUTION` (default 300 s), so a steady agent is not a write every poll. An agent on the direct Tailscale pathway never touches the gateway and shows its last tunnel use. If the logs cannot be read the previous values stay. Agent names ending in `-via` or `-client` are rejected (those are restriction-name suffixes).
- **Lab bridge** (`spec.bridge: true`, opt-in). The controller generates a WireGuard keypair for the agent and for its bridge (a small X25519 implementation, checked
  against the RFC 7748 vectors), allocates a slot (`10.99.<slot>.0/30` and the NodePort `31820 + slot`, at most `BRIDGE_SLOTS` = 16, kept in `status.bridge`) and server-side-applies the bridge's
  Secret, Deployment and NodePort Service in the `tunnel-bridge` namespace ([../../../../tunnel-bridge](../../../../tunnel-bridge/README.md)); objects of agents that no longer want one are deleted. The agent's
  `agent.env` gets `WG_*`, and its **via** secret gains one more allowed tunnel: UDP to its own bridge Service on 51820, nothing else (so a leaked via secret still cannot reach another agent's bridge). Rotation
  regenerates the WireGuard keys (no grace period). A broken bridge namespace is logged and never stops credentials or restrictions. Prerequisites: the `bridge-authkey` Secret (see `bridge-rbac.yaml`), the
  image `ghcr.io/vmd1/tunnel-bridge` and `oci/firewall/tunnel-bridge.yaml` (direct UDP).
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

- **vmd1.homelab is the uk-home leg**: `coordination[-0|-1].vmd1.homelab` are CNAMEs to `uk-home.ingress.vmd1.homelab` (the home WAN IP), the other two domains stay on the edge nodes and are the fallback when home is unreachable. Home Traefik (`traefik-uk-home-lb`) serves the same IngressRoute.
- **Cloudflare name**: `cf-coordination.vmd1.homelab` is the only proxied name (DNS `CF_PROXY_ON`). It is routed to the any-replica (via) service only, never the per-replica reverse-tunnel routes, because Cloudflare cuts a request with no response headers after ~100s.

## Enrollment (`POST /enroll`)

Instead of copying an agent's credentials around, an operator hands a server a **3-use token** (`tunnel-agent/scripts/make-provision.sh`, which stores
only the token's SHA-256 in `Secret enroll-<name>` with `uses: 3` and an expiry). The controller serves `POST /enroll` (`{name, token}`) on port 8080;
`ingressroute.yaml` routes `Path(/enroll)` on the `coordination[.cf-]` names to it (priority above the wstunnel route, rate limited). A valid token returns
`CANARY`, `TS_AUTHKEY` (from `Secret tunnel-enroll-common`, created by hand with `set-enroll-common.sh`, never committed) and the agent's `agent.env`
(`Secret agent-<name>`); the use is deducted before the answer is sent (optimistic `resourceVersion` write, so concurrent requests cannot share a use).
A wrong, expired, used-up or suspended-agent request gets the same `403 denied`; only the reason is logged, never the token.

`GET /setup/<key>` serves the provisioning script for a valid key (`curl -fsSL https://coordination.vmd1.homelab/setup/<key> | sudo sh`): the controller renders
`controller/provision.template.sh` (shipped in the `tunnel-gateway-code` ConfigMap) with the key, the agent's name, the enroll URLs and the shared settings
from `Secret tunnel-enroll-common` (`SSH_PUBKEY`, `ADMIN_USER`, `REGISTRY_*`; never the Tailscale key, which only `/enroll` returns). It does not use a use, and a
bad, expired, used-up or suspended-agent key gets the same `403 denied`. The script is a small POSIX stub that unpacks the bash script, so `| sh` works on dash.
