#!/usr/bin/env bash
# Runs once inside the build VM (appliance/build.sh): Docker, the console and its images, then cleanup.
# Progress goes to the serial console as "PAC-BUILD: ..."; the last line is PAC-BUILD-OK or PAC-BUILD-FAIL.
set -euo pipefail
DATA=$1                                   # mounted data disk: console.tar.gz, images.tar, VERSION
log() { echo "PAC-BUILD: $*" | tee /dev/ttyS0; }
trap 'echo "PAC-BUILD-FAIL line $LINENO" > /dev/ttyS0' ERR
export DEBIAN_FRONTEND=noninteractive
APP=/opt/proxmox-ai-infra
VERSION=$(cat "$DATA/VERSION")

log "packages"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -q
apt-get install -y -q --no-install-recommends docker-ce docker-ce-cli containerd.io docker-compose-plugin \
  qemu-guest-agent unattended-upgrades curl jq
systemctl enable docker qemu-guest-agent unattended-upgrades

log "images"
systemctl start docker
docker load -i "$DATA/images.tar"

log "console $VERSION"
mkdir -p "$APP"
tar -xzf "$DATA/console.tar.gz" --strip-components=1 -C "$APP"
cd "$APP"
touch .appliance
cp .env.example .env && chmod 600 .env
# shellcheck source=../scripts/lib.sh
. scripts/lib.sh
env_set VERSION "$VERSION"
env_set IMAGE_REGISTRY "$(cat "$DATA/REGISTRY")"
env_set COMPOSE_PROFILES ""
env_set PUBLIC_URL "http://localhost:8080"
ensure_secret_files >/dev/null
mkdir -p certs backups profiles && chmod 700 backups

log "services"
install -m 0755 appliance/files/pac-setup /usr/local/sbin/pac-setup
install -m 0644 appliance/files/proxmox-ai-infra.service /etc/systemd/system/proxmox-ai-infra.service
install -m 0644 appliance/files/motd /etc/motd
systemctl enable proxmox-ai-infra.service
# daily backup at 02:15, keeps 14
echo '15 2 * * * root cd /opt/proxmox-ai-infra && scripts/backup.sh >> backups/backup.log 2>&1' > /etc/cron.d/proxmox-ai-infra-backup
# security updates only, no automatic reboots
printf 'Unattended-Upgrade::Automatic-Reboot "false";\n' > /etc/apt/apt.conf.d/52proxmox-ai-infra

log "cleanup"
systemctl stop docker
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
rm -f /usr/local/share/ca-certificates/build-extra-ca.crt && update-ca-certificates --fresh >/dev/null  # build-only CA
rm -f /etc/ssh/ssh_host_*                   # regenerated on first boot
cloud-init clean --logs --seed --machine-id # the clone gets its own identity, user and keys from Proxmox
truncate -s 0 /etc/machine-id
journalctl --rotate >/dev/null 2>&1 || true; journalctl --vacuum-time=1s >/dev/null 2>&1 || true
fstrim -av >/dev/null 2>&1 || true
sync
echo PAC-BUILD-OK > /dev/ttyS0
