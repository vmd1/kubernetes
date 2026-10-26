# NetworkPolicy components

Reusable kustomize Components for default-deny networking (see `kubernetes/HARDENING-PLAN.md`, PR 2). An app includes them from its own `kustomization.yaml`; no shared policy is edited when an app is added.

| Component | Adds | Use for |
| :--- | :--- | :--- |
| [netpol-baseline](netpol-baseline/README.md) | default-deny (Ingress + Egress), DNS egress, ingress from Traefik (the pod CIDR, see the component README) and Prometheus | every enrolled app |
| [netpol-egress-public](netpol-egress-public/README.md) | internet egress minus private, tailnet and link-local ranges | apps that call out (SMTP, APIs) |
| [netpol-db-client](netpol-db-client/README.md) | egress to the database namespaces by label | apps using CNPG or Redis |
| [netpol-egress-any](netpol-egress-any/README.md) | unrestricted egress (ingress stays denied) | probes, scanners, monitoring |
| [netpol-api-server](netpol-api-server/README.md) | egress to the Kubernetes API | operators, controllers, Headlamp |
| [netpol-ldap-client](netpol-ldap-client/README.md) | egress to the LLDAP namespace (`vmd1.homelab/ldap-server=true`) | Authelia, the registry |
| [netpol-ldap-server](netpol-ldap-server/README.md) | ingress on the LDAP ports from `vmd1.homelab/ldap-client=true` namespaces | LLDAP |
| [netpol-db-operator](netpol-db-operator/README.md) | egress from the CNPG operator to the database namespaces (8000, 5432) | cnpg-system |

Always include `netpol-baseline`; the others only add allows on top of it.

## Enrolling an app

```yaml
# <group>/<app>/kustomization.yaml
components:
  - ../../policies/components/netpol-baseline

patches:
  - target: {kind: NetworkPolicy}                       # components carry no namespace
    patch: |-
      - {op: add, path: /metadata/namespace, value: <namespace>}
  - target: {kind: NetworkPolicy, name: allow-ingress-traefik}
    patch: |-
      - {op: replace, path: /spec/ingress/0/ports/0/port, value: <app port>}
  - target: {kind: NetworkPolicy, name: allow-ingress-monitoring}
    patch: |-
      - {op: replace, path: /spec/ingress/0/ports/0/port, value: <metrics port>}
```

Both ports default to the placeholder `1`, so a forgotten patch fails closed. The app's own manifests need nothing.

## Cluster-wide ranges

Every CIDR the components need is in one file, [../vars/cluster-ranges.yaml](../vars/README.md), injected with kustomize `replacements`. Flux `postBuild.substituteFrom` is deliberately not used: seven manifests contain literal `${...}`. Each component pulls the vars through its own `ranges/` directory (a uniquely suffixed copy), because kustomize rejects two resources with the same name when an app includes several components. The ConfigMap is `local-config`, so it is never rendered.

## Checking

```bash
kubectl kustomize resources/<group>/<app>
kubectl kustomize resources/<group>/<app> | kubectl apply --dry-run=server -f -   # SOPS secrets in the output will not dry-run
```
