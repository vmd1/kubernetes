# k3s config (`resources/k3s-config/`)

Canonical content of the k3s control-plane settings that Flux cannot apply because they live on the host. Audit logging was installed on hades-01 on 2026-10-26; secrets encryption is not installed yet. **Not reconciled by Flux**: [../../_scripts/apply-k3s-config.sh](../../_scripts/README.md) diffs and installs them over SSH.

## Files

| File | Installed as | Description |
| :--- | :--- | :--- |
| [config.yaml.d/10-audit-logging.yaml](config.yaml.d/10-audit-logging.yaml) | `/etc/rancher/k3s/config.yaml.d/10-audit-logging.yaml` | The API audit-log flags (appended to the existing `kube-apiserver-arg`). |
| [config.yaml.d/20-secrets-encryption.yaml](config.yaml.d/20-secrets-encryption.yaml) | `/etc/rancher/k3s/config.yaml.d/20-secrets-encryption.yaml` | `secrets-encryption: true`. Not installed unless `--with-encryption` is passed. |
| [audit-policy.yaml](audit-policy.yaml) | `/etc/rancher/k3s/audit-policy.yaml` | What the API server logs: metadata only for Secrets/ConfigMaps, full request and response for RBAC and admission changes, no routine node reads or events. |

## Applying (by hand, in a window)

1. Take an etcd snapshot (`k3s etcd-snapshot save`).
2. `_scripts/apply-k3s-config.sh <ssh-target>` to review the diff, then with `--apply`. It never restarts k3s.
3. Restart the control plane (`systemctl restart k3s`). The control plane is a single node, so the API is down for the restart.
4. Re-encrypt existing Secrets: `k3s secrets-encrypt status`, then `k3s secrets-encrypt reencrypt` once it reports the new key is active.
5. Update [../../../docs/host-config.md](../../../docs/host-config.md) with the date applied.

## Design Decisions

- **Drop-in, not an edit of `config.yaml`**: the `+` suffix appends to the arrays already there, so the file holding the node IP, flannel interface and etcd snapshot settings is left alone.
- **No secrets here**: the etcd snapshot S3 key in `/etc/rancher/k3s/config.yaml` is plaintext on the host and should be moved out and rotated; that is a host change and is not part of this PR.
- **Not yet shipped to Loki**: `monitoring-agents` runs on the ingress nodes only, so the audit log on the control plane is read on the host until a collector is added.

## Related

- [../policies/admission/README.md](../policies/admission/README.md) — policy violations appear in this audit log.
- [../../../docs/host-config.md](../../../docs/host-config.md) — host config outside GitOps.
