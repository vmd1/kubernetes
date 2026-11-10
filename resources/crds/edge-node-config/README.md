# EdgeNodeConfig CRD

Cluster-scoped, `edge.vmd1.homelab/v1alpha1`, short name `enc`. Declarative settings for the image nodes; `noded` on each node reads the
objects whose `nodeSelector` matches its labels, merges them (most specific wins), validates, writes k3s / sysctl / timesyncd
drop-ins and reports `node.vmd1.homelab/config-state`, `config-hash` and `config-error` on its Node. Objects live in
`resources/edge/edge-node-config/`. Design: `docs/edge-node-roadmap.md`, phase 1.B.
