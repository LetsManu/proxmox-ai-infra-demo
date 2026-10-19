#!/usr/bin/env bash
# Back up the console: database, OpenTofu state (TEST, PROD, platform), approved AI roles, SSH host keys.
#   scripts/backup.sh [directory]          default ./backups, keeps the newest $BACKUP_KEEP (14) archives
# Secrets are NOT in the archive: keep secrets/ and .env in your password manager or vault.
# Daily at 02:15:  15 2 * * *  cd /opt/proxmox-ai-infra && scripts/backup.sh >> backups/backup.log 2>&1
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "$0")/lib.sh"

dir=${1:-backups}
keep=${BACKUP_KEEP:-14}
mkdir -p "$dir" && chmod 700 "$dir"
file="$dir/console-$(date -u +%Y%m%d-%H%M%S).tar.gz"

dc ps --status running --services 2>/dev/null | grep -qx backend || die "The backend is not running (docker compose up -d)."
umask 077
if ! dc exec -T backend python -m app.cli backup - > "$file"; then
  rm -f "$file"
  die "Backup failed (see above). Running jobs? Retry later or: docker compose exec backend python -m app.cli backup - --force"
fi
dc exec -T backend python -m app.cli verify - < "$file" > /dev/null || { rm -f "$file"; die "The new archive does not verify."; }
say "Backup: $file ($(du -h "$file" | cut -f1))"

# keep the newest $keep archives
ls -1t "$dir"/console-*.tar.gz 2>/dev/null | tail -n +$((keep + 1)) | while read -r old; do rm -f "$old"; done
