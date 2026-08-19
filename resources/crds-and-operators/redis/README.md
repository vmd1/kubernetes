# Redis Master-Replica HA Cluster (redis-operator)

This directory manages the High Availability (HA) Redis Cluster using [OT-CONTAINER-KIT/redis-operator](https://github.com/OT-CONTAINER-KIT/redis-operator).

## Overview

- **Redis Operator**: Installed via Helm chart `ot-helm/redis-operator` into namespace `redis-operator`.
- **Master/Replica Replication**: Defined via `RedisReplication` CR (`kind: RedisReplication`, `apiVersion: redis.redis.opstreelabs.in/v1beta2`).
- **Sentinel Monitoring**: Managed via `RedisSentinel` CR (`kind: RedisSentinel`, `apiVersion: redis.redis.opstreelabs.in/v1beta2`).
- **Load Balancer**: HAProxy deployment exposing `redis-master-lb` (LoadBalancer on `192.168.12.221:6379` via Kube-VIP) pointing to the active master node via `redis-headless.redis.svc.cluster.local`.
- **Metrics**: `redisExporter` sidecars enabled on `RedisReplication` and `RedisSentinel` CRs scraping metrics per pod for Prometheus.

## File Manifest

| File | Purpose |
| ---- | ------- |
| [operator.yaml](operator.yaml) | Declares the K3s HelmChart for `redis-operator` v0.25.0 in `redis-operator` namespace with rightsized resources. |
| [manifest.yaml](manifest.yaml) | Defines `RedisReplication` (with exporter sidecar), `RedisSentinel` (with exporter sidecar), and HAProxy LoadBalancer Service/Deployment. |

## Node Selector & Placement

- **Redis Server & HAProxy Nodes**: Labeled with `storage.vmd1.homelab/redis-server=true`
- **Redis Sentinel Nodes**: Labeled with `storage.vmd1.homelab/redis-sentinel=true`
