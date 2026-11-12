# k3s config (`resources/k3s-config/`)

Canonical content of the k3s control-plane settings that Flux cannot apply because they live on the host. Audit logging was installed on hades-01 on 2026-10-26; secrets encryption is not installed yet. **Not reconciled by Flux**: [../../_scripts/apply-k3s-config.sh](../../_scripts/README.md) diffs and installs them over SSH.

## Files

| File | Installed as | Description |
| :--- | :--- | :--- |
| [config.yaml.d/10-audit-logging.yaml](config.yaml.d/10-audit-logging.yaml) | `/etc/rancher/k3s/config.yaml.d/10-audit-logging.yaml` | The API audit-log flags (appended to the existing `kube-apiserver-arg`). |
| [config.yaml.d/20-secrets-encryption.yaml](config.yaml.d/20-secrets-encryption.yaml) | `/etc/rancher/k3s/config.yaml.d/20-secrets-encryption.yaml` | `secrets-encryption: true`. Not installed unless `--with-encryption` is passed. |
| [config.yaml.d/30-leader-election.yaml](config.yaml.d/30-leader-election.yaml) | `/etc/rancher/k3s/config.yaml.d/30-leader-election.yaml` | 60 s lease / 45 s renew deadline for the in-process controller-manager, scheduler and cloud-controller-manager, so a node stall no longer ends in `leaderelection lost` and a k3s exit. See [hades-01 control plane stalls](#hades-01-control-plane-stalls). |
| [k3s.service.d/20-memory-protect.conf](k3s.service.d/20-memory-protect.conf) | `/etc/systemd/system/k3s.service.d/20-memory-protect.conf` | `MemoryLow=2G`, `OOMScoreAdjust=-900`: the kernel reclaims from pods before it swaps k3s. Needs `systemctl daemon-reload` before the restart. |
| [config.yaml.d/40-node-allocatable.yaml](config.yaml.d/40-node-allocatable.yaml) | `/etc/rancher/k3s/config.yaml.d/40-node-allocatable.yaml` | `kube-reserved` 1 GiB + `system-reserved` 0.5 GiB and a 300 Mi `eviction-hard`, so allocatable stops equalling capacity. See [hades-01 control plane stalls](#hades-01-control-plane-stalls). |
| [k3s.service.d/30-go-memory.conf](k3s.service.d/30-go-memory.conf) | `/etc/systemd/system/k3s.service.d/30-go-memory.conf` | `GOMEMLIMIT=1536MiB`: clamps the Go heap peak of the k3s process. |
| [sysctl.d/99-zzz-vmd1-vm.conf](sysctl.d/99-zzz-vmd1-vm.conf) | `/etc/sysctl.d/99-zzz-vmd1-vm.conf` | `vm.swappiness=60`, replaces the two conflicting files. Needs `sysctl --system`. |
| [audit-policy.yaml](audit-policy.yaml) | `/etc/rancher/k3s/audit-policy.yaml` | What the API server logs: metadata only for Secrets/ConfigMaps, full request and response for RBAC and admission changes, no routine node reads or events. |

## Applying (by hand, in a window)

1. Take an etcd snapshot (`k3s etcd-snapshot save`).
2. `_scripts/apply-k3s-config.sh <ssh-target>` to review the diff, then with `--apply`. It never restarts k3s.
3. Restart the control plane (`systemctl restart k3s`). The control plane is a single node, so the API is down for the restart.
4. Re-encrypt existing Secrets: `k3s secrets-encrypt status`, then `k3s secrets-encrypt reencrypt` once it reports the new key is active.
5. Update [../../../docs/host-config.md](../../../docs/host-config.md) with the date applied.

## hades-01 control plane stalls

First diagnosed 2026-11-08 (25 restarts), re-diagnosed 2026-11-12 with a live CPU and heap profile of the k3s process (`kubectl get --raw /api/v1/nodes/hades-01/proxy/debug/pprof/profile?seconds=45`, the kubelet's pprof covers the whole k3s process), the audit log, `/proc` accounting over 30 s windows and the kernel's reclaim counters. The 11-08 conclusion ("capacity, not a bug") was incomplete: the node is not short of CPU or pods, it is short of **memory that nobody budgeted for the control plane**.

**Root cause**

hades-01 reports `allocatable.memory` equal to `capacity` (8145608Ki): no `kube-reserved`, no `system-reserved`. The scheduler and kubelet therefore treat all 7.8 GiB as pod space, yet the k3s server process alone holds 1.2 GB resident plus 0.6 GB swapped out (about 1.8 GB, peak 2.6 GB RSS + 1.7 GB swap), and the kernel needs 0.5 GB (slab 450 MB, page tables, tailscaled). The kernel has no choice but to reclaim from somebody, and it reclaims from everyone, k3s included.

**Chain of events (measured)**

1. Memory is exhausted: `AnonPages` 6.15 GB, page cache 0.7 GB, `MemAvailable` 0.5 GB, and all eight fake-NUMA slices (the Pi 5 firmware adds `numa=fake=8`) have about 30 MB free each.
2. The kernel thrashes through the 4 GB zram swap: since boot (47 h) `pswpin` 270 M pages, `pswpout` 295 M pages (about 1.1 TB each way), `workingset_refault_anon` 198 M, `pgmajfault` 340 M. Anonymous pages are swapped out and needed again almost immediately, so this is a working set above RAM, not cold pages parked in swap.
3. That reclaim is the "high CPU" of the node. Over a 30 s window: **eight `kswapd` threads use about 0.45 core**, k3s-server 0.56 core (a third of it system time: faults, zram), Longhorn engines + `tgtd` 0.37, tailscaled 0.16, podflow 0.19. The 45 s CPU profile of k3s itself has no hot function: GC 17 %, TLS/socket writes 10 %, request plumbing the rest. Audit logging is 1.7 %, gzip 4 %, kube-router 1.4 % CPU (but 1.9 GB of allocations in `syncPodFirewallChains`).
4. etcd and the apiserver stall: etcd answers slowly (`apply request took too long` about 5,300 per hour, `etcd-client retrying of unary invoker failed`), apiserver handlers hit the 60 s `http: Handler timeout`.
5. k3s exits. There are **two** lease families. The three components covered by `30-leader-election.yaml` (controller-manager, scheduler, cloud-controller-manager) no longer kill k3s. The 2026-11-12 20:35:25 exit was `level=fatal msg="leaderelection lost for k3s"`: k3s's own core lease, whose timeouts are compiled in and cannot be configured. The only defence is not stalling.
6. The cold start makes it worse: informers relist, OpenAPI is rebuilt from 116 CRDs, agents re-authenticate (scrypt, 16 MB per verification), operators re-reconcile.

**What inflates the control plane (all avoidable)**

| Item | Evidence | Fix |
| :--- | :--- | :--- |
| No node reservation | allocatable = capacity | [40-node-allocatable.yaml](config.yaml.d/40-node-allocatable.yaml) |
| Go heap allowed to double | live heap 706 MB, `heap_inuse` 1.5 GB, `next_gc` 1.67 GB | [30-go-memory.conf](k3s.service.d/30-go-memory.conf) (peak clamp) |
| CRD bloat | `apiextensions` + `kube-openapi` hold 359 MB of heap for 116 CRDs (5.2 MB of schema JSON); 10 `monitoring.coreos.com` CRDs are 45 % of all schema bytes and have no instances and no owner (no Prometheus Operator runs) | unused CRDs deleted 2026-11-12, below |
| Hot reconcile loop | `redis-operator` makes 24 % of all API requests (about 5 per second during the stall, still 2.9 per second after); by count the largest caller, but only a few percent of a core | upgrade to v0.27.0, see [../operators/redis/README.md](../operators/redis/README.md) |
| No-op re-applies | Flux re-applies 17 Kustomizations every 10 min (about 3.5 requests/s, dry-run + SSA of unchanged objects); the NetworkPolicies were verified unchanged, so kube-router is not resynced by it | raise `interval`, optional |
| Status churn from CR-backed controllers | Longhorn status PUTs about 1/s; each deep-copies the unstructured object (0.9 GB allocated in 35 min) | inherent to Longhorn v1 |
| kube-vip lease renewals | about 1/s (`vip_leaseduration`/`renewdeadline`/`retryperiod` in `operators/kube-vip`) | tune only with a failover test |
| Observability agent | `podflow` pinned at its 200m limit on hades-01 (conntrack read, 5,683 entries), 170 MB | scan interval / limits, optional |
| Overlay over WireGuard | `flannel-iface=tailscale0`: pod traffic between hades-01 and hades-02 (same LAN) is VXLAN inside userspace WireGuard; tailscaled 0.16 core | architectural, not changed |

**Not the cause** (checked, clean): etcd size (59 MB, 4,153 keys) and object counts (191 pods, 754 events, 43 leases); the disk (NVMe, `get_throttled=0x0`, 57 C, governor ondemand at 2.4 GHz); the kernel OOM-killer (none in 3 h); the audit log (1.7 % CPU, 4 MB/min of writes); Flux's NetworkPolicy patches (no object changed in a 75 s watch); `vm.page-cluster` (already 0).

**Fixes, in order**

1. Reserve the control plane's memory ([40-node-allocatable.yaml](config.yaml.d/40-node-allocatable.yaml)). This is the structural fix: it makes the scheduler and the kubelet account for k3s, caps the kubepods cgroup so pressure stays inside it, and adds a kubelet eviction threshold.
2. Optional rebalancing: with a 1 GiB k3s reservation the kubepods limit is about 6.0 GiB against a 4.8 GiB working set, so it fits without moving anything; if the working set grows past about 5.5 GiB, move workload to hades-02 first (it has 3.3 GB available, no swap; but its CPU *requests* are 94 %, so pods moved there need their `requests` trimmed to measured usage first: HA, Prometheus, continuwuity and Jellyfin request more than they use). Candidates by size on hades-01: Home Assistant 1.0 GB (`hostNetwork`), continuwuity 610 MB, Prometheus 527 MB, Longhorn instance-manager 612 MB (must stay with its volumes).
3. Shrink the apiserver's own footprint: delete the unused CRDs (done, below), install the Go memory clamp ([30-go-memory.conf](k3s.service.d/30-go-memory.conf)).
4. Stop the loops: redis-operator (its README), then optionally raise the Flux `interval` from 10 m.
5. Tidy the swap setting ([sysctl.d/99-zzz-vmd1-vm.conf](sysctl.d/99-zzz-vmd1-vm.conf)); hygiene only.
6. If memory is still above about 85 % after 1-5, taint hades-01 `node-role.kubernetes.io/control-plane:NoSchedule` and tolerate only what must stay (Longhorn, kube-vip, multus, whereabouts, node exporters): a control plane should not share its RAM with 68 pods.

**Rolling this out** (done 2026-11-12 21:34 UTC: allocatable 8145608Ki to 6265544Ki, swap-in/out about 1100/1600 to 88/227 pages/s ninety seconds after the restart; steps kept for reference;  the single control plane means the API is down for the restart)

1. `k3s etcd-snapshot save`.
2. Check pod memory first (step 2 above): the new kubepods limit is about 6.0 GiB and the current pod working set is about 4.8 GiB (`kubectl top pods`), so it fits, but a pod that outgrows it is OOM-killed inside kubepods.
3. `_scripts/apply-k3s-config.sh <ssh-target>` to review the diff, then with `--apply`.
4. On the host: `sudo sysctl --system`, `sudo systemctl daemon-reload`, `sudo systemctl restart k3s`. Remove `/etc/sysctl.d/99-swappiness.conf` and `99-zram.conf` once the new file is confirmed.
5. Verify: `kubectl get node hades-01 -o jsonpath='{.status.allocatable.memory}'` is about 6.0 Gi; `grep -E 'pswp(in|out)' /proc/vmstat` twice 60 s apart (the rate should fall from about 1,700 pages/s toward 0); `top -H` shows `kswapd*` near idle; `k3s.service` memory.swap.current falls.

**Unused CRDs: deleted 2026-11-12.** 27 CRDs with zero instances, no Helm or Flux owner and no running consumer were removed by hand (116 -> 89): the ten `*.monitoring.coreos.com`, the seventeen `*.hub.traefik.io` found on the cluster, `bfddropprofiles.metallb.io` and `podlogs.monitoring.grafana.com` (MetalLB, Prometheus Operator, Alloy and Traefik Hub are not installed; Traefik runs with `--providers.kubernetescrd` only). Their definitions were saved before deletion and can be re-applied with `kubectl apply --server-side -f`. The `hub.traefik.io` CRDs may be re-created by the next Traefik chart upgrade; if they return, turn Hub off in the chart values rather than deleting them again. The CNPG, Redis, Longhorn, Traefik (`traefik.io`), cert-manager, Tailscale and Flux CRDs stay: they are bundled with running controllers that watch them. The k3s heap only shrinks after the next k3s restart.

## Design Decisions

- **Drop-in, not an edit of `config.yaml`**: the `+` suffix appends to the arrays already there, so the file holding the node IP, flannel interface and etcd snapshot settings is left alone.
- **No secrets here**: the etcd snapshot S3 key in `/etc/rancher/k3s/config.yaml` is plaintext on the host and should be moved out and rotated; that is a host change and is not part of this PR.
- **Not yet shipped to Loki**: `monitoring-agents` runs on the ingress nodes only, so the audit log on the control plane is read on the host until a collector is added.

## Related

- [../policies/admission/README.md](../policies/admission/README.md) — policy violations appear in this audit log.
- [../../../docs/host-config.md](../../../docs/host-config.md) — host config outside GitOps.
