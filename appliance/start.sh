#!/usr/bin/env bash
# Boot-time start of the console appliance (proxmox-ai-infra.service). Uses the images loaded into the VM.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../scripts/lib.sh
. "$(dirname "$0")/../scripts/lib.sh"
ensure_secret_files >/dev/null
# the first start after boot can be slow (image layers, health checks): retry instead of failing the unit
for attempt in 1 2 3 4 5; do
  dc up -d --remove-orphans && exit 0
  echo "start attempt $attempt failed, retrying in 20 s" >&2
  sleep 20
done
exit 1
