#!/usr/bin/env bash
# Take desktop and hardware leftovers off a small Ubuntu node (the 1 GB ingress nodes).
#
#   slim-node.sh <ssh-target>            show what is enabled or running; changes nothing
#   slim-node.sh <ssh-target> --apply    stop, disable and mask the units (no package changes)
#   slim-node.sh <ssh-target> --purge    also purge the packages (simulated first; see below)
#
# Covers snapd, apport, ModemManager, udisks2 and fwupd. --apply is a few systemctl calls: it frees the memory and the
# boot work (snapd seeding, apport) without touching dpkg, which matters because apt/dpkg on a 954 MB node under memory
# pressure can itself tip it into a stall. Masking is reversible with `systemctl unmask`. --purge is for a stable node:
# it refuses while any snap is installed, while dpkg has interrupted packages, if the apt simulation fails or is empty,
# and if apt would also remove anything on a protected list (SSH, cloud-init, networking, Tailscale, the iSCSI/multipath
# stack the OCI boot disk uses, kernels, base meta-packages).
# <ssh-target> is whatever `ssh` accepts; no host is hard-coded. Needs passwordless sudo.
set -euo pipefail

target="${1:?usage: slim-node.sh <ssh-target> [--apply|--purge]}"
mode="${2:-dry-run}"

# shellcheck disable=SC2029,SC2016  # the script below is meant to be expanded on the node
ssh -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=8 "$target" "bash -s -- $mode" <<'REMOTE'
set -euo pipefail
mode="$1"
patterns="snapd* apport* ModemManager* udisks2* fwupd*"

units=""
for p in $patterns; do
  for u in $(systemctl list-unit-files --no-legend "$p" 2>/dev/null | awk '{print $1}' | grep -E '\.(service|socket|timer|path)$' || true); do units="$units $u"; done
done
echo "$(hostname): $(free -m | awk '/Mem:/{print "used="$3"MB avail="$7"MB"}')"
for u in $units; do printf "  %-34s enabled=%-9s active=%s\n" "$u" "$(systemctl is-enabled "$u" 2>/dev/null || true)" "$(systemctl is-active "$u" 2>/dev/null || true)"; done
[ "$mode" = "dry-run" ] && { echo "(dry run: nothing changed)"; exit 0; }

sudo systemctl disable --now $units >/dev/null 2>&1 || true
sudo systemctl mask $units >/dev/null 2>&1 || true
echo "masked:$units"
echo "after:  $(free -m | awk '/Mem:/{print "used="$3"MB avail="$7"MB"}')"
[ "$mode" = "--purge" ] || exit 0

want="snapd apport apport-symptoms python3-apport modemmanager udisks2 fwupd fwupd-signed"
protected='^(openssh-server|openssh-client|cloud-init|netplan\.io|systemd|systemd-sysv|tailscale|open-iscsi|multipath-tools|sudo|iptables|nftables|conntrack|ca-certificates|curl|jq|unattended-upgrades|ubuntu-minimal|ubuntu-standard|ubuntu-server|ubuntu-server-minimal|linux-.*)$'
installed=""
for p in $want; do dpkg-query -W -f='${db:Status-Abbrev}' "$p" 2>/dev/null | grep -q '^ii' && installed="$installed $p"; done
[ -n "$installed" ] || { echo "no packages to purge"; exit 0; }
if command -v snap >/dev/null 2>&1 && [ -n "$(snap list 2>/dev/null | awk 'NR>1')" ]; then echo "snaps installed; refusing to purge snapd" >&2; exit 1; fi
if [ -n "$(sudo dpkg --audit 2>&1)" ]; then echo "dpkg has interrupted packages (sudo dpkg --audit); fix them first" >&2; exit 1; fi
sim=$(apt-get -s purge --auto-remove $installed 2>&1) || { echo "apt simulation failed:"; echo "$sim" | tail -5; exit 1; }
removed=$(echo "$sim" | awk '/^Remv/{print $2}')
[ -n "$removed" ] || { echo "apt simulation removed nothing; refusing"; exit 1; }
echo "would purge: $(echo $removed | tr '\n' ' ')"
if bad=$(echo "$removed" | grep -E "$protected"); then echo "REFUSING: protected packages in the removal: $(echo $bad | tr '\n' ' ')" >&2; exit 1; fi
sudo DEBIAN_FRONTEND=noninteractive apt-get purge --auto-remove -y $installed
echo "purged; $(free -m | awk '/Mem:/{print "used="$3"MB avail="$7"MB"}')"
REMOTE
