#!/usr/bin/env bash
# Upgrade the console to the release in this directory, or to a tag when this is a git checkout.
#   scripts/upgrade.sh             after extracting the new release over the old directory (.env, secrets/,
#                                  certs/, profiles/ and backups/ are kept)
#   scripts/upgrade.sh v2.1.0      git checkout: fetch and switch to that tag first
# Always backs up first. Roll back: set VERSION=<old> in .env and run scripts/restore.sh <pre-upgrade backup>.
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "$0")/lib.sh"

[ -f .env ] || die "No .env here. For a new installation run scripts/install.sh."
old=$(env_get VERSION); old=${old:-unknown}

if [ -n "${1:-}" ]; then
  [ -d .git ] || die "A version argument needs a git checkout. Otherwise extract the release here and run without it."
  git fetch --tags --quiet
  git -c advice.detachedHead=false checkout --quiet "$1"
fi
new=$(bundle_version)
say "Upgrade $old -> $new"

if dc ps --status running --services 2>/dev/null | grep -qx backend; then
  say "Backup before the upgrade"
  scripts/backup.sh
else
  warn "The console is not running; no pre-upgrade backup was made."
fi

# files and settings that newer releases expect
ensure_secret_files
mkdir -p certs profiles
missing=$(comm -23 <(sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p' .env.example | sort -u) \
                   <(sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p' .env | sort -u))
if [ -n "$missing" ]; then
  warn "New settings (defaults apply until you set them in .env, see .env.example and CHANGELOG.md):"
  printf '  %s\n' $missing >&2
fi
env_set VERSION "$new"

if [ "${UPGRADE_BUILD:-0}" = 1 ]; then dc build; else dc pull || die "Pull failed (docker login ghcr.io?). Or UPGRADE_BUILD=1 scripts/upgrade.sh"; fi
dc up -d
wait_healthy
say "Upgraded to $new. Release notes: CHANGELOG.md"
