#!/usr/bin/env bash
# Command-line production promotion (the web console does the same thing).
#
# Plans PRODUCTION with its own state file, shows the plan, and applies the
# saved plan ONLY after a human types PROMOTE at an interactive terminal.
# There is deliberately no --yes / auto-approve flag.
#
# Example (run from infra/):
#   export PROXMOX_VE_ENDPOINT=https://pve.example.internal:8006/
#   export PROXMOX_VE_API_TOKEN='automation@pve!infra-demo=<secret>'
#   ./scripts/promote.sh --vars /workspace/prod/generated.tfvars.json
set -euo pipefail

VARS=""
STATE="${STATE_PATH:-/workspace/state/prod/terraform.tfstate}"
TF="${IAC_BINARY:-tofu}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vars) VARS="$2"; shift 2 ;;
    --state) STATE="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 --vars generated.tfvars.json [--state path]"; exit 0 ;;
    *) echo "Unknown option $1" >&2; exit 1 ;;
  esac
done

cd "$(dirname "$0")/.."
[[ -f "$VARS" ]] || { echo "--vars file with the prod 'vms' map is required" >&2; exit 1; }
[[ -t 0 ]] || { echo "Refusing to run without an interactive terminal: production needs a human." >&2; exit 1; }
: "${PROXMOX_VE_ENDPOINT:?export PROXMOX_VE_ENDPOINT}" "${PROXMOX_VE_API_TOKEN:?export PROXMOX_VE_API_TOKEN}"

export TF_DATA_DIR="${TF_DATA_DIR:-$(dirname "$STATE")/../../prod/.terraform}"
PLAN="$(mktemp -d)/prod.tfplan"

"$TF" init -input=false -reconfigure -backend-config="path=$STATE" >/dev/null
"$TF" plan -input=false -var-file=environments/prod.tfvars -var-file="$VARS" -out="$PLAN"

if "$TF" show -json "$PLAN" | grep -q '"delete"'; then
  printf '\n\033[1;31mWARNING: this plan DESTROYS at least one production resource.\033[0m\n'
fi

echo
read -r -p "I understand this will change production. Type PROMOTE to apply: " answer
if [[ "$answer" != "PROMOTE" ]]; then
  echo "Aborted. Nothing was changed."
  exit 1
fi
"$TF" apply -input=false "$PLAN"
echo "Production promotion applied by ${USER:-unknown} at $(date -u +%FT%TZ)"
