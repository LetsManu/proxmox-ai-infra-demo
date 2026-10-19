#!/usr/bin/env bash
# Install the console from a release (OVERVIEW.md, "Install in five minutes").
#   tar xzf proxmox-ai-infra-<version>.tar.gz && cd proxmox-ai-infra-<version> && scripts/install.sh
# Asks for the few values every installation needs, creates .env and secrets/ with the right permissions,
# pulls the release images and starts the console. Re-running it keeps existing .env values and secrets.
#   --build            build the images from this checkout instead of pulling them
#   --non-interactive  take answers from the environment (PROXMOX_HOST, PROXMOX_TOKEN_SECRET, AUTH_MODE, ...)
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "$0")/lib.sh"

BUILD=0; ASK=1
for a in "$@"; do
  case "$a" in
    --build) BUILD=1 ;;
    --non-interactive) ASK=0 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) die "Unknown option $a" ;;
  esac
done

# ---- prerequisites -------------------------------------------------------------
command -v docker >/dev/null || die "Docker is not installed (https://docs.docker.com/engine/install/)."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is missing (package docker-compose-plugin)."
docker info >/dev/null 2>&1 || die "Cannot talk to Docker. Is it running, and is $(id -un) in the docker group?"
command -v curl >/dev/null || die "curl is missing."
VERSION=$(bundle_version)
[ -n "$VERSION" ] || die "Run this from the extracted release (backend/app/__init__.py not found)."
say "Proxmox AI Infra Console $VERSION"

# ---- questions -------------------------------------------------------------------
ask() {  # ask VAR "question" default [secret]
  local var=$1 q=$2 def=$3 secret=${4:-} cur ans
  cur=$(env_get "$var"); [ -n "$cur" ] && def=$cur
  if [ "$ASK" = 0 ]; then ans=${!var:-$def}
  elif [ -n "$secret" ]; then read -r -s -p "$q: " ans; echo >&2; ans=${ans:-$def}
  else read -r -p "$q [${def}]: " ans; ans=${ans:-$def}; fi
  printf '%s' "$ans"
}

new_env=0
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; new_env=1; fi
ensure_secret_files

if [ "$new_env" = 1 ] || [ "$ASK" = 1 ]; then
  say "Connection to Proxmox (docs/api-token-setup.md creates the API token)"
  live=$(ask LIVE_MODE "Connect to a real Proxmox? (true = live, false = demo mode)" false)
  env_set LIVE_MODE "$live"
  if [ "$live" = true ]; then
    env_set PROXMOX_HOST "$(ask PROXMOX_HOST "Proxmox host name" pve.example.internal)"
    env_set PROXMOX_NODE "$(ask PROXMOX_NODE "Proxmox node" pve)"
    env_set PROXMOX_USER "$(ask PROXMOX_USER "API user" automation@pve)"
    env_set PROXMOX_TOKEN_ID "$(ask PROXMOX_TOKEN_ID "API token ID (name only)" infra-demo)"
    if [ ! -s secrets/proxmox_token_secret ]; then
      tok=$(ask PROXMOX_TOKEN_SECRET "API token secret (input hidden)" "" secret)
      [ -n "$tok" ] && printf '%s' "$tok" | as_root tee secrets/proxmox_token_secret >/dev/null
    fi
  fi

  say "Sign-in (docs/authentication.md)"
  env_set PUBLIC_URL "$(ask PUBLIC_URL "Address people open in the browser" "http://localhost:8080")"
  mode=$(ask AUTH_MODE "Sign-in: oidc (Authentik, Entra ID, AD FS), ldap (Active Directory, OpenLDAP) or none" none)
  env_set AUTH_MODE "$mode"
  case "$mode" in
    oidc)
      env_set AUTH_PROVIDER_NAME "$(ask AUTH_PROVIDER_NAME "Name on the sign-in button" Authentik)"
      env_set OIDC_ISSUER "$(ask OIDC_ISSUER "Issuer URL" "")"
      env_set OIDC_CLIENT_ID "$(ask OIDC_CLIENT_ID "Client ID" proxmox-console)"
      if [ ! -s secrets/oidc_client_secret ]; then
        sec=$(ask OIDC_CLIENT_SECRET "Client secret (input hidden)" "" secret)
        [ -n "$sec" ] && printf '%s' "$sec" | as_root tee secrets/oidc_client_secret >/dev/null
      fi ;;
    ldap)
      env_set AUTH_PROVIDER_NAME "$(ask AUTH_PROVIDER_NAME "Name shown on the sign-in page" "Active Directory")"
      env_set LDAP_URL "$(ask LDAP_URL "Directory URL (ldaps://dc01.example.internal:636)" "")"
      env_set LDAP_BASE_DN "$(ask LDAP_BASE_DN "Base DN" "")"
      env_set LDAP_BIND_DN "$(ask LDAP_BIND_DN "Service account DN" "")"
      if [ ! -s secrets/ldap_bind_password ]; then
        pw=$(ask LDAP_BIND_PASSWORD "Service account password (input hidden)" "" secret)
        [ -n "$pw" ] && printf '%s' "$pw" | as_root tee secrets/ldap_bind_password >/dev/null
      fi
      warn "Check LDAP_USER_FILTER and LDAP_CA_FILE in .env for your directory (docs/authentication.md)." ;;
    none) warn "No sign-in: keep FRONTEND_BIND=127.0.0.1 and use the console only on this machine." ;;
    *) die "AUTH_MODE must be oidc, ldap or none." ;;
  esac
  if [ "$mode" != none ]; then
    env_set AUTH_VIEWER_GROUPS "$(ask AUTH_VIEWER_GROUPS "Viewer group(s), ;-separated" px-viewers)"
    env_set AUTH_OPERATOR_GROUPS "$(ask AUTH_OPERATOR_GROUPS "Operator group(s)" px-operators)"
    env_set AUTH_APPROVER_GROUPS "$(ask AUTH_APPROVER_GROUPS "Approver group(s)" px-approvers)"
    case "$(env_get PUBLIC_URL)" in
      https://*) env_set AUTH_COOKIE_SECURE true ;;
      *) warn "PUBLIC_URL is not HTTPS: session cookies are set without Secure (lab only)."; env_set AUTH_COOKIE_SECURE false ;;
    esac
  fi
fi
# a plain (non-secret) password in .env would be overridden by the secrets overlay: keep .env free of them
for k in PROXMOX_TOKEN_SECRET OIDC_CLIENT_SECRET LDAP_BIND_PASSWORD ANTHROPIC_API_KEY WINDOWS_ADMIN_PASSWORD; do
  env_set "$k" ""
done
env_set VERSION "$VERSION"
mkdir -p certs profiles backups && chmod 700 backups

# ---- images and start --------------------------------------------------------------
if [ "$BUILD" = 1 ]; then
  say "Building images $VERSION from this checkout"
  dc build
else
  say "Pulling images $VERSION"
  if ! dc pull; then
    die "Could not pull the images. For a private registry: docker login ghcr.io (token with read:packages).
       Or build them here: scripts/install.sh --build"
  fi
fi
dc up -d
wait_healthy
cat <<EOF

Next steps
  - Open the console and go to Platform -> Check what is missing (OVERVIEW.md, step 10).
  - Secrets for Linux/Windows configuration: secrets/ansible_ssh_key, secrets/windows_admin_password (docs/configuration.md).
  - Daily backup: add to crontab  15 2 * * *  cd $ROOT && scripts/backup.sh >> backups/backup.log 2>&1
EOF
