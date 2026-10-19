# Shared helpers for install.sh, upgrade.sh, backup.sh and restore.sh. Sourced, not run.
# shellcheck shell=bash

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1

SECRET_FILES=(proxmox_token_secret anthropic_api_key ansible_ssh_key windows_admin_password proxmox_ssh_key
              oidc_client_secret ldap_bind_password)

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
die()  { printf '\033[31mError: %s\033[0m\n' "$*" >&2; exit 1; }

# docker compose with the secrets overlay when secrets/ exists
dc() {
  local files=(-f docker-compose.yml)
  [ -d secrets ] && files+=(-f docker-compose.secrets.yml)
  docker compose "${files[@]}" "$@"
}

# root-owned files for the backend (uid 10001) need sudo unless we are root
as_root() { if [ "$(id -u)" = 0 ]; then "$@"; else sudo "$@"; fi; }

# release archives carry VERSION (e.g. 2.1.0-rc.1 = image tag); a git checkout falls back to the code's version
bundle_version() {
  if [ -s VERSION ]; then tr -d '[:space:]' < VERSION; else sed -n 's/^__version__ = "\(.*\)"/\1/p' backend/app/__init__.py; fi
}

# set KEY=VALUE in .env (replace or append); the value is passed through the environment, so any character is safe
env_set() {
  KEY="$1" VALUE="$2" awk 'BEGIN { k = ENVIRON["KEY"]; v = ENVIRON["VALUE"]; done = 0 }
    $0 ~ "^" k "=" { print k "=" v; done = 1; next } { print }
    END { if (!done) print k "=" v }' .env > .env.tmp && cat .env.tmp > .env && rm -f .env.tmp  # keeps mode 600
}

env_get() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -1; }

ensure_secret_files() {
  [ -d secrets ] || { mkdir -p secrets && chmod 700 secrets; }
  local f
  for f in "${SECRET_FILES[@]}"; do
    [ -e "secrets/$f" ] || { : > "secrets/$f"; say "  created empty secrets/$f"; }
  done
  as_root chmod 600 secrets/*
  as_root chown 10001:10001 secrets/*
}

wait_healthy() {
  local port url
  port=$(env_get FRONTEND_PORT); port=${port:-8080}
  url="http://127.0.0.1:${port}"
  for _ in $(seq 1 60); do
    if curl -fsS "$url/healthz" >/dev/null 2>&1 && curl -fsS "$url/api/health" >/dev/null 2>&1; then
      say "Console is up: $url (or your PUBLIC_URL)"
      return 0
    fi
    sleep 3
  done
  dc ps
  die "The console did not become healthy within 3 minutes. Check: docker compose logs backend"
}
