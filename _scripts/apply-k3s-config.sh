#!/usr/bin/env bash
# Show (default) or install the k3s control-plane config kept in resources/k3s-config/.
#
#   apply-k3s-config.sh <ssh-target>            diff the files on the host against Git
#   apply-k3s-config.sh <ssh-target> --apply    copy them to the host (does NOT restart k3s)
#
# <ssh-target> is whatever `ssh` accepts for the control-plane node (user@host or an ssh_config alias); it is
# never hard-coded here. Needs passwordless sudo on the host. Restart k3s yourself, in a window, after taking an
# etcd snapshot: see resources/k3s-config/README.md.
set -euo pipefail

target="${1:?usage: apply-k3s-config.sh <ssh-target> [--apply]}"
mode="${2:-diff}"
src="$(cd "$(dirname "$0")/../resources/k3s-config" && pwd)"

files=(
  "config.yaml.d/10-hardening.yaml:/etc/rancher/k3s/config.yaml.d/10-hardening.yaml"
  "audit-policy.yaml:/etc/rancher/k3s/audit-policy.yaml"
)

rc=0
for pair in "${files[@]}"; do
  local_file="$src/${pair%%:*}"
  remote_file="${pair#*:}"
  case "$mode" in
    diff)
      echo "== $remote_file"
      if ! ssh "$target" "sudo cat '$remote_file'" 2>/dev/null | diff -u - "$local_file"; then rc=1; fi
      ;;
    --apply)
      tmp="/tmp/$(basename "$remote_file").$$"
      scp -q "$local_file" "$target:$tmp"
      ssh "$target" "sudo install -D -m 0644 '$tmp' '$remote_file' && rm -f '$tmp'"
      echo "installed $remote_file"
      ;;
    *) echo "unknown mode: $mode" >&2; exit 2 ;;
  esac
done
[ "$mode" = "--apply" ] && echo "Files installed. k3s was NOT restarted; see resources/k3s-config/README.md."
exit $rc
