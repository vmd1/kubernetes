# Redis Master-Replica HA Cluster (redis-operator)

This directory manages the High Availability (HA) Redis Cluster using [OT-CONTAINER-KIT/redis-operator](https://github.com/OT-CONTAINER-KIT/redis-operator).

## Overview

- **Redis Operator**: Installed via Helm chart `ot-helm/redis-operator` into namespace `redis-operator`.
- **Master/Replica Replication**: Defined via `RedisReplication` CR (`kind: RedisReplication`, `apiVersion: redis.redis.opstreelabs.in/v1beta2`).
- **Sentinel Monitoring**: Managed via `RedisSentinel` CR (`kind: RedisSentinel`, `apiVersion: redis.redis.opstreelabs.in/v1beta2`).
- **Load Balancer**: HAProxy deployment exposing `redis-master-lb` (LoadBalancer on `XXX.XXX.XXX.XXX:6379` via Kube-VIP) pointing to the active master node via `redis-headless.redis.svc.cluster.local`.
- **Metrics**: `redisExporter` sidecars enabled on `RedisReplication` and `RedisSentinel` CRs scraping metrics per pod for Prometheus.

## File Manifest

| File | Purpose |
| ---- | ------- |
| [operator.yaml](operator.yaml) | Declares the K3s HelmChart for `redis-operator` v0.27.0 in `redis-operator` namespace with rightsized resources. |
| [manifest.yaml](manifest.yaml) | Defines `RedisReplication` (with exporter sidecar), `RedisSentinel` (with exporter sidecar), and HAProxy LoadBalancer Service/Deployment. |

## Node Selector & Placement

- **Redis Server & HAProxy Nodes**: Labeled with `storage.vmd1.homelab/redis-server=true`
- **Redis Sentinel Nodes**: Labeled with `storage.vmd1.homelab/redis-sentinel=true`

## Probes

The operator's default probe (`redis-cli ping`, 1 s timeout, 3 failures) is too tight for a node that stalls. On 2026-11-06 hades-01 stalled and the kubelet SIGKILLed `redis-0` and `redis-2` (exit 137, 8-9 restarts each). The `RedisReplication` and `RedisSentinel` CRs now set the same exec probe with a 5 s timeout, liveness failureThreshold 6 and readiness failureThreshold 3.

A sentinel container restart is costly. The opstree sentinel entrypoint appends `sentinel monitor myMaster XXX.XXX.XXX.XXX 6379 2` to a config that the running sentinel already rewrote on the pod's emptyDir, so the next start fails with `Duplicate master name` and crash-loops until the pod is recreated. `redis-sentinel-sentinel-2` sat in that state for about 1100 restarts. Fix: `kubectl -n redis delete pod <sentinel pod>`. Avoid restarting just the container (probe failures, OOM), which is why the probes are relaxed.

## Network policy

Enrolled in the NetworkPolicy baseline (docs/cluster-hardening-plan.md, Appendix F): baseline, api-server, db-client. Ingress 8081, metrics 8080. Same-namespace traffic is allowed; everything else is denied by default.


## Reconcile loop and sentinel resets (2026-11-12)

redis-operator v0.25.0 was the largest single caller of the API server by count: 10,427 of 42,602 requests in 35 minutes (24 %, about 5 per second) during the hades-01 stall, and still 2.9 per second afterwards (about 24 % of a quiet 11.8 per second). Almost all of it is `get`/`update` of the sentinel StatefulSet and its four Services, `list pods`, and a `get poddisruptionbudgets` that 404s. That is only a few percent of a core on the control plane, so it is not why hades-01 is slow. The functional problem is worse than the load.

**Two bugs in v0.25.0 (both fixed in v0.27.0)**

1. Every successful sentinel reconcile (about every 10 s) ends in `SENTINEL RESET myMaster` on all three sentinels. A reset wipes a sentinel's list of replicas and peers, which it relearns only at its next 10 s `INFO`. The sentinels therefore never hold a stable topology: on 2026-11-12 all three reported `slaves=0` while redis-2 reported two online replicas, and `sentinel replicas myMaster` was empty. A sentinel with no known replica cannot promote one, so automatic failover is effectively not working. v0.27.0: "only reset sentinels that hold stale topology entries" (#1931).
2. `SentinelMonitor` asks `SENTINEL MASTER`; if that call errors (a read timeout is enough) it assumes the master is unmonitored and sends `SENTINEL MONITOR`, which fails with `Duplicate master name`; the reconcile requeues, with `Conn has unread data` beside it. While hades-01 was swapping, 24 of these errors were logged in 30 minutes and the loop stopped by itself once load fell. The function is unchanged in v0.27.0, but v0.27.0 also "keeps reconciling the sentinel group while replication pods are unreachable" (#1932) and stops persisting `/etc/redis` for sentinels (#1934), which is the root of the `Duplicate master name` crash-loop described under Probes.

**Fix: upgraded the chart 0.25.0 to 0.27.0 on 2026-11-12.** `helm upgrade` does not update CRDs, so the v0.27.0 `Redis`, `RedisCluster`, `RedisReplication` and `RedisSentinel` CRDs were applied by hand first (`kubectl apply --server-side --force-conflicts -f https://raw.githubusercontent.com/OT-CONTAINER-KIT/redis-operator/v0.27.0/charts/redis-operator/crds/crds.yaml`, 1.7 MB; the larger RedisReplication schema costs the apiserver some heap). Do the same for any future chart bump, before merging it. After the bump the operator should stop resetting sentinels: `sentinel replicas myMaster` on each sentinel lists two replicas and `sentinel master myMaster` shows `num-slaves 2`, `num-other-sentinels 2`.

`kubectl -n redis delete pod <sentinel>` rebuilds a sentinel's state; see Probes.

## Upgrade to v0.27.0: what happened (2026-11-12)

The chart bump worked (all three sentinels now report `slaves=2,sentinels=3`, `sentinel ckquorum` is OK on each, the sentinels are no longer reset every reconcile), but it was not free, and it did not lower the API load.

- **It rolled everything at once.** v0.27.0 generates a different StatefulSet template, so all three `redis` pods and all three sentinels were recreated within about a minute. The Redis pods have no PVC (emptyDir), so the data is gone on every roll: Authelia sessions were lost (users are logged out) and the `redis-master` Service had no healthy master for a few minutes. Treat any operator bump as a Redis restart and do it in a window.
- **The new operator deadlocked on the empty cluster.** The recreated pods all came up as masters with offset 0 (`redis-0` and `redis-1` both `role:master`, `redis-2` a replica of a stale IP). v0.27.0 refuses to pick a master from an ambiguous view ("No master identified in a partial or ambiguous view, keeping the last known master node", "no reachable master found ... requeueing" every ~3 s), so it never issued `SENTINEL MONITOR` and the sentinels sat on `XXX.XXX.XXX.XXX:6379` (sdown).
- **Recovery:** make the operator's recorded master (`kubectl -n redis get redisreplication redis -o jsonpath='{.status.masterNode}'`) the only master and point the others at it: `kubectl -n redis exec redis-N -c redis -- redis-cli replicaof <master pod IP> 6379`. With one master that has attached replicas the operator proceeds on its own, re-monitors the sentinels (`slaves=2,sentinels=3`) and fixes the `redis-role` labels, which the `redis-master` Service selects on. Took about two minutes. Check Authelia (`https://identity.vmd1.homelab/api/health`) afterwards.
- **API load is unchanged.** After settling, the operator still makes about 3.5 requests per second (it was 2.9 on v0.25.0): each reconcile still does about 14 `get`/`update` calls on the sentinel StatefulSet and Services. v0.27.0 fixes sentinel correctness, not load.
- **Before the next bump,** put Redis on a PVC or accept the data loss, and before merging check that the pods are not all rolled at once (`updateStrategy` partition on the StatefulSets is not exposed by the CRD).
