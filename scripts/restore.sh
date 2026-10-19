#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh. Replaces the database and OpenTofu state.
#   scripts/restore.sh backups/console-20261019-021500.tar.gz
# Proxmox is not touched. Afterwards, plan once per environment: the plan shows any difference between the
# restored state and what really runs on Proxmox.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "$0")/lib.sh"

file=${1:-}
[ -f "$file" ] || die "Usage: scripts/restore.sh <backup.tar.gz>"

say "Checking $file"
dc run --rm -T --no-deps backend python -m app.cli verify - < "$file"

if [ "${RESTORE_YES:-}" != 1 ]; then
  printf 'This replaces the current database and OpenTofu state. Type RESTORE to continue: '
  read -r answer
  [ "$answer" = RESTORE ] || die "Cancelled, nothing changed."
fi

say "Stopping the console"
dc stop frontend backend
dc run --rm -T --no-deps backend python -m app.cli restore - < "$file"
dc up -d
wait_healthy
say "Restored. Next: Platform -> Check what is missing, and plan each machine once to compare with Proxmox."
