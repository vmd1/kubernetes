# netpol-egress-public

`allow-egress-public`: egress to `0.0.0.0/0` and `::/0` except the private ranges, the tailnet ranges and link-local (this blocks the LAN, other nodes' tailnet addresses, the pod and Service networks and the cloud metadata endpoint). Ranges come from [../../vars](../../vars/README.md). Add it next to `netpol-baseline`; apps needing a specific internal peer add their own narrow policy.
