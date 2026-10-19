#!/usr/bin/env bash
# Build the console appliance disk for Proxmox (docs/appliance.md).
#   appliance/build.sh <version> <output.qcow2>
# Boots the official Debian 12 cloud image once in QEMU; cloud-init runs appliance/provision.sh, which installs
# Docker, loads the console images and sets up the services, then the VM powers off. Needs: qemu-system-x86_64,
# qemu-img, xorriso, curl, docker (to export the images), and internet access for the VM.
# Environment:
#   IMAGE_REGISTRY  images to export (default ghcr.io/letsmanu/proxmox-ai-infra-demo); they must exist locally
#   CADDY_IMAGE     default caddy:2.10.2-alpine
#   EXTRA_CA_FILE   CA bundle the build VM must trust (TLS-intercepting proxy); removed again before the image is sealed
#   QEMU_EXTRA      extra QEMU arguments for debugging, e.g. "-vnc 127.0.0.1:1"
set -euo pipefail
VERSION=${1:?version}; OUT=${2:?output.qcow2}
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(dirname "$HERE")
REGISTRY=${IMAGE_REGISTRY:-ghcr.io/letsmanu/proxmox-ai-infra-demo}
CADDY=${CADDY_IMAGE:-caddy:2.10.2-alpine}
BASE_URL=https://cloud.debian.org/images/cloud/bookworm/latest
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
log() { printf '\033[1m%s\033[0m\n' "$*"; }

log "Debian 12 cloud image"
curl -fsSL -o "$WORK/base.qcow2" "$BASE_URL/debian-12-genericcloud-amd64.qcow2"
curl -fsSL -o "$WORK/SHA512SUMS" "$BASE_URL/SHA512SUMS"
(cd "$WORK" && grep ' debian-12-genericcloud-amd64.qcow2$' SHA512SUMS | sed 's/debian-12-genericcloud-amd64.qcow2$/base.qcow2/' | sha512sum -c -)
qemu-img create -q -f qcow2 -F qcow2 -b "$WORK/base.qcow2" "$WORK/disk.qcow2" 16G

log "Console $VERSION and images"
mkdir -p "$WORK/data" "$WORK/v"
printf '%s\n' "$VERSION" > "$WORK/v/VERSION"  # like the release archive: install.sh and upgrade.sh read it
(cd "$ROOT" && git archive --format=tar.gz --prefix=console/ --add-file="$WORK/v/VERSION" -o "$WORK/data/console.tar.gz" HEAD)
docker save -o "$WORK/data/images.tar" "$REGISTRY/backend:$VERSION" "$REGISTRY/frontend:$VERSION" "$CADDY"
printf '%s\n' "$VERSION" > "$WORK/data/VERSION"
printf '%s\n' "$REGISTRY" > "$WORK/data/REGISTRY"
cp "$HERE/provision.sh" "$WORK/data/provision.sh"
xorriso -as mkisofs -quiet -iso-level 3 -J -R -V PACDATA -o "$WORK/data.iso" "$WORK/data"

log "cloud-init seed"
mkdir -p "$WORK/seed"
printf 'instance-id: pac-build\nlocal-hostname: proxmox-ai-infra\n' > "$WORK/seed/meta-data"
{
  echo "#cloud-config"
  echo "growpart: {mode: auto, devices: ['/']}"
  echo "bootcmd: [[sh, -c, 'echo PAC-BUILD: cloud-init running > /dev/ttyS0']]"
  if [ -n "${EXTRA_CA_FILE:-}" ]; then
    echo "write_files:"
    echo "  - path: /usr/local/share/ca-certificates/build-extra-ca.crt"
    echo "    content: |"
    sed 's/^/      /' "$EXTRA_CA_FILE"
  fi
  echo "runcmd:"
  [ -n "${EXTRA_CA_FILE:-}" ] && echo "  - [update-ca-certificates]"
  echo "  - [mkdir, -p, /mnt/pacdata]"
  echo "  - [mount, -o, ro, /dev/disk/by-label/PACDATA, /mnt/pacdata]"
  echo "  - [bash, -c, 'bash /mnt/pacdata/provision.sh /mnt/pacdata > /var/log/pac-build.log 2>&1 || echo PAC-BUILD-FAIL > /dev/ttyS0']"
  echo "  - [umount, /mnt/pacdata]"
  echo "  - [poweroff]"
} > "$WORK/seed/user-data"
xorriso -as mkisofs -quiet -J -R -V cidata -o "$WORK/seed.iso" "$WORK/seed"

log "Provisioning (KVM if available, else emulation: much slower)"
accel=tcg; [ -w /dev/kvm ] && accel=kvm
timeout 7200 qemu-system-x86_64 -machine q35 -accel "$accel" -cpu max -smp 4 -m 4096 \
  -drive if=virtio,file="$WORK/disk.qcow2",format=qcow2 \
  -drive file="$WORK/seed.iso",media=cdrom,readonly=on \
  -drive file="$WORK/data.iso",media=cdrom,readonly=on \
  -netdev user,id=n0 -device virtio-net-pci,netdev=n0 \
  -serial file:"$WORK/serial.log" -monitor none -display none ${QEMU_EXTRA:-}
grep -a "PAC-BUILD" "$WORK/serial.log" | tr -d '\r' || true
grep -aq "PAC-BUILD-OK" "$WORK/serial.log" || { echo "Provisioning failed (see above)"; exit 1; }

log "Compress"
qemu-img convert -O qcow2 -c -o compression_type=zstd "$WORK/disk.qcow2" "$OUT"
qemu-img info "$OUT" | grep -E "virtual size|disk size"
