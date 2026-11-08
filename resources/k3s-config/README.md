# k3s config (`resources/k3s-config/`)

Canonical content of the k3s control-plane settings that Flux cannot apply because they live on the host. Audit logging was installed on hades-01 on 2026-10-26; secrets encryption is not installed yet. **Not reconciled by Flux**: [../../_scripts/apply-k3s-config.sh](../../_scripts/README.md) diffs and installs them over SSH.

## Files

| File | Installed as | Description |
| :--- | :--- | :--- |
| [config.yaml.d/10-audit-logging.yaml](config.yaml.d/10-audit-logging.yaml) | `/etc/rancher/k3s/config.yaml.d/10-audit-logging.yaml` | The API audit-log flags (appended to the existing `kube-apiserver-arg`). |
| [config.yaml.d/20-secrets-encryption.yaml](config.yaml.d/20-secrets-encryption.yaml) | `/etc/rancher/k3s/config.yaml.d/20-secrets-encryption.yaml` | `secrets-encryption: true`. Not installed unless `--with-encryption` is passed. |
| [config.yaml.d/30-leader-election.yaml](config.yaml.d/30-leader-election.yaml) | `/etc/rancher/k3s/config.yaml.d/30-leader-election.yaml` | 60 s lease / 45 s renew deadline for the in-process controller-manager, scheduler and cloud-controller-manager, so a node stall no longer ends in `leaderelection lost` and a k3s exit. See [hades-01 control plane stalls](#hades-01-control-plane-stalls). |
| [k3s.service.d/20-memory-protect.conf](k3s.service.d/20-memory-protect.conf) | `/etc/systemd/system/k3s.service.d/20-memory-protect.conf` | `MemoryLow=2G`, `OOMScoreAdjust=-900`: the kernel reclaims from pods before it swaps k3s. Needs `systemctl daemon-reload` before the restart. |
| [audit-policy.yaml](audit-policy.yaml) | `/etc/rancher/k3s/audit-policy.yaml` | What the API server logs: metadata only for Secrets/ConfigMaps, full request and response for RBAC and admission changes, no routine node reads or events. |

## Applying (by hand, in a window)

1. Take an etcd snapshot (`k3s etcd-snapshot save`).
2. `_scripts/apply-k3s-config.sh <ssh-target>` to review the diff, then with `--apply`. It never restarts k3s.
3. Restart the control plane (`systemctl restart k3s`). The control plane is a single node, so the API is down for the restart.
4. Re-encrypt existing Secrets: `k3s secrets-encrypt status`, then `k3s secrets-encrypt reencrypt` once it reports the new key is active.
5. Update [../../../docs/host-config.md](../../../docs/host-config.md) with the date applied.

## hades-01 control plane stalls

Diagnosed 2026-11-08 (k3s had restarted 25 times; kube-vip, cloud-provider, Flux, cnpg and the Longhorn CSI sidecars all restarting with it).

**Chain of events**

1. hades-01 (Raspberry Pi 5, 4 cores, 8 GB) runs the control plane and 56 workload pods. Pod memory is about 5.2 GB (Home Assistant 1.15 GB, Longhorn managers and instance managers about 1.1 GB, Collabora, Postgres, Jellyfin, ...), anonymous memory is 5.8 GB, and k3s itself is 1 GB RSS (3.7 GB peak with 2.9 GB swap before the last restart). Total demand is above 8 GB.
2. The only swap is a 4 GB zram device with `vm.swappiness=100` (two sysctl files disagree, 10 and 100; 100 wins), so swap is carved out of the same RAM. MemAvailable sat at 600-950 MB for the whole 7 days in Prometheus, with 10-70 MB/s of swap-out the entire time. Page cache is squeezed to about 1 GB, so file-backed pages (the k3s binary included) refault constantly: about 27 billion major faults and 154 OOM kills since boot.
3. CPU requests are at 96% of allocatable (limits 607%), load average 24 on 4 cores, `k3s-server` at 75% CPU. etcd's WAL fdatasync takes 1-2 s on a healthy NVMe (about 1,000 warnings a day), and 44,000 "apply request took too long" warnings a day.
4. A Lease renewal to the local API server times out. The in-process controller-manager / cloud-controller-manager logs `leaderelection lost` and exits, which kills k3s (`status=1/FAILURE`, 15:09:53 UTC on 2026-11-08). systemd restarts it 5 s later.
5. Each restart returns 503s from the API for about 30 s, fails every probe on the node, makes kube-vip lose its leases (and leaves stale VIPs), and brings Flux, cnpg and Longhorn controllers back cold. The cold start adds CPU and memory load, so the next stall comes sooner.

**Not the cause**: etcd size and object counts are small (about 200 pods, 700 events, 3,400 lease PUTs), the kernel never OOM-killed k3s, the disk is NVMe, the host was not under-voltage or throttled (`get_throttled=0x0`), and the node did not reboot.

**Fixes, in order**

1. Install the two drop-ins above (stops one slow lease renewal from killing k3s, and keeps k3s resident). Needs a k3s restart in a window.
2. Cut memory demand on hades-01 by about 1.5-2.5 GB. Everything pinned to `topology.kubernetes.io/zone=uk-home` can only use hades-01 or hades-02, and hades-02 is also at 75% of its memory requests, so there is no room to rebalance: reduce, or add a node (see below). Candidates: Home Assistant (limit 2.1 GB, 1.15 GB used), Collabora (7 spare kit processes; set `--o:num_prespawn_children=1`, or scale to 0 when not editing documents), Jellyfin, Longhorn's second instance manager.
3. Add capacity: another 8 GB+ node in `uk-home` (or an x86 mini PC), then taint hades-01 `node-role.kubernetes.io/control-plane:NoSchedule` and give the system pods that must stay (Longhorn, kube-vip, multus, node exporters) a toleration. A control plane next to 56 pods on 8 GB will keep stalling whatever the timeouts are.
4. Set kubelet `kube-reserved` / `system-reserved` and `eviction-hard: memory.available<300Mi` on hades-01 so the scheduler leaves headroom and the kubelet evicts a pod before the node thrashes. Do this after step 2 or 3: memory requests are already 80% of allocatable, and reserving 1.5 GB would leave some pods unschedulable.
5. Remove the conflicting `vm.swappiness` file so the value is deliberate (zram with a working set above RAM is better at 30-60 than at 100).

## Design Decisions

- **Drop-in, not an edit of `config.yaml`**: the `+` suffix appends to the arrays already there, so the file holding the node IP, flannel interface and etcd snapshot settings is left alone.
- **No secrets here**: the etcd snapshot S3 key in `/etc/rancher/k3s/config.yaml` is plaintext on the host and should be moved out and rotated; that is a host change and is not part of this PR.
- **Not yet shipped to Loki**: `monitoring-agents` runs on the ingress nodes only, so the audit log on the control plane is read on the host until a collector is added.

## Related

- [../policies/admission/README.md](../policies/admission/README.md) — policy violations appear in this audit log.
- [../../../docs/host-config.md](../../../docs/host-config.md) — host config outside GitOps.
