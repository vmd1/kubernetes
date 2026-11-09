#!/usr/bin/env bash
# Provision this server with the homelab tunnel-agent. Debian / Ubuntu, amd64 or arm64. Run as root (or with sudo).
#
# Served by the coordination server at /setup/<key> (the controller renders this template for a valid enrollment token):
#
#   curl -fsSL https://coordination.vmd1.homelab/setup/<key> | sudo sh
#
# It carries that 3-use token (not the agent's credentials: it trades the token for them at coordination.<domain>/enroll) and the
# shared registry login, so treat it like a key. It deletes itself once everything worked.
#
# Override with environment variables: TS_HOSTNAME, ADMIN_USER, AGENT_DIR, SKIP_DOCKER=1.
set -euo pipefail

AGENT_DIR=${AGENT_DIR:-/opt/tunnel-agent}
TS_HOSTNAME=${TS_HOSTNAME:-@@TS_HOSTNAME@@}
ADMIN_USER=${ADMIN_USER:-@@ADMIN_USER@@}
ENROLL_NAME='@@ENROLL_NAME@@'
ENROLL_TOKEN='@@ENROLL_TOKEN@@'
ENROLL_URLS='@@ENROLL_URLS@@'            # tried in turn: any one that answers will do
AGENT_IMAGE='@@AGENT_IMAGE@@'
REGISTRY_HOST='@@REGISTRY_HOST@@'        # fallback when the image cannot be pulled from ghcr.io
REGISTRY_IMAGE='@@REGISTRY_IMAGE@@'
REGISTRY_USER='@@REGISTRY_USER@@'
REGISTRY_PASSWORD='@@REGISTRY_PASSWORD@@'

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# ---- 0. checks ---------------------------------------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || die "run as root (sudo is not installed)"
  exec sudo -E bash "$0" "$@"
fi
[ -r /etc/os-release ] || die "no /etc/os-release: this script supports Debian and Ubuntu only"
. /etc/os-release
case " ${ID:-} ${ID_LIKE:-} " in
  *" debian "*|*" ubuntu "*) ;;
  *) die "unsupported OS '${PRETTY_NAME:-unknown}': Debian or Ubuntu (or a derivative) is required" ;;
esac
case "$(dpkg --print-architecture)" in
  amd64|arm64) ;;
  *) die "unsupported architecture $(dpkg --print-architecture): the agent image exists for amd64 and arm64" ;;
esac
command -v systemctl >/dev/null 2>&1 || warn "systemd not found: Docker will be installed but may not start on boot"
export DEBIAN_FRONTEND=noninteractive

# ---- 1. prerequisites --------------------------------------------------------------------------------------------
log "installing prerequisites"
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg iproute2 sudo >/dev/null

# ---- 1b. admin user ----------------------------------------------------------------------------------------------
# Key-only login (no password is set), so sudo is passwordless. Re-running adds nothing twice.
log "provisioning ssh users"
if ! id "$ADMIN_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$ADMIN_USER"
  passwd -l "$ADMIN_USER" >/dev/null
fi
usermod -aG sudo "$ADMIN_USER"
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$ADMIN_USER" > "/etc/sudoers.d/90-$ADMIN_USER"
chmod 0440 "/etc/sudoers.d/90-$ADMIN_USER"
visudo -cf "/etc/sudoers.d/90-$ADMIN_USER" >/dev/null || { rm -f "/etc/sudoers.d/90-$ADMIN_USER"; die "sudoers entry invalid"; }
ssh_dir=$(getent passwd "$ADMIN_USER" | cut -d: -f6)/.ssh
install -d -m 0700 -o "$ADMIN_USER" -g "$ADMIN_USER" "$ssh_dir"
touch "$ssh_dir/authorized_keys"
key='@@SSH_PUBKEY@@'
grep -qxF "$key" "$ssh_dir/authorized_keys" || printf '%s\n' "$key" >> "$ssh_dir/authorized_keys"
chown "$ADMIN_USER:$ADMIN_USER" "$ssh_dir/authorized_keys"
chmod 0600 "$ssh_dir/authorized_keys"

# ---- 2. credentials: trade the enrollment token for this agent's environment -------------------------------------
# The coordination server counts the token's uses (3) and refuses it afterwards. A re-run after a success finds agent.env
# and does not spend another use.
log "provisioning agent credentials"
install -d -m 0700 "$AGENT_DIR"
if [ ! -s "$AGENT_DIR/agent.env" ]; then
  tmp=$(mktemp "$AGENT_DIR/.enroll.XXXXXX")
  trap 'rm -f "$tmp"' EXIT
  enrolled=0
  for base in $ENROLL_URLS; do
    # the token goes in on stdin, not in the process list
    if printf '{"name":"%s","token":"%s"}' "$ENROLL_NAME" "$ENROLL_TOKEN" |
       curl -fsS --max-time 30 -H 'Content-Type: application/json' --data-binary @- "$base/enroll" -o "$tmp" 2>/dev/null &&
       grep -q '^CANARY=' "$tmp"; then
      enrolled=1; break
    fi
  done
  [ "$enrolled" = 1 ] || die "could not enrol with any coordination server (token used up or expired, or none reachable)"
  printf 'TS_HOSTNAME=%s\n' "$TS_HOSTNAME" >> "$tmp"
  chmod 0600 "$tmp"
  mv "$tmp" "$AGENT_DIR/agent.env"
  trap - EXIT
fi
chmod 0600 "$AGENT_DIR/agent.env"

# ---- 3. Docker Engine + compose plugin (official Docker apt repository) -------------------------------------------
if [ "${SKIP_DOCKER:-0}" != 1 ] && ! { command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; }; then
  log "installing Docker Engine and the compose plugin"
  # Debian and Ubuntu derivatives report their parent in ID_LIKE / UBUNTU_CODENAME.
  if [ "${ID}" = ubuntu ] || [[ " ${ID_LIKE:-} " == *" ubuntu "* ]]; then
    repo_os=ubuntu; codename=${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}
  else
    repo_os=debian; codename=${VERSION_CODENAME:-}
  fi
  [ -n "$codename" ] || die "cannot work out the release codename from /etc/os-release"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$repo_os/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$repo_os $codename stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
fi
command -v docker >/dev/null 2>&1 || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "the docker compose plugin is missing"
if command -v systemctl >/dev/null 2>&1; then systemctl enable --now docker >/dev/null 2>&1 || true; fi
for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
docker info >/dev/null 2>&1 || die "the Docker daemon is not running"

# ---- 4. kernel features the agent uses ---------------------------------------------------------------------------
# /dev/net/tun: a real tailscale0 (every host port reachable). wireguard: only for agents that have a lab bridge.
log "loading kernel modules (tun, wireguard)"
install -d /etc/modules-load.d
modprobe tun 2>/dev/null || true
[ -c /dev/net/tun ] || warn "/dev/net/tun is missing: the agent will fall back to userspace Tailscale (ssh only is published)"
if modprobe wireguard 2>/dev/null; then
  printf 'tun\nwireguard\n' > /etc/modules-load.d/tunnel-agent.conf
else
  printf 'tun\n' > /etc/modules-load.d/tunnel-agent.conf
  warn "the wireguard kernel module is not available: the direct-WireGuard pathways are skipped (the rest still work)"
fi

# ---- 5. the agent image: ghcr.io first, then the private registry -------------------------------------------------
pull_image() {
  if timeout 180 docker pull -q "$AGENT_IMAGE" >/dev/null 2>&1; then return 0; fi
  if [ -n "$REGISTRY_USER" ]; then
    warn "cannot pull $AGENT_IMAGE (ghcr.io blocked?): trying $REGISTRY_HOST"
    if printf '%s' "$REGISTRY_PASSWORD" | docker login "$REGISTRY_HOST" -u "$REGISTRY_USER" --password-stdin >/dev/null 2>&1; then
      if timeout 180 docker pull -q "$REGISTRY_IMAGE" >/dev/null 2>&1; then
        docker logout "$REGISTRY_HOST" >/dev/null 2>&1 || true
        AGENT_IMAGE=$REGISTRY_IMAGE
        return 0
      fi
      docker logout "$REGISTRY_HOST" >/dev/null 2>&1 || true
    fi
  fi
  # a previous run may already have left an image here
  if docker image inspect "$AGENT_IMAGE" >/dev/null 2>&1; then warn "using the image already on this server"; return 0; fi
  if docker image inspect "$REGISTRY_IMAGE" >/dev/null 2>&1; then AGENT_IMAGE=$REGISTRY_IMAGE; warn "using the image already on this server"; return 0; fi
  return 1
}
log "pulling the agent image"
pull_image || die "could not pull the agent image from ghcr.io or $REGISTRY_HOST"

cat > "$AGENT_DIR/compose.yml" <<__COMPOSE__
services:
  tunnel:
    image: $AGENT_IMAGE
    pull_policy: if_not_present
    container_name: tunnel-agent
    restart: unless-stopped
    network_mode: host            # "ssh to the server" means the server's own sshd
    cap_add: [NET_ADMIN]          # a real tailscale0, and the WireGuard pathways
    devices: ["/dev/net/tun:/dev/net/tun"]
    env_file: [agent.env]
    volumes: ["tunnel-state:/var/lib/tailscale"]   # keeps the tailnet identity across restarts
    logging:
      driver: json-file
      options: {max-size: "10m", max-file: "3"}
volumes:
  tunnel-state: {}
__COMPOSE__
chmod 0644 "$AGENT_DIR/compose.yml"

# ---- 6. start ----------------------------------------------------------------------------------------------------
log "starting the agent"
docker compose -f "$AGENT_DIR/compose.yml" up -d --remove-orphans >/dev/null 2>&1 \
  || docker compose -f "$AGENT_DIR/compose.yml" up -d --remove-orphans

# ---- 7b. the host CLI (`vmd1 agent path list|pick`, `down`, `up`): a scratch image on the private registry ---------------
install_vmd1() {
  [ -n "$REGISTRY_USER" ] || return 0
  printf '%s' "$REGISTRY_PASSWORD" | docker login "$REGISTRY_HOST" -u "$REGISTRY_USER" --password-stdin >/dev/null 2>&1 || return 0
  img="$REGISTRY_HOST/vmd1:latest"
  if timeout 120 docker pull -q "$img" >/dev/null 2>&1 && docker create --name vmd1-install "$img" /vmd1 >/dev/null 2>&1; then
    docker cp vmd1-install:/vmd1 /usr/local/bin/vmd1 >/dev/null 2>&1 && chmod 0755 /usr/local/bin/vmd1 || true
    docker rm vmd1-install >/dev/null 2>&1 || true
  fi
  docker logout "$REGISTRY_HOST" >/dev/null 2>&1 || true
}

# ---- 7. verify ---------------------------------------------------------------------------------------------------
log "waiting for a working pathway (up to 3 minutes)"
status=""
for _ in $(seq 1 90); do
  status=$(curl -fsS --max-time 3 http://XXX.XXX.XXX.XXX:9099/ 2>/dev/null || true)
  if [ -n "$status" ] && printf '%s' "$status" | grep -q '"active"[[:space:]]*:[[:space:]]*"[^"]'; then break; fi
  status=""; sleep 2
done
if [ -n "$status" ]; then
  # Parse the status: which pathways are active; for wss-tunnel, the gateway server and its SSH port.
  printf '%s' "$status" | docker exec -i tunnel-agent python3 -c '
import json, re, sys
from urllib.parse import urlparse
st = json.load(sys.stdin)
name = st["active"]
print("pathway: " + ", ".join(st.get("active_all") or [name]))
if name.startswith("wss-tunnel"):
    print("server:  " + (urlparse(st["pathways"][name].get("tunnel") or "").hostname or "?"))
    m = re.search(r":(\d+)", str((st.get("reachable_at") or {}).get("ssh", "")))
    print("port:    " + (m.group(1) if m else "?"))
'
  install_vmd1
  echo "Done"
  # The enrollment token and the registry login live only in this file: it has served its purpose.
  if [ -f "$0" ]; then shred -u "$0" 2>/dev/null || rm -f "$0"; fi
else
  warn "no pathway is active yet. The agent keeps retrying; look at:  docker logs -f tunnel-agent  (this file is kept so you can re-run it)"
fi
