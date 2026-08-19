# Cert-Manager

Cert-Manager automatically provisions, renews, and manages TLS certificates in the cluster. It leverages ACME through Let's Encrypt using Cloudflare DNS-01 validation.

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines the HelmChart custom resource that deploys `cert-manager` version `v1.20.2` in the `cert-manager` namespace. |
| [cluster-issuer.yaml](cluster-issuer.yaml) | Configures a Cluster-wide Issuer `letsencrypt-cloudflare` using the Let's Encrypt ACME server and DNS-01 challenge solving via Cloudflare. |
| [certificate.yaml](certificate.yaml) | Deploys a wildcard certificate request (`cluster-wildcard-tls`) for multiple domains (`vmd1.homelab`, `vmd1.homelab`, `vmd1.homelab`, `vmd1.homelab`, `flix4all.cc` and their wildcards) targeting the `traefik` namespace. |

## Design Decisions

- **DNS-01 Challenge**: Used instead of HTTP-01 to allow wildcard certificates and to request certificates without exposing internal DNS/ports to the public internet.
- **Custom Recursive Nameservers**: Formatted with values `1.1.1.1:53,8.8.8.8:53` to bypass potentially buggy local network DNS resolvers during self-check validation loops.
- **Unified Secret Storage**: Secret generated is placed directly in the `traefik` namespace (`cluster-wildcard-tls`), which allows Traefik to instantly mount it for TLS termination.

## Dependencies

- **CRDs**: The Jetstack Helm Chart is configured with `crds.enabled: true` to automatically load the cert-manager custom resource definitions (e.g. `Certificate`, `Issuer`, `ClusterIssuer`).
- **Cloudflare API Secret**: Requires an external secret `cloudflare-api-token` containing the `apiToken` key in the namespace of cert-manager to perform DNS record updates during Let's Encrypt validation.

## Services & Routers

- Cert-manager itself does not expose external routers. It runs internal webhook and controller APIs to communicate with the Kubernetes API server and handle certificate requests.
- **Provisioned Secret**: `cluster-wildcard-tls` (in namespace `traefik`), used by Traefik ingress routes to secure HTTPS traffic.

## Storage

- **Private Key Storage**: The ACME account private key is stored within the Kubernetes Secret `letsencrypt-cloudflare-key` in the `cert-manager` namespace.
- **Certificates Storage**: The issued PEM-formatted certificates and private keys are saved inside the `cluster-wildcard-tls` Kubernetes Secret in the `traefik` namespace. No persistent volumes (PVCs) are required as state is managed entirely using Kubernetes Secrets.

## Constraints & Scheduling

- Runs in the `cert-manager` namespace, with the Helm controller orchestrating the release in `kube-system`.
- Highly dependent on network accessibility to Cloudflare's API endpoint and the Let's Encrypt ACME API directories.

## Configs & Credentials

- **External Secret Dependency**: `cloudflare-api-token` (must contain `apiToken`).
- **ACME Account Secret**: `letsencrypt-cloudflare-key` (auto-managed by the cluster issuer).
