# UniFi Network Application

UniFi Network Application manages UniFi networking hardware (Access Points, Switches, Security Gateways).

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines `unifi` namespace, MongoDB database Deployment (`mongo:7.0`), UniFi Network Application Deployment (`lscr.io/linuxserver/unifi-network-application`), Services, MetalLB LoadBalancer (`192.168.12.10`), and Traefik `IngressRoute` (`unifi.vmd1.homelab`). |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `unifi-db-secrets` (credentials for MongoDB and UniFi) and ConfigMap `unifi-db-init` (`init-mongo.js`). |

## Design Decisions

- **Node Co-Location**: Pinned strictly to `uk-home` zone (`topology.kubernetes.io/zone: uk-home` on `hades-01`).
- **Dedicated Subnet LoadBalancer**: MetalLB assigns IP `192.168.12.10` from the `192.168.12.0/24` pool for L2 device inform (8080) and STUN (3478/UDP).
- **RAM Constraints**: Total stack limit capped at **1.0 GiB** (MongoDB limit `256Mi` with `wiredTigerCacheSizeGB=0.15`, UniFi limit `768Mi` with `MEM_LIMIT=512M`).
- **Traefik Ingress**: Route `unifi.vmd1.homelab` on `websecure` (port 443) using `ServersTransport` with `insecureSkipVerify: true` to backend port `8443`.
