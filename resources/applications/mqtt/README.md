# Mosquitto MQTT Broker

Mosquitto is a lightweight open-source message broker implementing the MQTT protocol. In this homelab, it acts as the primary messaging bus for smart home devices and Home Assistant telemetry integrations.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines the Namespace `mqtt`, the PersistentVolumeClaim for storage, ConfigMap containing the broker settings, Deployment running `eclipse-mosquitto:2.0.18`, and a `LoadBalancer` Service. |

## Design Decisions

- **Configurable Access**: Configured with `allow_anonymous true` to permit quick home IoT telemetry reporting (e.g., Tasmota, ESPHome) without certificate overhead on the internal subnet.
- **WebSocket Protocol Support**: Exposes a secondary listener on port `9001` running over WebSockets to support browser-based clients or web integrations.
- **Physical Node Binding**: Pinned to home hardware (`hades-01` in `region: uk-home`) to align with physical local network discovery and lower connection latencies.
- **Direct LoadBalancer Access**: Exposed via a standard `LoadBalancer` type service to assign a dedicated, static IP mapping (`10.0.0.10`) directly onto the Tailscale interface for external hardware integration.

## Dependencies

- **Tailscale/K3s LoadBalancer**: Relies on k3s internal load balancer provider to assign IP mapping on host interface.

## Services & Routers

- **Kubernetes Service**: `mosquitto` (LoadBalancer type).
  - Port `1883` mapping to container port `1883` (Standard MQTT).
  - Port `9001` mapping to container port `9001` (WebSockets).
- No external HTTP ingress routes are defined since communication is non-HTTP TCP.

## Storage

- **PVC**: `mqtt-pvc`
  - **Storage Class**: `longhorn-single-replica`
  - **Size**: `2Gi`
  - **Mount Point**: Mounted to `/mosquitto/data`.
  - **Data Persistence**: Stores persistent message queues and broker state between container cycles.

## Constraints & Scheduling

- **Deployment Strategy**: Set to `Recreate` deployment strategy. This restricts execution to a single replica to avoid volume locking conflicts on the backing Longhorn storage.
- **Scheduling Constraint**: Uses `nodeSelector` targeting `region: uk-home`.
- **Resource Constraints**:
  - Request: `50m` CPU, `64Mi` RAM.
  - Limit: `200m` CPU, `256Mi` RAM.

## Configs & Credentials

- **ConfigMap**: `mosquitto-config`
  - Mounts `mosquitto.conf` detailing listeners, ports, allowed connections, and persistence settings.
