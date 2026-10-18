#!/usr/bin/env bash
# Validate a VM through the Proxmox API (same checks as the web console).
#
# Credentials are read from the environment (or --env-file), never from args:
#   PROXMOX_HOST, PROXMOX_PORT, PROXMOX_USER, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET,
#   PROXMOX_VERIFY_SSL, PROXMOX_NODE
#
# Example:
#   ./validate-vm.sh --env-file ../../.env --vmid 901 --port 22
set -euo pipefail

VMID=""
PORT=""
TIMEOUT=300
ENV_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vmid) VMID="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 --vmid ID [--port N] [--timeout S] [--env-file FILE]"; exit 0 ;;
    *) echo "Unknown option $1" >&2; exit 1 ;;
  esac
done
[[ -n "$VMID" ]] || { echo "--vmid is required" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

if [[ -n "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^PROXMOX_[A-Z_]+=' "$ENV_FILE")
  set +a
fi
: "${PROXMOX_HOST:?set PROXMOX_HOST}" "${PROXMOX_TOKEN_SECRET:?set PROXMOX_TOKEN_SECRET}"
PORT_API="${PROXMOX_PORT:-8006}"
NODE="${PROXMOX_NODE:-pve}"
CURL_OPTS=(-fsS --max-time 15 -H "Authorization: PVEAPIToken=${PROXMOX_USER}!${PROXMOX_TOKEN_ID}=${PROXMOX_TOKEN_SECRET}")
[[ "${PROXMOX_VERIFY_SSL:-true}" == "false" ]] && CURL_OPTS+=(-k)
API="https://${PROXMOX_HOST}:${PORT_API}/api2/json/nodes/${NODE}/qemu/${VMID}"

api() { curl "${CURL_OPTS[@]}" "$API$1"; }
pass() { printf '  \033[32mPASS\033[0m %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; FAILED=1; }
FAILED=0

echo "Validating VMID $VMID on node $NODE"

status="$(api /status/current | jq -r .data.status || echo unknown)"
[[ "$status" == "running" ]] && pass "VM running" || fail "VM status is '$status'"

ip=""
deadline=$((SECONDS + TIMEOUT))
while [[ -z "$ip" && $SECONDS -lt $deadline ]]; do
  ip="$(api /agent/network-get-interfaces 2>/dev/null \
    | jq -r '[.data.result[] | select(.name != "lo") | ."ip-addresses"[]? | select(."ip-address-type"=="ipv4") | ."ip-address"][0] // empty' || true)"
  [[ -z "$ip" ]] && sleep 5
done
[[ -n "$ip" ]] && pass "Guest agent reports IP $ip" || fail "No IPv4 from qemu-guest-agent"

ci=0
while [[ $SECONDS -lt $deadline ]]; do
  if api "/agent/file-read?file=/var/lib/cloud/instance/boot-finished" >/dev/null 2>&1; then ci=1; break; fi
  sleep 5
done
[[ $ci -eq 1 ]] && pass "cloud-init completed" || fail "cloud-init not completed"

if [[ -n "$PORT" && -n "$ip" ]]; then
  if timeout 5 bash -c "</dev/tcp/$ip/$PORT" 2>/dev/null; then pass "tcp/$PORT open"; else fail "tcp/$PORT closed"; fi
fi

if [[ $FAILED -eq 0 ]]; then echo "RESULT: PASS"; else echo "RESULT: FAIL"; exit 1; fi
