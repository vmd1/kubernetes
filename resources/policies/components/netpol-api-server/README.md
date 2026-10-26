# netpol-api-server

Opt-in `allow-egress-api-server`: egress to `API_SERVER_CIDR` on 6443. Pods reach the API through the `kubernetes` Service, which is DNATed to the endpoint before policy is evaluated, so the endpoint address (not the Service IP) is what is allowed. The value is the single control-plane node today; if the control plane moves, change it in [../../vars](../../vars/README.md). Not used by the pilot.
