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
| [operator.yaml](operator.yaml) | Declares the K3s HelmChart for `redis-operator` v0.25.0 in `redis-operator` namespace with rightsized resources. |
| [manifest.yaml](manifest.yaml) | Defines `RedisReplication` (with exporter sidecar), `RedisSentinel` (with exporter sidecar), and HAProxy LoadBalancer Service/Deployment. |

## Node Selector & Placement

- **Redis Server & HAProxy Nodes**: Labeled with `storage.vmd1.homelab/redis-server=true`
- **Redis Sentinel Nodes**: Labeled with `storage.vmd1.homelab/redis-sentinel=true`

## Probes

The operator's default probe (`redis-cli ping`, 1 s timeout, 3 failures) is too tight for a node that stalls. On 2026-11-06 hades-01 stalled and the kubelet SIGKILLed `redis-0` and `redis-2` (exit 137, 8-9 restarts each). The `RedisReplication` and `RedisSentinel` CRs now set the same exec probe with a 5 s timeout, liveness failureThreshold 6 and readiness failureThreshold 3.

A sentinel container restart is costly. The opstree sentinel entrypoint appends `sentinel monitor myMaster XXX.XXX.XXX.XXX 6379 2` to a config that the running sentinel already rewrote on the pod's emptyDir, so the next start fails with `Duplicate master name` and crash-loops until the pod is recreated. `redis-sentinel-sentinel-2` sat in that state for about 1100 restarts. Fix: `kubectl -n redis delete pod <sentinel pod>`. Avoid restarting just the container (probe failures, OOM), which is why the probes are relaxed.

## Network policy

Enrolled in the NetworkPolicy baseline (docs/cluster-hardening-plan.md, Appendix F): baseline, api-server, db-client. Ingress 8081, metrics 8080. Same-namespace traffic is allowed; everything else is denied by default.

