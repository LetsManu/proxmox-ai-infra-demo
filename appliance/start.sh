#!/usr/bin/env bash
# Boot-time start of the console appliance (proxmox-ai-infra.service). Uses the images loaded into the VM.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=../scripts/lib.sh
. "$(dirname "$0")/../scripts/lib.sh"
ensure_secret_files >/dev/null
dc up -d --remove-orphans
