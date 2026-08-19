#!/usr/bin/env bash
# =============================================================================
# Helper script to decrypt and apply (or dry-run) SOPS secrets to Kubernetes
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Ensure age key is configured
if [[ -z "${SOPS_AGE_KEY_FILE:-}" ]]; then
  if [[ -f "${HOME}/.config/sops/age/keys.txt" ]]; then
    export SOPS_AGE_KEY_FILE="${HOME}/.config/sops/age/keys.txt"
  else
    echo "ERROR: SOPS_AGE_KEY_FILE not set and ~/.config/sops/age/keys.txt not found!" >&2
    exit 1
  fi
fi

# Ensure binaries are available
export PATH="${HOME}/.local/bin:${PATH}"

DRY_RUN=""
ACTION="apply"

usage() {
  echo "Usage: $0 [--dry-run|--diff|--apply]"
  echo "  --dry-run   Perform client-side dry-run validation without modifying cluster"
  echo "  --diff      Show diff between SOPS secrets and live cluster secrets"
  echo "  --apply     Decrypt and apply secrets to the Kubernetes cluster (default)"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      ACTION="dry-run"
      shift
      ;;
    --diff)
      ACTION="diff"
      shift
      ;;
    --apply)
      ACTION="apply"
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      ;;
  esac
done

cd "${REPO_ROOT}"

SECRET_FILES=$(find resources -name '*.sops.yaml' | sort)

echo "==> Running $ACTION on $(echo "$SECRET_FILES" | wc -l) SOPS secret files..."

for file in $SECRET_FILES; do
  echo "--> Processing: $file"
  case "$ACTION" in
    dry-run)
      sops --decrypt "$file" | kubectl apply --dry-run=client -f -
      ;;
    diff)
      sops --decrypt "$file" | kubectl diff -f - || true
      ;;
    apply)
      sops --decrypt "$file" | kubectl apply -f -
      ;;
  esac
done

echo "==> Done!"
