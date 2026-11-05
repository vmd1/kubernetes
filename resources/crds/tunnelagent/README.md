# TunnelAgent CRD

`tunnelagents.tunnel.vmd1.homelab` (v1alpha1, namespaced, short name `ta`): one object per server running [tunnel-agent](../../../../tunnel-agent/README.md).
The controller in [../../projects/tunnel-gateway/](../../projects/tunnel-gateway/README.md) turns each one into per-agent credentials (Secret `agent-<name>`) and
into the gateway's wstunnel restrictions. Spec: `suspended`, `expose`, `gateway`, `rotateAfter`, `rotationGrace`, `rotationToken`.
Status: `conditions` (Ready), `gateway`, `gateways`, `ports`, `secretName`, `rotatedAt`, `previousValidUntil`.

Never pruned (see [../README.md](../README.md)): deleting this CRD deletes every agent's record and, with it, their credentials.
