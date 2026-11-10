# EdgeNodeConfig objects

Settings for the image nodes, applied by `noded` (phase 1.B of `docs/edge-node-roadmap.md`). `defaults` selects every node and
sets nothing. Roll a change out with `mode: try` and a `nodeSelector` for the canary (hera-02) first; `nodectl get nodes -o
custom-columns` is not needed, the result is on the Node: `kubectl get node <n> -o jsonpath='{.metadata.annotations}'`
(`node.vmd1.homelab/config-state`: applied, staged, rejected, rolled-back).
