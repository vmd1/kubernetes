# netpol-db-client

`allow-egress-db`: egress to namespaces labelled `vmd1.homelab/db-server=true` on 5432 (Postgres), 6379 (Redis) and 26379 (Sentinel). The client namespace carries `vmd1.homelab/db-client=true`, which the database side matches for ingress (PR 3). The `db-server` label is not yet on `cnpg` and `redis` in `namespaces/namespaces.yaml`; add it before enrolling a client. No pilot app uses this component.
