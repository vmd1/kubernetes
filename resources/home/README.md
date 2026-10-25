# Home (`resources/home/`)

Home automation and the home network. Applied by the `home` Flux Kustomization ([../../clusters/vmd1/home.yaml](../../clusters/vmd1/home.yaml)), which depends only on `operators`.

## Contents

| Folder | Description |
| :--- | :--- |
| [home-assistant/](home-assistant/README.md) | Home automation core on the local subnet with a filebrowser sidecar. |
| [mqtt/](mqtt/README.md) | Eclipse Mosquitto broker for IoT/Home Assistant messaging. |
| [unifi/](unifi/README.md) | UniFi Network Application for managing UniFi networking hardware. |

## Related

- [../README.md](../README.md): how the groups fit together.
- [../../../cluster-info.md](../../../cluster-info.md): cluster inventory.
