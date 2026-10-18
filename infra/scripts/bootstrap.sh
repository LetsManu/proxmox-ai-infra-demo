#!/usr/bin/env bash
# One-time Proxmox bootstrap: creates everything the console itself is not
# allowed to create (least-privilege user, role, API token, ACLs, resource pool,
# image/snippet storage, SDN VLAN zone + vnets) with OpenTofu (infra/bootstrap).
#
# Run by an administrator from a workstation, NOT by the console. Admin
# credentials live only in this shell's environment:
#   export PROXMOX_VE_ENDPOINT=https://<proxmox-host>:8006/
#   export PROXMOX_VE_USERNAME=root@pam
#   read -rs PROXMOX_VE_PASSWORD && export PROXMOX_VE_PASSWORD
#   # self-signed lab certificate only:  export PROXMOX_VE_INSECURE=true
#
# Usage (from the repository root):
#   infra/scripts/bootstrap.sh [-var node_name=pve] [-var pve_major=9] [-var 'vm_storages=["local-lvm"]'] ...
#
# Result: secrets/proxmox_token_secret (chmod 600) and the .env values to set.
set -euo pipefail

TF="${IAC_BINARY:-tofu}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STACK="$ROOT/infra/bootstrap"

: "${PROXMOX_VE_ENDPOINT:?export PROXMOX_VE_ENDPOINT (admin session)}"
if [[ -z "${PROXMOX_VE_API_TOKEN:-}" && -z "${PROXMOX_VE_PASSWORD:-}" ]]; then
  echo "Set PROXMOX_VE_USERNAME/PROXMOX_VE_PASSWORD (root@pam) or an admin PROXMOX_VE_API_TOKEN." >&2
  exit 1
fi
[[ -t 0 ]] || { echo "Interactive terminal required: a person must confirm the bootstrap." >&2; exit 1; }
command -v "$TF" >/dev/null || { echo "$TF not found (install OpenTofu or set IAC_BINARY=terraform)" >&2; exit 1; }

PLAN="$(mktemp -d)/bootstrap.tfplan"
"$TF" -chdir="$STACK" init -input=false >/dev/null
"$TF" -chdir="$STACK" plan -input=false -out="$PLAN" "$@"

echo
read -r -p "Type BOOTSTRAP to create these resources on Proxmox: " answer
[[ "$answer" == "BOOTSTRAP" ]] || { echo "Aborted. Nothing was changed."; exit 1; }
"$TF" -chdir="$STACK" apply -input=false "$PLAN"

mkdir -p "$ROOT/secrets" && chmod 700 "$ROOT/secrets"
umask 077
"$TF" -chdir="$STACK" output -raw token_secret > "$ROOT/secrets/proxmox_token_secret"
chmod 600 "$ROOT/secrets/proxmox_token_secret" "$STACK/terraform.tfstate"

echo
echo "Token secret written to secrets/proxmox_token_secret (use docker-compose.secrets.yml)."
echo "The backend container runs as uid 10001 and must be able to read it:"
echo "  sudo chown 10001:10001 secrets/proxmox_token_secret"
echo "The bootstrap state ($STACK/terraform.tfstate) contains the secret too: keep it private, never commit it."
echo
echo "Set these in .env:"
"$TF" -chdir="$STACK" output -json env | python3 -c 'import json,sys; [print(f"{k}={v}") for k,v in json.load(sys.stdin).items()]'
echo "LIVE_MODE=true"
