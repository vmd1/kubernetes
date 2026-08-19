# Headlamp

Headlamp is an easy-to-use, extensible Kubernetes web UI. It provides a visual dashboard to manage, monitor, and configure resources within the cluster.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Full K8s manifest containing Namespace, ServiceAccount, RBAC ClusterRoleBinding, Deployment (running Headlamp), Service, and Traefik `IngressRoute` configuration. |

## Design Decisions

- **Admin Service Account Integration**: Employs `-in-cluster` and `-unsafe-use-service-account-token` args, letting Headlamp authenticate via the cluster-admin service account (`headlamp`). This removes the need for users to manually input kubeconfigs or tokens to log in.
- **SSO Authentication Gate**: Secured behind the Authentik `authentik-auth` middleware at the Traefik router level to prevent unauthorized access.

## Dependencies

- **Authentik**: Authentik namespace middleware `authentik-auth` is required to authenticate requests to the ingress.
- **K8s RBAC**: Relies on the default Kubernetes cluster-admin role mapping.

## Services & Routers

- **Kubernetes Service**: `headlamp` (ClusterIP, exposing port `80` mapping to container port `4466`).
- **Ingress Route**:
  - Host `headlamp.vmd1.homelab` on `websecure` entrypoint.
  - Middlewares: `authentik-auth` in `authentik` namespace.

## Storage

No persistent volumes (PVC) are configured for Headlamp. It is a stateless dashboard application querying metadata directly from the Kubernetes API.

## Constraints & Scheduling

- **Tolerations**: Tolerates ingress taints (`node-role=ingress:NoSchedule`), allowing the scheduler to place the pod on edge/ingress nodes.
- **Resource Constraints**:
  - Request: `50m` CPU, `128Mi` RAM.
  - Limit: `500m` CPU, `512Mi` RAM.

## Configs & Credentials

This deployment does not rely on configmaps or local secrets. Access credentials are managed through the mounted ServiceAccount token with `cluster-admin` access.
