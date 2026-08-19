# OCI Reboot Controller (oci-reboot)

The OCI Reboot Controller is a Python-based custom Kubernetes controller. It monitors the health of Oracle Cloud Infrastructure (OCI) instances running in the cluster and triggers hardware-level reboots via OCI API calls if a node remains unresponsive (NotReady) for too long.

## Namespace
`oci-controller`

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines the `oci-controller` namespace, ServiceAccount, ClusterRole/Binding for node access, Secrets containing OCI credentials, ConfigMap containing the controller code (`controller.py`), and the deployment. |

## Design Decisions

- **In-Cluster Python Agent**: Runs as a single pod watching the Kubernetes API node resources.
- **Node-to-Account Mapping**: Scalable schema that allows binding specific credentials to specific nodes based on node label `oci-account=<account-name>` mapping to secret name `oci-credentials-<region><account-name>`.
- **Safety Cooldown Guard**: Implements a 5-minute cooldown (`COOLDOWN_SECONDS=300`) and requires a node to be in `NotReady` state for at least 180 seconds before initiating an OCI RESET command, preventing reboot loops during transient API network hiccups.

## Dependencies

- **OCI API Access**: Outbound connection to `https://iaas.<region>.oraclecloud.com` to trigger instance resets.
- **Kubernetes RBAC**: Read access permissions to node status.

## Services & Routers

This service has no listening endpoints, services, or ingress routes. It is an egress-only watcher daemon.

## Storage

No persistent volume claims are used. The application configuration and source code is loaded dynamically from configmaps and secrets.

## Constraints & Scheduling

- **Target Node Labels**: Watches only nodes labeled with `oci-reboot=true`.
- **Resource Constraints**:
  - Request: `10m` CPU, `32Mi` RAM.
  - Limit: `100m` CPU, `128Mi` RAM.

## Configs & Credentials

- **ConfigMap**: `oci-reboot-controller-code`
  - Houses the `controller.py` execution script.
- **Secrets**: `oci-credentials-<region><account-name>`
  - `OCI_USER_OCID`: OCI user ID.
  - `OCI_TENANCY_OCID`: tenancy ID.
  - `OCI_COMPARTMENT_OCID`: compartment ID.
  - `OCI_FINGERPRINT`: SSH key fingerprint.
  - `OCI_REGION`: OCI region name (e.g. `uk-london-1`).
  - `OCI_KEY_CONTENT`: RSA private key for OCI authentication.
- **Env**:
  - `POLL_INTERVAL`: frequency of node scans (default `30s`).
  - `NOT_READY_THRESHOLD`: time in seconds a node must be unhealthy before reboot (default `180s`).
