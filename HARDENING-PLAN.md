# Cluster hardening plan: NetworkPolicies and admission policies

Status: **FINAL PLAN.** Nothing in this plan is applied yet.
Written 2026-10-25 against `main` @ `94ba8fe` (after the Flux purpose-group restructure and the
`namespaces` / `node-labels` layers landed). Delivered in **three PRs** (section 5).

Goal: default-deny networking plus built-in admission policies, with nothing tied to specific
IPs, node names, namespace names, or hostnames, and everything managed in Git.

## 1. Scope and non-goals

In scope: default-deny NetworkPolicies, ValidatingAdmissionPolicy (VAP), Pod Security Admission
(PSA) labels, quotas, service account / RBAC guardrails, node-level API hardening (Tailscale ACLs,
API audit logging, secrets encryption).

Out of scope (decided): image provenance/registry allowlists, Service type restrictions, IngressRoute
guardrails, image signing (cosign), runtime detection (Falco/Tetragon), a policy blocking
control-plane tolerations or scheduling onto free-tier nodes, and a drop-ALL-capabilities rule.
No new controllers are installed: everything uses Kubernetes v1.35 built-ins, k3s's embedded
NetworkPolicy controller (kube-router), and the existing Flux setup.

## 2. Findings that shape the design

Re-verified live on 2026-10-25: 8 nodes Ready on v1.35.5+k3s1, 39 namespaces, all 16 Flux
Kustomizations Ready on `94ba8fe`, no NetworkPolicies outside `flux-system` and `longhorn-system`
(plus our `longhorn-manager-allow-prometheus`), no ValidatingAdmissionPolicies, no
`MutatingAdmissionPolicy` API. The pod inventory below is from 2026-10-23.

- k3s, flannel over `tailscale0`. No `disable-network-policy`, so NetworkPolicy is **enforced**.
- `ValidatingAdmissionPolicy` is available (`admissionregistration.k8s.io/v1`); no
  `MutatingAdmissionPolicy`, so nothing can inject a securityContext for us.
- **Flux layout:** foundation layers `node-labels` and `namespaces` run first, then `crds` and
  `operators`. Eleven purpose groups (`vpn`, `oci`, `proxy`, `auth`, `platform`, `observability`,
  `home`, `media`, `personal`, `projects`, `edge`) each `dependsOn: operators` only, so a broken
  group cannot hold up another. Manifests live in `resources/<group>/<app>/`.
- **Namespaces are in Git already.** `resources/namespaces/namespaces.yaml` declares 34
  Namespaces, each `kustomize.toolkit.fluxcd.io/prune: disabled`; app manifests no longer
  declare their own. Not covered: `default`, `kube-system`, `kube-public`, `kube-node-lease`
  (left to k3s) and `flux-system` (from `gotk-components.yaml`). **None has a `vmd1.homelab/tier` or
  PSA label yet**, except `flux-system`'s `pod-security.kubernetes.io/warn=restricted`.
- **Node labels are in Git already** (`resources/node-labels/<node>.yaml`, 8 files,
  labels only, `prune: disabled`, `wait: false`). This plan needs no new node label.
- hostNetwork pods: `traefik`, `powerdns`, `home-assistant`, `monitoring` (node-exporter),
  `kube-system`. Privileged pods: `kube-system`, `longhorn-system`, `monitoring`, `tailscale`.
  hostPath users: `kube-system`, `longhorn-system`, `monitoring`, `traefik`, `powerdns`, `geoip`, `media`.
- **Tailnet-only routing exists.** The `tailnet-only` Traefik middleware (`proxy/traefik/tailnet-only.yaml`)
  allow-lists the TCP peer `100.64.0.0/10` and `fd7a:115c:a1e0::/48` and is attached to the admin
  routes (Headlamp, Longhorn, LLDAP, router console, and others). It judges the peer address
  Traefik sees, so netpols must not change that address.
- **Tailscale ACL is in Git:** `tailscale/policy.hujson`, applied by `tailscale-acl-sync` (tests run
  first), previewed by `tailscale-acl-preview`. Nodes are `tag:k3s`; today `tag:k3s` and
  `tag:k8s-operator` may reach `*` on all ports, `tag:servers` reaches `autogroup:tagged` on all
  ports, and members reach `tag:k3s` on 53/80/443/853/8448 (needed for split DNS).
- The `edge` group isolates the 1 GB ingress nodes, so a NotReady ingress node marks only `edge`
  NotReady. zeus-01 is the one node with a known instability history.
- 7 existing manifests contain literal `${...}` (nextcloud, cf-ddns, registry, error-pages,
  edge-sites redirects, monitoring-agents, podflow dashboards). That rules out turning on Flux
  `postBuild.substituteFrom` for whole groups (see principle 2).

## 3. Scalability principles (apply to every PR)

1. **Select by label, never by name.** Policies target namespaces via `vmd1.homelab/tier` and opt-in
   labels such as `vmd1.homelab/db-client`, and databases via namespace labels. A new app inherits
   the right policy by being labelled, with no edit to the policy.
2. **No literal IPs/CIDRs in policy files, and no per-node IPs anywhere in Git.** Node objects are
   the source of truth for node addressing: `status.addresses` (InternalIP is the Tailscale
   address; ExternalIP is public on the OCI nodes, the Tailscale address on hades/zeus-01) and
   `spec.podCIDR` (a /24 per node). Nothing in the policies lists a node.
   - Selectors first: CoreDNS via the `k8s-app=kube-dns` pod selector, monitoring and databases
     via namespace labels.
   - Where NetworkPolicy has no selector for the peer (host-network sources, API server,
     RFC1918 exceptions), the only literals are *ranges that belong to the cluster, not a node*,
     kept in **one vars file** and injected by kustomize `replacements` inside the shared
     components: `POD_CIDR`, `SERVICE_CIDR`, `TAILNET_CIDR` (IPv4 `100.64.0.0/10` plus
     `fd7a:115c:a1e0::/48`, the same ranges `tailnet-only` uses), `PRIVATE_CIDRS`,
     `LINK_LOCAL_CIDR`, `NODE_LOCAL_DNS_IP`, `API_SERVER_CIDR`. Not Flux `postBuild`, because of
     the `${...}` collisions in section 2.
   - A drift check (`check-policies.sh`) compares the vars file with the live Node
     `spec.podCIDR` / `status.addresses`, so it can't silently go stale.
   - ExternalIP is never used in a policy: in-cluster traffic rides the Tailscale addresses.
3. **Parameterise VAPs.** Allowlists (hostPath prefixes) are `paramKind` objects, not inlined CEL.
4. **Exemptions come from Git-owned namespace labels and param objects, never from labels on the
   pod.** A pod-level exemption label would let any workload author bypass the policy. Example:
   `policy.vmd1.homelab/allow-host-network=true` on the `home-assistant` entry in `namespaces.yaml`.
5. **Reusable Kustomize components, not copy/paste** (`policies/components/`). Each app's
   `kustomization.yaml` adds one line; per-app additions are small overlays.
6. **Guard against drift in CI** (`check-policies.sh`, PR 1).
7. **Git is the only source of truth, including labels.** Namespaces, policies and quotas are
   declared in this repo and reconciled by Flux; nothing is labelled with `kubectl label`.
   Server-side apply reverts manual edits to fields Flux owns. The Tailscale tailnet is already
   GitOps; k3s host config (PR 1) has its canonical content in Git and a reviewed apply script.
8. **A broken policy must not hold up an app group.** Groups keep depending only on `operators`:
   netpol components are included by each app, and admission policies live in their own layer
   that no group depends on.

## 4. Repository layout (new)

```
resources/policies/
  README.md
  kustomization.yaml
  vars/                        # the only place cluster-wide ranges live
  admission/
    params/                    # ParamKind objects (allowlists)
    baseline.yaml  app-hardening.yaml  service-accounts.yaml  rbac.yaml
    storage.yaml   metadata.yaml       namespace-tier.yaml    resource-limits.yaml
    bindings.yaml              # one binding per policy, namespaceSelector on tier labels
  components/
    netpol-baseline/           # default-deny + shared allows (DNS, ingress, scrape)
    netpol-egress-public/      # private-range / metadata egress block for internet-facing apps
    netpol-db-client/          # egress to CNPG/Redis for namespaces labelled as clients
    netpol-egress-any/         # ingress still denied; egress open, for probing apps
    quota-default/             # ResourceQuota + LimitRange by tier
resources/k3s-config/  # canonical k3s config fragments (no secrets)
.github/scripts/check-policies.sh
```

Extended, not created: `resources/namespaces/`. New Flux Kustomization
`clusters/vmd1/policies.yaml` (foundation layer, `dependsOn: namespaces`) for `policies/admission/`.
Components are consumed through each app's own kustomization, so groups gain no `dependsOn`.
Confirm with `flux build` that a component path outside a group's directory is allowed.

## 5. Delivery: three PRs

### PR 1: labels, admission policies (Warn/Audit), quotas, API hardening
Low blast radius: nothing is denied and no traffic changes.

1. **Namespace labels** (extend `namespaces/namespaces.yaml`):
   - `vmd1.homelab/tier=app|infra|system` and PSA labels on every entry (`warn=restricted`,
     `audit=restricted` everywhere; `enforce=baseline` for `tier=app`).
   - Add `default`, `kube-system`, `kube-public`, `kube-node-lease` to the file (labels only; SSA
     merges, prune disabled; update the "Not here" note in `namespaces/README.md`) and patch
     `flux-system` from `clusters/vmd1/flux-system/kustomization.yaml`, not the generated gotk files.
   - Namespace-scoped exemption labels (for example `policy.vmd1.homelab/allow-host-network=true`
     on `home-assistant` and `monitoring`).
   - **Draft tier map (review in the PR):**
     - `system`: `default`, `kube-system`, `kube-public`, `kube-node-lease`, `flux-system`,
       `longhorn-system`, `tailscale`, `traefik`, `powerdns`.
     - `infra`: `cert-manager`, `cf-ddns`, `cnpg`, `cnpg-system`, `geoip`, `redis`,
       `redis-operator`, `lldap`, `authelia`, `oauth2-proxy`, `registry`, `monitoring`,
       `oci-controller`.
     - `app`: `bookorbit`, `cinepro`, `gossip`, `headlamp`, `home-assistant`, `homelable`,
       `matrix`, `media`, `mqtt`, `nextcloud`, `ntfy`, `obsidian`, `qecomp`, `unifi`,
       `uptime-kuma`, `vaultwarden`, `vmd1-web`.
   - **Adoption caveat:** the first `node-labels` apply on 2026-10-25 removed labels that had been
     set by hand and weren't in the file (including `node.vmd1.homelab/public-ip` on the cloud nodes,
     which left the PowerDNS `ingress.vmd1.homelab` zone with only the home IP). Before merging,
     diff `kubectl get ns --show-labels` against the file and carry over anything still wanted.
     Only keys Flux applies are owned, so adding new keys is safe.
2. **Admission policies**, each a VAP plus a binding with `validationActions: [Warn, Audit]` and a
   `namespaceSelector` on the tier label:

   | Policy | Applies to | Rule |
   | --- | --- | --- |
   | baseline | `app`, `infra` | no privileged, hostNetwork/PID/IPC, added capabilities, unsafe sysctls (hostNetwork allowed where the namespace carries the allow label) |
   | app-hardening | `app` | runAsNonRoot, no privilege escalation, readOnlyRootFilesystem, seccomp RuntimeDefault, no `:latest`/untagged |
   | service-accounts | `app` | `automountServiceAccountToken: false` unless the SA is annotated as needing the API; no `default` SA |
   | rbac | all | `cluster-admin` bindings only to subjects in a param list; no wildcard verbs/resources |
   | storage | all | hostPath prefixes from the param allowlist; PVCs must name a StorageClass |
   | metadata | `app` | `app.kubernetes.io/name` and owner label present |
   | namespace-tier | cluster | a Namespace must carry `vmd1.homelab/tier` |
   | resource-limits | `app` | cpu/memory limits set (stays Warn permanently) |

3. **Quotas:** `quota-default` component (`ResourceQuota` + `LimitRange` by tier), sized from
   observed usage (95th percentile plus headroom) so nothing is evicted; per-app override is one patch.
4. **CI guard:** `check-policies.sh`, run from the existing `kubernetes-diff.yaml`. Every
   Namespace is defined exactly once in `namespaces/` with a valid tier; no CIDR literals in
   `policies/` outside the vars file; every `tier=app|infra` app kustomization includes
   `netpol-baseline` (reports only until PR 3); a scheduled drift check compares the vars file
   and `namespaces.yaml` with the live cluster.
5. **Cluster API hardening** (canonical in `k3s-config/`, applied by a reviewed script in
   `_scripts/` that diffs the host against Git first; not Flux-reconciled):
   - API audit logging (`audit-log-path`, `audit-policy-file`), shipped to Loki by Promtail.
   - Secrets encryption at rest: check `k3s secrets-encrypt status`, enable if off.
   - Move the etcd S3 key out of the plaintext config (SOPS or env var) and rotate it (section 10).
   - Take an etcd snapshot first and restart the control plane in a window; hades-01 is the only
     control-plane node, so a bad config means API downtime.
6. Also in this PR: `policies/README.md`, vars file, empty `policies` Flux Kustomization.

Exit: Flux Ready, no pod churn, tier label on all 39 namespaces, violation report produced
(events, audit log and Prometheus admission metrics summarised per namespace by a small script).
Each violation is fixed in the app manifest or added to a param allowlist with a comment.

### PR 2: NetworkPolicy components, pilot enrolment, Tailscale ACL tightening
1. **`netpol-baseline` component:**
   - `default-deny-all` (Ingress + Egress).
   - Egress to DNS: CoreDNS via namespace + `k8s-app=kube-dns` selector; node-local-dns via
     `NODE_LOCAL_DNS_IP`.
   - Ingress from the ingress controller. Traefik is hostNetwork, but flannel carries its traffic to
     pods: to a pod on another node the source is that node's flannel address (`10.42.N.0`, from
     `ip route get` on zeus-01: `via flannel.1 src 10.42.3.0`), and to a pod on its own node the
     `cni0` gateway (`10.42.N.1`, also the kubelet probe source seen in pod logs). It is never a
     Tailscale address, so the original 3a (allow `TAILNET_CIDR`) would have cut ingress.
     **Changed 2026-10-26:** allow `POD_CIDR` on the app's port only. No per-node data, but any
     pod can reach that port; every other port and every non-cluster source stays denied. A
     per-node reconciler (3b) that allows only the `.0`/`.1` addresses derived from the Node
     objects is the tighter option, deferred until that exposure matters.
   - Ingress from `monitoring` for scraping, selector-based, one allowed port per app via a patch.
   - Egress to the API server from `API_SERVER_CIDR`, as a separate opt-in component.
2. **`netpol-egress-public`:** for internet-facing apps, egress to `0.0.0.0/0` with
   `except: [PRIVATE_CIDRS, TAILNET_CIDR, LINK_LOCAL_CIDR]`, which blocks the cloud metadata
   endpoint and the LAN through ranges rather than single addresses. Apps that need specific
   internal peers add narrow allows.
3. **`netpol-db-client`:** namespaces labelled `vmd1.homelab/db-client=true` get egress to the
   CNPG/Redis namespaces (selected by label); the DB namespaces accept ingress only from
   namespaces carrying that label, so adding a client app is a label, not a policy edit.
4. **`netpol-egress-any`:** for apps whose job is to reach arbitrary targets (`uptime-kuma`
   probes every service, `homelable` scans the network, `qecomp` needs the local network and
   the internet, `monitoring` scrapes every namespace and node). They still get default-deny
   **ingress**, with egress explicitly allowed to anywhere, so a monitor never reports false
   outages. They are not in the pilot. `headlamp` only needs the API server and uses
   `netpol-baseline` plus the opt-in API-server component.
5. **Pilot enrolment:** `ntfy`, `gossip`, `obsidian` (single-pod apps with simple traffic:
   ingress, scrape, DNS, and few outbound calls). Allow rules come from observed flows
   (Prometheus plus short-lived `conntrack` sampling on a node), not guesses.
6. **Tailscale ACL** (`tailscale/policy.hujson`, already GitOps): replace the broad `tag:k3s` and
   `tag:k8s-operator` grants (`*` on all ports) and `tag:servers` to `autogroup:tagged` with
   explicit ports between `tag:k3s` nodes: 6443 (API), 2379-2380 (etcd), 10250 (kubelet), the
   flannel port (8472/udp) and whatever the inventory shows is needed (Longhorn, Tailscale
   operator). Keep the member grant to `tag:k3s` on 53/80/443/853/8448 exactly as it is: split DNS
   and the tailnet-only routes depend on it. Add ACL `tests` for the new denials and that
   grant. Preview with `tailscale-acl-preview`, and keep console access when applying.

Exit (soak at least 48 h before PR 3): from a throwaway pod in a pilot namespace, DNS works and
forbidden egress is dropped; ingress via Traefik works end to end; Prometheus still scrapes; the
uptime-kuma checks for the pilot apps stay green and there are no new restarts. After the ACL
change, a `tailnet-only` route works from a tailnet member and still returns the branded 403 off
the tailnet (the pilot apps have no tailnet-only route, so use an existing admin route).

### PR 3: remaining enrolments, switch admission to Deny
Opened only after PR 1's audit report has been clean for 7 days and PR 2's pilot has soaked.
1. **Enrol the remaining namespaces** by adding the component line (and the app's port/scrape
   patch) to each app kustomization, in two commits for review: the rest of `tier=app`, then
   `tier=infra` (`cnpg`, `redis`, `lldap`, `authelia` first among those). Left alone:
   `tier=system` namespaces (vendor policies for `flux-system` and `longhorn-system`;
   host-network or privileged for the rest) and `home-assistant`.
2. **Flip admission bindings** from `[Warn, Audit]` to `[Deny]`, `tier=app` first, then `infra`
   (`resource-limits` stays Warn). VAP `failurePolicy: Fail` is set here, not earlier.
3. Switch `check-policies.sh` from reporting to failing on a missing `netpol-baseline`; update
   `cluster-info.md` and `resources/README.md` (layer table).
Rollback for any single namespace: remove its component line (or revert the commit); for an admission
policy: put the binding back to `[Warn, Audit]`.

## 6. Adding a new app after this lands

1. Add its Namespace to `namespaces/namespaces.yaml` with `vmd1.homelab/tier` (and
   `vmd1.homelab/db-client=true` if it uses CNPG or Redis).
2. App `kustomization.yaml` (in `resources/<group>/<app>/`): include
   `../../policies/components/netpol-baseline`
   (and `netpol-egress-public` if internet-facing).
3. Add a one-line patch for the app port and scrape port.
That is all. No edits to any shared policy.

## 7. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| An unstable node (zeus-01) can make a bad rule look like a node fault, or the reverse | pilot first, 48 h soak, rollback = revert; `edge` isolation keeps a NotReady ingress node from stalling other groups |
| Flux adopting existing objects removes fields not in Git (seen on 2026-10-25 with node labels) | diff live labels against the file before merging; add new keys only; keep `prune: disabled` |
| PR 3 enrols many namespaces at once | each enrolment is one independent line; flows were captured per app beforehand; the two-commit split (app, then infra) lets a reviewer drop the infra commit; rollback is a revert |
| hostNetwork Traefik source IP seen differently by kube-router | resolved 2026-10-26: the source is inside `POD_CIDR` (flannel or cni0 address), so ingress allows `POD_CIDR`; confirm end to end after PR 2 merges (a request through Traefik to each pilot app) |
| Netpol or ACL changes alter the peer address the `tailnet-only` middleware sees | the `traefik` namespace stays unenrolled; after the ACL change, check an existing tailnet-only route from on and off the tailnet |
| A default-deny egress rule breaks an app that needs broad access (uptime-kuma probes, qecomp reaches the LAN and internet) | those apps (uptime-kuma, homelable, qecomp, monitoring) use `netpol-egress-any` and are enrolled last, never in the pilot |
| Tailnet/CGNAT range blocked by the private-range egress rule | `TAILNET_CIDR` is excepted only for public-facing tiers; apps that talk to tailnet services get a narrow allow |
| Tightening the Tailscale ACL cuts nodes off from each other, or breaks split DNS for members | ACL `tests` in the same PR; preview workflow; member grant to `tag:k3s` unchanged; apply with console access |
| `${...}` in existing manifests breaks if Flux substitution is enabled | no `postBuild.substituteFrom`; inject with kustomize `replacements` inside the components |
| CEL policy bugs block deploys | Warn/Audit through PR 1 and 2; server-side dry-run in CI; `failurePolicy: Fail` only in PR 3 |
| Control-plane config error (PR 1 API hardening) | etcd snapshot first; change in a window; keep the previous config file |
| A stale `namespaces.yaml` entry lingers because pruning is disabled | `check-policies.sh` compares it with live namespaces and flags unmatched ones |

## 8. Validation

- Every PR: `kubectl apply --dry-run=server`, `kubeconform` and `flux build` in CI; after merge,
  all Flux Kustomizations Ready, uptime-kuma checks green, no new restarts.
- PR 1: sample violating pods are admitted with warnings and logged, compliant ones silent.
- PR 2 and 3: the netpol checks in the PR 2 exit criteria, repeated for each newly enrolled tier.

## 9. Open items to resolve while implementing

- Whether secrets encryption is already enabled (not checked).
- Exact Traefik source-address behaviour under kube-router (decided in the PR 2 pilot).
- Whether kustomize `replacements` from the vars file work across group boundaries under
  `flux build`; fall back to per-component literals generated by a script if not.
- Quota values per namespace (from real usage).
- Final tier map (PR 1 draft above).

## 10. Unrelated issue found while exploring

`/etc/rancher/k3s/config.yaml` on hades-01 contains the etcd-snapshot S3 access/secret key in
plaintext, and it was printed into a Claude session transcript. Rotate that Backblaze application
key (PR 1 moves it out of the plaintext config).

## 11. Changes since the first draft

- Cut to three PRs; removed the control-plane-toleration / free-tier scheduling policy (so no
  `node.vmd1.homelab/class` label is needed) and the drop-ALL-capabilities rule.
- Reflects the Flux purpose-group layout and the existing `namespaces` and `node-labels` layers.
- Uses `tailscale/policy.hujson` as the ACL source. The pilot is `ntfy`, `gossip`, `obsidian`;
  uptime-kuma, homelable and qecomp are not piloted because they must reach arbitrary targets
  (they get `netpol-egress-any`). Per-namespace profiles are in Appendix A, agreed against the
  owner's corrections of 2026-10-25.
- Flux `postBuild` substitution is ruled out (literal `${...}` in 7 manifests); kustomize
  `replacements` is used instead.
- hades-02 is no longer treated as unstable; zeus-01 is the only node with a known history.

## Appendix A. Per-namespace network profile

Agreed 2026-10-25 from a manifest read plus the owner's corrections. "Baseline" is
`netpol-baseline` (default-deny, DNS, ingress from Traefik via the pod CIDR, Prometheus scrape).
Image pulls are done by the kubelet on the node, not by the pod, so NetworkPolicy never needs a
registry allow for them. Default-deny also cuts traffic between pods of the same namespace, so the baseline
includes an `allow-intra-namespace` rule. Profiles were checked against three days of podflow traffic categories
(2026-10-26).

| Namespace | Profile | Notes |
| --- | --- | --- |
| gossip | baseline | **pilot** |
| obsidian | baseline | **pilot** (CouchDB, inbound only) |
| ntfy | baseline + egress-public | **pilot**; web push to browser push services needs outbound. The SMTP relay (smtp2go, 587) and the listener on 25 are configured but unused (`emails_sent=0`); drop them from the config when convenient. Its ConfigMap holds the SMTP password and web-push private key in plaintext: move them to a SOPS Secret and rotate |
| vaultwarden | baseline + db-client + egress-public | Postgres (CNPG, seen in podflow); outbound SMTP |
| bookorbit | baseline + db-client + egress-public | internet for book metadata |
| cinepro | baseline + db-client + egress-public | Redis, `api.vmd1.homelab` |
| media | baseline + egress-public | Jellyfin metadata |
| nextcloud | baseline + db-client + egress-public | Postgres (CNPG, seen in podflow); Backblaze B2 and the app store out; Collabora is in the same namespace |
| matrix | baseline + egress-public | no database traffic in podflow (the bridges use files, not CNPG); federation to the internet |
| mqtt | baseline + LAN-ingress | LAN devices on 1883/9001; **not enrolled yet**: the source address of LAN clients through the kube-vip VIP is unverified |
| unifi | baseline + LAN-ingress + egress-public | LAN devices in; Ubiquiti SSO and cloud out; **not enrolled yet**, same reason as mqtt (MongoDB runs in the namespace, covered by the intra-namespace rule) |
| home-assistant | not enrolled | hostNetwork |
| headlamp | baseline + API server | no internet |
| homelable, uptime-kuma, qecomp | baseline + egress-any | scans / probes / LAN + internet |
| vmd1-web | baseline + egress-public + api-server | the edge-operator calls the API server and the build Jobs reach the registry and GitHub (podflow); the kubelet pulls images, so the registry is only needed for those calls |
| authelia | baseline + db-client + ldap-client + egress-public | LLDAP (ldap-client), Postgres, Redis, SMTP |
| lldap | baseline + db-client + ldap-server | Postgres (CNPG, seen in podflow); LDAP (3890, 6360) in from the `ldap-client` namespaces (Authelia, registry) |
| oauth2-proxy | baseline + egress-public | `identity.vmd1.homelab` |
| registry | baseline + ldap-client | docker-auth authenticates against LLDAP |
| cnpg | db namespace + egress-public | Postgres clients in, replication inside the namespace, Backblaze S3 backups out. **Not enrolled yet**: the `pg-cluster-rw-lb` LoadBalancer (kube-vip VIP on the LAN) may have LAN clients, and its masqueraded source address would defeat per-namespace client isolation; identify who uses the VIP first |
| cnpg-system | baseline + api-server + db-operator | operator; egress to the `cnpg` pods (status 8000, Postgres 5432); the API server's webhook calls (9443) arrive from the node's flannel address |
| redis | db namespace | clients in, replication inside the namespace; no API server. **Not enrolled yet**, same reason as `cnpg` (`redis-master-lb` VIP) |
| redis-operator | baseline + api-server + db-client | operator; egress to the `redis` pods (6379, 26379) |
| monitoring | baseline + egress-any | scrapes everything |
| cert-manager | baseline + egress-public + API server | Let's Encrypt, DNS-01 provider |
| cf-ddns | baseline + egress-public + API server | `api.ipify.org`, Cloudflare, patches node labels |
| oci-controller | baseline + egress-public + API server | OCI API; the port controller SSHes (22) to node public IPs, which egress-public allows because it only excludes private, tailnet and link-local ranges |
| geoip | baseline + egress-public | MaxMind |
| `tier=system` | not enrolled | `kube-system`, `flux-system`, `longhorn-system`, `traefik`, `powerdns`, `tailscale` |

The operator namespaces (`cnpg-system`, `redis-operator`) and the data namespaces (`cnpg`, `redis`)
get different profiles on purpose: only the operators talk to the API server, and only the data
namespaces accept database clients.

## Appendix B. Status of the NetworkPolicy rollout (2026-10-28)

The pilot (ntfy, gossip, obsidian) stays. The app-tier and infra-tier enrolments (#234, #235) were reverted in #246
after the 1 GB ingress nodes started stalling right after #235 applied, and `zeus-01` fell into a reset loop (about
one hard reset an hour, up from about one a day; 27 in 24 hours at the peak).

**The revert did not stop the stalls**, so the NetworkPolicy rollout was not the cause. What the evidence shows:
- The nodes are 954 MB with no swap. About 6 minutes after a boot `zeus-01` showed I/O pressure around 88 % and memory
  pressure around 41 %, with `k3s-agent` reading 27 MB/s, `promtail` 19 MB/s, plus `tailscaled`, containerd, PowerDNS and
  podflow: a page-cache thrash. "Available" memory (about 350 MB) overstated the headroom.
- Left alone, a node stalls for a few minutes and recovers. Two things kept `zeus-01` looping: the reboot controller reset
  it after 180 s (restarting the burst on a cold cache) and `promtail` kept its positions under `/run` (a tmpfs), so it
  re-read every container log after each boot. Both were fixed in #247 (reset threshold 600 s, cooldown 1200 s, positions
  in `/var/lib/promtail`).
- `zeus-01` and `zeus-02` began stalling in the same minute on 2026-10-26 (about 16:56), which points at a shared or
  platform cause; the trigger is not identified. An OCI stop/start of `zeus-01` on 2026-10-28 was followed by 30+ minutes
  of stable uptime. The kube-router resync of about 200 policies every 10 to 30 seconds seen in its journal is real load on
  these nodes, but it is not shown to be the cause.
- Ruled out: growth of the k3s agent (flat at about 105 MB), Tailscale traffic (low and unchanged), the ACL change.

**Before re-enrolling NetworkPolicies:**
- keep the small nodes stable for several days with the fixes above;
- cut the number of NetworkPolicy objects (drop the placeholder-only policies and the IPv6 blocks, merge the rest);
- decide whether the small ingress nodes should run the network-policy controller at all
  (`disable-network-policy` is a per-node k3s agent flag; their pods are DaemonSets);
- consider swap or zram on the 1 GB nodes (kubelet needs `fail-swap-on=false`).

The enrolment commits stay in history (`ce9bb94`, `e763d94`) and can be re-applied from there.
