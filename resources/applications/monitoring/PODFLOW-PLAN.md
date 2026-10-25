# Pod flow visibility plan (`podflow`)

Status: Phase 0 (measurement) done 2026-10-21; Phases 1-4 implemented 2026-10-23 and deployed 2026-10-24 (see "Implementation notes" at the end). Dashboards (Phase 6) and tailnet attribution (Phase 5) are not built.

## Goal

Per-pod network flow visibility for the whole cluster, in the style of a router's flow-stats pages:

| View | Content |
| :--- | :--- |
| Pod Traffic | Table of pods: RX/TX rate, 7d and 30d RX/TX, active/idle. Click through to a pod. |
| Pod Detail | One pod: 15m / 1h / 1d / 7d / 30d history, categories, top peers, recent flows. |
| Traffic Categories | Volume and rate by category and application, cluster-wide or per namespace/pod. |
| Active Flows | Top 50 flows by rate (src, dst, ports, protocol, classification, category) with a minimum-rate filter. |
| Connection History | Recently closed flows (25/50/100 rows) with duration, RX/TX, classification, closed-at. |

Constraints: pod-to-pod traffic included; identify the pod on both ends; cover Tailscale exit-node pods; Loki +
Prometheus together at most 70Gi; retention at most 30d; the Tailscale free plan has no flow logs; no CNI change
(Cilium/Hubble rejected: 1GB edge nodes, live flannel-over-Tailscale cluster, little policy to gain).

## Facts measured on 2026-10-21 that shaped the plan

| Fact | Value | Consequence |
| :--- | :--- | :--- |
| Pods | 183 | Per-pod metric series stay small (a few thousand). |
| Prometheus today | 7d retention, 30Gi PVC, 6.1GB used, 195,842 head series | 30d at the same series count is about 26GB, so cut series. About 55k series are apiserver/etcd histogram buckets. |
| Loki today | 10Gi PVC, 2.1GB used, 720h retention, Traefik + auth.log only | Room for flow logs once the PVC grows. |
| Storage | Every Longhorn volume is single-replica on hades-01's only Longhorn disk (233GB, 109GB free, 180GB scheduled). hades-02 has `create-default-disk=false` | The 70Gi budget lands on one disk. Check headroom before each expansion. |
| hades-02 memory | 7.3GB total, about 1.1GB available | Loki and Prometheus both run there. Bigger Loki limits need care. |
| Edge nodes | 6 x 1GB, 55-65% used (about 350-450Mi free) | The agent must stay under about 64Mi. |
| conntrack tables | hades-02 about 4,100 entries, zeus-02 about 565 (max 131,072 each), `bridge-nf-call-iptables=1` | Cheap to read. Same-node pod-to-pod traffic is tracked. |
| conntrack interface | `/proc/net/nf_conntrack` and `/proc/net/stat/nf_conntrack` do not exist (procfs compiled out), no `conntrack` binary | Netlink is the only way in. The plan already uses it. |
| `nf_conntrack_acct` / `nf_conntrack_timestamp` | both 0 on hades-02 | Byte counts and start times are off. The agent must enable them. |
| Pod networking | flannel (vxlan over `tailscale0`), `cni0` 10.42.x.1/24 per node | Cross-node flows are tracked on both nodes. Dedupe rule below. |
| DNS path | Pods use CoreDNS `10.43.0.10` directly. The `node-local-dns` DaemonSet does not exist (the `nodedns` entry in `cluster-info.md` is stale) | Do not rely on node-local-dns. hostNetwork pods use the node resolver, whose DNS never crosses `cni0` (zeus-02 saw zero DNS packets on `cni0` in 10 minutes), so sniff all interfaces with a port-53 BPF filter. |
| Controllers | Python images in `controllers/`, built by `controller-images.yaml`; the image list is hard-coded in `.github/scripts/controller-images-changes.sh` | The agent is Go for memory reasons. A Dockerfile build works for any language. Add `podflow` (and `podflow-ts`) to the `IMAGES` array. |
| Measured flow rates (10 min, 2026-10-21) | zeus-02: 5.8 new/s, 5.3 closes/s, about 455k closes/day. hades-02: 35 new/s, 16 closes/s (peak 55 new/s), about 1.41M closes/day. 54% (zeus-02) and 77% (hades-02) of closed flows carried under 1KB. Only 6-12 flows over 100KB per 10 minutes. Flows with at least 1KB moved per minute: 10-14 (zeus-02), 5-26 (hades-02) | Volume is moderate, and most of it is DNS, health probes and overlay transport, which the aggregation rules below remove. |
| Overlay share | UDP 8472 (vxlan) was 46% of closed flows on hades-02 and 9% on zeus-02. DNS was 16% and 15% | Excluding overlay from logs and aggregating DNS removes more than half the lines. |
| Event loss | hades-02 hit 17 `ENOBUFS` socket overflows in 10 minutes with a default-sized buffer | Events alone lose flows. The periodic dump must be the source of truth. |

## Architecture

```
 every node (DaemonSet podflow, hostNetwork)
   conntrack netlink (NEW/UPDATE/DESTROY + 30s dump)  --\
   DNS replies sniffed on cni0 (IP -> hostname)         --+--> flow table --> Prometheus :9477 /metrics
   pod/service cache (kube API, in memory)              --/                |
   GeoLite2 Country + ASN (/var/lib/geoip, read-only)                      +--> JSON lines on stdout
   rules ConfigMap (app/category classifier)                                     |
                                                                       promtail (existing) --> Loki
 Grafana (existing): Prometheus panels + Loki panels
```

## Agent design

**Capture.** Read conntrack through netlink in the host network namespace. Subscribe to DESTROY events (final
counters) and run a periodic dump every 30s to get deltas for flows still open. The dump is the source of truth for
metrics; events only make close lines timely. Measured on hades-02: 17 `ENOBUFS` overflows in 10 minutes at
35 new flows/s, so the socket uses `SO_RCVBUFFORCE` with several MB, and any flow that vanishes from the dump without
a DESTROY event gets a close line from its last dump values. A drop counter is exported. Conntrack's own
duration includes the idle-timeout tail (UDP 30s, TCP close/time-wait), so the log line's duration is last-active
(from the 30s dumps, plus or minus 30s) minus start. The agent enables
`net.netfilter.nf_conntrack_acct=1` and `nf_conntrack_timestamp=1` in a privileged init container, so it is GitOps and
survives node rebuilds. IPv4 only, matching the cluster. IPv6 events are counted and ignored.

**Identity.** Resolve both ends of every flow:
- Pod IP to pod, namespace, owning workload and node, from an in-memory pod cache (full pod watch, about 183 pods, a
  few MB).
- Service ClusterIP and LoadBalancer IP to Service. For Service-bound flows the conntrack original destination is the
  Service and the reply source is the backend pod, so both are logged (`via_service`).
- Node IP to node. Host-network pods (Traefik, kube-vip, node-local-dns, whereabouts) share the node IP and are logged
  as the node. Per-process attribution is out of scope.
- Anything else is `external`, tagged with country and ASN organisation.
- Tailscale exit-node pods are normal pods. Clients' traffic leaves via the pod's `eth0` after NAT inside the pod, so
  the core agent attributes the flow to the `ts-*` pod. Per-device attribution comes from Phase 5 (reading conntrack
  inside the pod's network namespace, where the client's `100.x` address is still the source).

**Deduplication.** A cross-node flow exists in conntrack on both nodes. Rules:
- Per-pod byte metrics are computed only from entries where that pod is a local endpoint, so each pod is counted once,
  on its own node.
- A flow log line is emitted only by the node hosting the source (original source) endpoint. If the source is not a
  cluster endpoint (an external client), the node hosting the destination emits it.
- Overlay transport (flannel vxlan UDP 8472, WireGuard UDP 41641 between nodes) is categorised `Overlay`. It is in
  metrics (identity `_host`) but not logged by default (`LOG_OVERLAY=false`), because it duplicates all pod traffic.

**Enrichment.**
- Hostnames: parse DNS responses (UDP/TCP 53) with an AF_PACKET socket on all interfaces (`any`) with a kernel BPF
  filter for port 53, so only DNS reaches userspace. Build an IP to name map honouring TTL plus 10 minutes, LRU capped
  at 20k entries. `cni0` alone is not enough: hostNetwork pods resolve through the node resolver. Measured DNS on
  hades-02: about 8.5 queries/s, all UDP.
- Country and ASN: GeoLite2-Country (already on every node via geoip-updater) plus GeoLite2-ASN. ASN needs adding to
  the geoip-updater editions list. Reloaded when the file changes.
- Classification: ordered rules (compiled into the image; an optional `RULES_FILE` JSON array is matched first, so a ConfigMap can override them). A rule matches protocol, destination port,
  hostname suffix, ASN organisation, and source/destination namespace, and yields `(app, category)`. Seed rules:
  Tailscale, WireGuard, DNS, TLS, QUIC, HTTP, Postgres, Redis, MQTT, LDAP, SMTP, NTP, SSH, Kubernetes API, etcd,
  kubelet, Longhorn (iSCSI), Flannel (Overlay), Backblaze B2/S3, Cloudflare, Google. Categories: VPN, Web, Database,
  Cache, Storage, DNS, Kubernetes, Email, Auth, Messaging, Monitoring, Overlay, Other, unclassified. This is
  port/hostname/ASN based, not deep packet inspection.

**Outputs.**

Prometheus metrics on a hostNetwork port (9477, confirm it is free), scraped through the existing
`kubernetes-pods` job (confirm the annotation convention there, else add a job):
- `podflow_bytes_total{ns,pod_name,workload,direction,application,category}`
- `podflow_flows_total{ns,pod_name,workload,application,category}` (closed flows)
- `podflow_peer_bytes_total{namespace,workload,direction,peer_kind,peer_namespace,peer_workload,peer_country}`
  (workload level, for pod-to-pod and Service maps)
- agent health: dropped events, flow-table size, DNS cache size, unresolved endpoint ratio

Estimated 3-5k series, about 2.5% of today's 196k.

Flow log lines (JSON, one per flow), two event types:
- `close`: one line when a flow ends.
- `active`: one line per 60s for flows that moved at least 1KB in the interval. This feeds Active Flows and covers
  long-lived flows.

```json
{"ts":"2026-10-21T18:05:16Z","event":"close","node":"hades-02","proto":"tcp",
 "src":{"kind":"pod","ns":"nextcloud","pod":"nextcloud-6d9f","workload":"deploy/nextcloud","ip":"10.42.2.40","port":41312},
 "dst":{"kind":"external","ip":"45.11.36.254","port":443,"host":"s3.eu-central-003.backblazeb2.com","country":"NL","org":"Backblaze"},
 "via_service":null,"app":"TLS","category":"Web","duration_ms":15000,
 "tx_bytes":4800,"rx_bytes":9970,"tx_pkts":21,"rx_pkts":24,"count":1}
```

Loki labels stay low-cardinality: `job="podflow"`, `node_name`, `event`. Everything else is parsed at query time with
`| json`. Short flows are aggregated per source, destination, port and protocol over 60s into one line with `count`
and summed bytes, so no flow is lost from the record but DNS lookups and health probes do not dominate volume.
"Short" means under 1KB total (conntrack duration is not usable for this, see Capture), and ICMP and UDP/53 always
aggregate. Both the 60s window and the 1KB threshold are settings.

**Runtime.**
- DaemonSet in `monitoring`, all nodes, tolerating every taint (edge nodes carry `node-role=ingress:NoSchedule`).
- Main container: root, capabilities `NET_ADMIN` and `NET_RAW` only, everything else dropped, read-only root
  filesystem, `RuntimeDefault` seccomp. Init container: privileged, only to set the two sysctls.
- ServiceAccount: get/list/watch on pods, services, nodes.
- Resources: request 20m/24Mi, limit 200m/64Mi, `GOMEMLIMIT=48MiB`. Hard caps on flow table and DNS cache.
- Image `ghcr.io/vmd1/podflow`, source in `controllers/podflow/`, pinned by digest in the manifest.

## Storage and retention budget (Loki + Prometheus <= 70Gi, retention <= 30d)

| | Now | Plan |
| :--- | :--- | :--- |
| Prometheus PVC | 30Gi | **40Gi** |
| Prometheus retention | 7d / 30GB | **30d / `retention.size=36GB`** |
| Loki PVC | 10Gi | **20Gi** (expandable later) |
| Loki retention | 720h | 720h (unchanged, already 30d) |
| Allocated total | 40Gi | **60Gi** (headroom to 70Gi if Loki needs to grow) |

Expected real usage, not allocation:
- Prometheus: 6.1GB per 7d now, so about 26GB at 30d. Dropping the apiserver/etcd histogram buckets removes about 28% of
  series, bringing it to about 19GB, plus about 1GB for podflow. The size cap protects the PVC either way.
- Loki: about 2GB today. Flow logs, from the Phase 0 rates: close lines about 2-2.7M/day cluster-wide after dropping
  overlay and aggregating short flows (hades-01 and the other edge nodes were not sampled, so this extrapolates from
  zeus-02 and hades-02), active lines about 150k/day. At about 350 bytes per line and 8x compression that is roughly
  85MB/day, so about 3GB for 30 days, 8GB if the estimate is 3x too low. Planning figure: 3-8GB flow logs, 5-10GB
  total Loki. That is why Loki is 20Gi, not 30Gi.
- Total about 25-30GB real, well inside the 60Gi allocation.

Loki has no size-based retention. Guards are the aggregation and threshold settings, a per-stream retention override
for `{job="podflow"}` if needed, and a Grafana alert on `kubelet_volume_stats_used_bytes` for `loki-pvc` above 80%.

Disk risk: everything sits on hades-01's Longhorn disk (233GB, 109GB free). Longhorn keeps a 15% minimal-available
reserve (about 35GB) and allows 200% over-provisioning (checked 2026-10-21). Real growth of about 25GB fits, but check
free space before each PVC expansion.

## Changes by file

| File | Change |
| :--- | :--- |
| `controllers/podflow/` (new) | Go agent, Dockerfile, README. Add `podflow` to the `IMAGES` array in `.github/scripts/controller-images-changes.sh`. |
| `resources/edge/podflow/podflow.yaml` (new) | ServiceAccount, ClusterRole/Binding, ConfigMap `podflow-rules`, DaemonSet. |
| `.../monitoring/manifest.yaml` | `loki-pvc` 10Gi to 20Gi; Loki memory limit review; Prometheus PVC 30Gi to 40Gi, `--storage.tsdb.retention.time=30d`, `--storage.tsdb.retention.size=36GB`; `metric_relabel_configs` dropping heavy apiserver/etcd buckets (first check no dashboard or rule uses them); promtail `keep` rule widened from `traefik` to `traefik` plus `monitoring`/`podflow`; promtail stage labelling `event`; optional recording rules for 7d/30d increases. |
| `.../monitoring/podflow-ts.yaml` (new, Phase 5) | DaemonSet `podflow-ts` (hostPID, `SYS_ADMIN` + `SYS_PTRACE`) on Connector nodes. No credentials: device names come from each Tailscale pod's own tailscaled. |
| `.../monitoring/podflow-dashboards.yaml` (new) | Dashboard ConfigMaps, mounted in the Grafana Deployment like the existing ones. |
| `.../infrastructure/geoip-updater` | Add the GeoLite2-ASN edition. |
| Docs | monitoring README, `controllers/README.md`, `cluster-info.md` (files, PVC sizes, retention, new DaemonSet; also remove the stale `nodedns` / node-local-dns entry), root README ToC if a section is added. |

PVC expansion goes through Flux. The storage classes allow expansion. If a volume does not resize online, follow the
`rwo_pvc_safe_rollout` procedure in `docs/runbooks/rwo-pvc-safe-rollout.md`.

## Dashboards (Grafana, provisioned)

- **Pod Traffic:** Prometheus instant queries per `(namespace, pod, workload)`: current rate, 7d and 30d `increase`,
  status (rate over the last 5m greater than 0). A data link opens Pod Detail with `$pod` set. Add recording rules if
  30d queries are slow.
- **Pod Detail:** history panels (15m, 1h, 1d, 7d, 30d), category donut and table, top peers from
  `podflow_peer_bytes_total`, that pod's recent flows from Loki.
- **Traffic Categories:** volume and current-rate donuts, application table with flows, down, up, rates, share.
- **Active Flows:** Loki `{job="podflow", event="active"}` over the last 2 minutes, `| json`, rate from bytes over the
  interval, top 50, minimum-rate variable (1 Kbps / 100 Kbps / 1 Mbps / 10 Mbps / 100 Mbps).
- **Connection History:** Loki `event="close"`, row-limit variable 25/50/100, filters for pod, namespace,
  destination, port.

## Phases (each ends with a check and a rollback)

**Phase 0 - measure. DONE 2026-10-21.** Ran a 10-minute sampler (conntrack netlink events plus 60s dumps, `acct` and
`timestamp` enabled temporarily and restored to 0 afterwards) on hades-02 and zeus-02, using `ubuntu@` with the cluster
SSH key for the edge node (`admin@` works on hades-02). Results are in the facts table above. Outcomes:
- Loki flow-log estimate narrowed from 2-15GB to about 3-8GB, so Loki is 20Gi.
- Aggregation by bytes (under 1KB), not by duration. Overlay (vxlan) excluded from logs.
- `SO_RCVBUFFORCE` plus dump-as-truth, because events are lost under load.
- DNS sniffing on all interfaces, not just `cni0`.
- No conntrack procfs, so no shortcuts: netlink only.
- Not done: hades-01 (arm64 control plane) and the other edge nodes were not sampled, and 10 minutes at one time of day
  misses backup and cron spikes. Re-check the Loki growth rate in Phase 3 against these figures.
- Sampler: not kept in the repo (it was a throwaway Python script; the agent's netlink parsing in Go replaces it).

**Phase 1 - storage and retention.** Prometheus 40Gi, 30d, size cap, bucket drops. Loki 20Gi. Check: both pods healthy,
PVCs resized, series count down, no dashboard broken. Rollback: revert the manifest commit (PVCs cannot shrink, so
leave sizes and revert only retention and relabelling).

**Phase 2 - agent core (metrics only).** Identity, dedup, Prometheus metrics. Canary on hades-02, then one edge node
(not zeus-01, which is flaky), 24h soak, then all nodes. Check: RSS under 64Mi, CPU low, dropped events near 0,
unresolved endpoints under 2%, every `ENOBUFS` recovered by the dump (no byte-total gap against cAdvisor), per-pod byte totals within a few percent of cAdvisor network counters for the same
pods. Rollback: delete the DaemonSet. It is passive, so the data path is untouched.

**Phase 3 - flow logs.** JSON lines, promtail relabel and stage, Loki queries. Canary first, then all nodes. Check:
Loki growth per day against the Phase 0 estimate, no ingestion rate-limit errors, promtail memory. Rollback: set the
log level to metrics-only or revert the promtail change.

**Phase 4 - enrichment.** DNS hostnames, GeoLite2 country and ASN (updater edition added first), classifier rules.
Check: share of flows with a hostname and with a non-`unclassified` category on a sample day.

**Phase 5 - tailnet device attribution.** Identify which tailnet device sent traffic that leaves through an exit-node
or subnet-router pod (Connectors `fr-marseille-cloud`, `in-mumbai-cloud`, `uk-home`, `uk-home-subnet-router`,
`uk-london-cloud`). Verified on 2026-10-21: the pods run `TS_USERSPACE=false`, privileged, in their own network
namespace, so the pod's conntrack table holds the original source (the client's `100.x` address) before NAT.
- **Agent.** A second DaemonSet, `podflow-ts`, separate from the core agent so the core stays unprivileged. It runs on
  the nodes hosting Connector pods (currently hades-02, zeus-02, hera-02, ares-01; use a selector that follows the
  Connectors rather than a fixed list), with `hostPID` and `SYS_ADMIN` + `SYS_PTRACE`. It finds each Tailscale
  pod's network namespace through `/proc` (matched to the pod by cgroup/UID), enters it with `setns`, and reads
  conntrack there with the same netlink code as the core agent. It also sniffs DNS inside that namespace, because
  clients may resolve names through the exit node. Budget: about 20-30Mi per pod.
- **Device names (no key, nothing to expire).** Map `100.x` to device name, owner and tags by asking the Tailscale pod's
  own tailscaled through its local API socket (`/tmp/tailscaled.sock` inside the pod, reachable from the host through
  `/proc/<pid>/root/tmp/tailscaled.sock`; `GET /localapi/v0/status`, the same data as `tailscale status --json`).
  Verified 2026-10-21 on the `uk-home` exit-node pod: the socket is world-writable (`srw-rw-rw-`) and the status lists
  22 peers with `HostName`, `TailscaleIPs`, `UserID`, `Tags`, `Online` plus a `User` map of owners. Cached and refreshed
  every minute or so. A Tailscale API key (90-day expiry) is not needed, and neither is an OAuth client; the operator's
  own `operator-oauth` credential is not touched. Limit: a pod only knows the peers its ACL view allows, which includes
  every client that uses it as an exit node or subnet router.
- **Output.** Same flow-line schema with `src.kind="tailnet"`, device name, and `via_exit_node`. Metrics:
  `podflow_tailnet_bytes_total{device,exit_node,direction,application,category}` (a few dozen series). New dashboard view
  "Tailnet Devices" with the same layout as Pod Traffic (device table, then drill-down to categories, active flows and
  connection history), filterable by exit node.
- **Dedup.** The core agent still logs the exit-node pod's own flows, now post-NAT. To avoid double counting, flows seen
  by `podflow-ts` are tagged and the core agent's matching post-NAT entries for `ts-*` pods are kept in metrics but
  not logged.
- **Check.** Generate traffic from a known device through an exit node and confirm its device name, destination and
  byte counts match the device's own view. Confirm memory and CPU on the 1GB edge nodes (zeus-02, hera-02, ares-01)
  before widening. Rollback: delete the `podflow-ts` DaemonSet (passive, the data path is untouched).
- **Not covered.** Traffic between two tailnet devices that never passes through a pod in this cluster. Only
  Tailscale's paid flow logs record that.

**Phase 6 - dashboards and docs.** The five dashboards plus the Tailnet Devices view, README and `cluster-info.md`
updates. (Dashboards can be built incrementally from Phase 2 on; this phase is the final polish and docs.)

Optional later, not committed to: real deep packet inspection (nDPI) on hades-01/02 only, if port/hostname
classification proves too coarse.

## Limits (known and accepted)

- Until Phase 5 is done, exit-node clients cannot be told apart (only the exit-node pod is visible). After Phase 5 they
  can, but only for traffic that passes through a Connector pod in this cluster. Device-to-device tailnet traffic
  that bypasses the cluster stays invisible (needs Tailscale's paid flow logs).
- Host-network pods appear as the node.
- Classification is rule-based. Expect more `unclassified` than the router's nDPI.
- Week and 30-day totals depend on Prometheus keeping 30d. If retention is cut, they shrink with it.
- Loki on hades-02 (about 1.1GB available memory) is the tightest resource. Moving Loki's affinity preference to
  hades-01 is the fallback if memory is short.

## Defaults chosen (change before Phase 2 if you disagree)

1. Agent in Go (memory), not Python like the other controllers.
2. Short flows are aggregated with a count, not dropped.
3. Overlay (vxlan/WireGuard) flows are metrics-only, not logged.
4. ASN data comes from adding GeoLite2-ASN to geoip-updater.

## Implementation notes (2026-10-23)

What was built (source: `controllers/podflow/`, deployment: `edge/podflow/podflow.yaml`), and where it differs from the
plan above:

- **Go, as planned.** A `scratch` image (about 7MB binary), standard library plus `golang.org/x/sys` and
  `maxminddb-golang`. No client-go and no Prometheus client library (heap and binary size). The Kubernetes cache is a
  hand-written list+watch.
- **Metric label names** are `ns`, `pod_name`, `workload`, `application` (not `namespace` / `pod` / `app`), because the
  `kubernetes-pods` job copies the pod's own labels onto every series (`namespace`, `pod`, and `app=podflow`), which
  would shadow them as `exported_*`. The first deployment showed exactly that for `app`. Host-network and node traffic is `ns="_host"`,
  `pod_name=<node>`.
- **Rules** ship in the image rather than in a `podflow-rules` ConfigMap; `RULES_FILE` allows an override later.
- **Baselining.** Flows that were already running when the agent starts (first dump, or start time before the agent)
  use their counters as a baseline, so a restart does not count their history as new traffic.
- **Reconcile guard.** A flow closed by the dump reconcile is remembered for a minute so its late DESTROY event is
  not counted twice.
- **Node identity** includes the `node.vmd1.homelab/public-ip` label (zeus-01's node object only knows its Tailscale
  address).
- **Local test (2026-10-23)**, real binary on zeus-02 and hades-02 against live conntrack with a snapshot of the
  cluster state: resident memory 17MB (zeus-02) and 21-23MB (hades-02), dump of 1,800 entries in 33ms, zero
  `ENOBUFS` overflows with `SO_RCVBUFFORCE`, no duplicate close lines, 3.2 close lines/s and 1.6-3 active lines/s on
  hades-02 (about 275k and 140-275k lines/day), and almost all flows classified after adding rules for the ports the
  test showed (containerd 10010, exporters, Authelia, Collabora, UPnP/NAT-PMP).
- **Known gaps:** GeoLite2-ASN is only available once geoip-updater has the new edition (until then `org` is empty and
  rules fall back to hostnames). DNS answers are learned for private addresses too, which is harmless. No dashboards.
- **For Phase 6:** Prometheus runs with `--query.max-samples=1000000`. A 7d or 30d `increase()` over a few hundred
  `podflow_bytes_total` series needs tens of millions of samples, so the pod table needs recording rules (hourly
  increases, `rule_files` is not configured yet) or a higher limit.

## Deployment notes (2026-10-24)

- **Rollout:** PRs #176 (storage/retention), #177 (agent), #179 (promtail, GeoLite2-ASN), #180 (DaemonSet), #181/#182
  (metric label fix). The agent runs on all 8 nodes: 11-28MB resident, no event overflows, targets up in Prometheus,
  flow lines in Loki from every node (about 9,400 lines per 5 minutes cluster-wide, so about 2.7M lines/day; at the
  planned 8x compression roughly 4GB for 30 days, inside the 20Gi Loki volume).
- **Series:** Prometheus went from about 196k to 136k series after the apiserver/etcd bucket drop, plus about 2k for
  podflow.
- **Bug found during verification:** the `kubernetes-pods` job copies the pod's labels onto every series, so
  `app="podflow"` replaced the agent's `app` metric label. Renamed to `application` (#181).
- **GHCR visibility:** the `ghcr.io/vmd1/podflow` package is created private; it had to be made public by hand
  (the API cannot do it) before nodes could pull it.
- **PVC expansion was stuck, then fixed (2026-10-24).** `prometheus-pvc` (30Gi to 40Gi) and `loki-pvc` (10Gi to 20Gi)
  showed `Resizing`: the hades-02 Longhorn instance manager had cached a stale host PID, so the engine could not
  refresh the iSCSI initiator. Restarting that instance manager with the three affected workloads (loki, prometheus,
  matrix continuwuity) scaled down fixed it; both PVCs are now 40Gi/20Gi and Prometheus kept all its data. Procedure:
  `longhorn_expansion_stuck` in `docs/runbooks/longhorn-expansion-stuck.md`.
- **OOM during that maintenance:** two podflow pods on the hades nodes were OOMKilled at the 64Mi limit while Longhorn
  reattached volumes (a burst of new connections; the limit also covers the mmapped GeoLite2 files and the 8MB
  conntrack socket buffer). Limit raised to 96Mi (request 32Mi, `GOMEMLIMIT` 64MiB). Normal use is 20-30MB.
- **Pre-existing, unrelated:** the Prometheus `etcd` target (`10.0.0.10:2381`) is refused; it was already down before
  any of these changes.

## Incident and design change (2026-10-24, Phase 5 rollout)

Adding a second DaemonSet (`podflow-ts`) and rolling the `podflow` image at the same time took edge nodes to NotReady
(hera-01, zeus-01, ares-02, hera-02, one after another, each recovering by itself). It was not CPU or the pods' own
memory (each used 8-16MB): the nodes (1GB, no swap, about 250MB "available" of which most is hot page cache) hit
page-cache thrashing. On zeus-01 the boot volume was read at 17-47 MB/s (about 450 IOPS, the volume's limit) with
100+ major page faults per second for about 7 minutes, so the kubelet starved. Every extra pod costs more than its RSS
(container shim, pause container, its own caches), and a rollout briefly doubles it.

Changes: tailnet attribution is now a mode of the main process (`TAILNET=true`, PR "refactor(podflow): tailnet
attribution inside the main process"), so there is no second DaemonSet; the DaemonSet rolls one node at a time with
`minReadySeconds: 60`. Not done, worth considering for the edge nodes: a small swapfile or zram (they have no swap, so
the kernel's only reclaimable memory is page cache including program code), `MemoryLow=` for the kubelet and
containerd, and fewer per-node pods.

## Phase 6 notes (2026-10-24)

Dashboards are generated by `gen-podflow-dashboards.py` into `podflow-dashboards.yaml` (see the README). Checked before
deploying against a local Grafana 13.2.4 (same version as the cluster) pointed at the live Prometheus and Loki through
`kubectl port-forward`: every panel query was run through Grafana's query API with real variable values (no errors), and
each dashboard was looked at in a browser. Fixes that came out of that: the `calculateField` `include` belongs inside
`reduce`; `organize.indexByName` is keyed by the original field names; table sorting must be the table's own `sortBy`
option (a `sortBy` transformation does not see renamed fields); `extractFields` on Loki log frames also surfaces the
stream labels, which are excluded; merged Prometheus instant queries name their value columns `Value #A`.

Recording rules: 5-minute rollups for windows up to 30 days of per-namespace series and for 24h per-pod totals, hourly
rollups for 7d/30d per-pod totals, peers, flows and tailnet totals. `--query.max-samples` is 5M (it was 1M).
