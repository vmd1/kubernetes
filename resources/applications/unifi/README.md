# UniFi Network Application

UniFi Network Application manages UniFi networking hardware (Access Points, Switches, Security Gateways).

## Breakdown of Files

| File | Description |
| :--- | :--- |
| [manifest.yaml](manifest.yaml) | Defines `unifi` namespace, MongoDB database Deployment (`mongo:7.0`), UniFi Network Application Deployment (`lscr.io/linuxserver/unifi-network-application`), Services, Kube-VIP LoadBalancer (`192.168.12.10`), and Traefik `IngressRoute` (`unifi.vmd1.homelab`). |
| [secrets.sops.yaml](secrets.sops.yaml) | SOPS-encrypted Secret `unifi-db-secrets` (credentials for MongoDB and UniFi) and ConfigMap `unifi-db-init` (`init-mongo.js`). |

## Design Decisions

- **Node Co-Location**: Pinned strictly to `uk-home` zone with `kubernetes.io/arch: amd64` (`hades-02`) due to MongoDB 7.0 requirements.
- **Dedicated Subnet LoadBalancer**: Kube-VIP assigns IP `192.168.12.10` pinned to `hades-02` (`kube-vip.io/vipHost: hades-02`) for device inform (8080) and STUN (3478/UDP).
- **RAM Constraints**: MongoDB limit `512Mi` with `wiredTigerCacheSizeGB=0.25` (minimum engine requirement), UniFi limit `768Mi` with `MEM_LIMIT=512M`.
- **Traefik Ingress**: Route `unifi.vmd1.homelab` on `websecure` (port 443) using `ServersTransport` with `insecureSkipVerify: true` to backend port `8443`.
