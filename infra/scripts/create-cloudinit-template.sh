#!/usr/bin/env bash
# Build a Proxmox cloud-init template from an official OS cloud image.
#
# Run ON THE PROXMOX NODE as root (uses `qm`). Image URLs are not hard-coded:
# they come from --image-url or from UBUNTU_2404_IMAGE_URL / DEBIAN_12_IMAGE_URL
# (e.g. `--env-file ./.env`).
#
# Example:
#   ./create-cloudinit-template.sh --os ubuntu-24-04 --vmid 9000 \
#       --storage local-lvm --bridge vmbr0 --ssh-key ~/.ssh/id_ed25519.pub \
#       --env-file ./.env --install-agent
set -euo pipefail

OS=""
VMID=""
NAME=""
STORAGE="local-lvm"
BRIDGE="vmbr0"
VLAN=""
CI_USER="ops"
SSH_KEY_FILE=""
IMAGE_URL=""
ENV_FILE=""
IP_CONFIG="ip=dhcp"
INSTALL_AGENT=0
WORKDIR="/var/tmp/cloud-images"

usage() {
  cat <<EOF
Usage: $0 --os <ubuntu-24-04|debian-12> --vmid <id> [options]

Options:
  --name NAME            Template name (default: tmpl-<os>)
  --storage POOL         Storage pool for the disk + cloud-init drive (default: $STORAGE)
  --bridge BRIDGE        Network bridge (default: $BRIDGE)
  --vlan TAG             VLAN tag for the template NIC (optional)
  --ci-user USER         Cloud-init default user (default: $CI_USER)
  --ssh-key FILE         SSH *public* key file added to the template
  --image-url URL        Cloud image URL (default: from env file / environment)
  --env-file FILE        Read UBUNTU_2404_IMAGE_URL / DEBIAN_12_IMAGE_URL from this file
  --static CIDR,GW       Static IP instead of DHCP, e.g. 192.0.2.10/24,192.0.2.1
  --install-agent        Install qemu-guest-agent into the image with virt-customize
  -h, --help             Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --os) OS="$2"; shift 2 ;;
    --vmid) VMID="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --storage) STORAGE="$2"; shift 2 ;;
    --bridge) BRIDGE="$2"; shift 2 ;;
    --vlan) VLAN="$2"; shift 2 ;;
    --ci-user) CI_USER="$2"; shift 2 ;;
    --ssh-key) SSH_KEY_FILE="$2"; shift 2 ;;
    --image-url) IMAGE_URL="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --static) IFS=, read -r cidr gw <<<"$2"; IP_CONFIG="ip=${cidr},gw=${gw}"; shift 2 ;;
    --install-agent) INSTALL_AGENT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[[ -n "$OS" && -n "$VMID" ]] || { usage; exit 1; }
command -v qm >/dev/null || die "qm not found. Run this script on a Proxmox VE node."
[[ $EUID -eq 0 ]] || die "Run as root on the Proxmox node."

if [[ -n "$ENV_FILE" ]]; then
  [[ -f "$ENV_FILE" ]] || die "Env file $ENV_FILE not found"
  # Only read the two image URL variables; never source the whole file.
  UBUNTU_2404_IMAGE_URL="$(grep -E '^UBUNTU_2404_IMAGE_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' || true)"
  DEBIAN_12_IMAGE_URL="$(grep -E '^DEBIAN_12_IMAGE_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' || true)"
fi

case "$OS" in
  ubuntu-24-04) IMAGE_URL="${IMAGE_URL:-${UBUNTU_2404_IMAGE_URL:-}}" ;;
  debian-12) IMAGE_URL="${IMAGE_URL:-${DEBIAN_12_IMAGE_URL:-}}" ;;
  *) die "Unsupported --os '$OS' (use ubuntu-24-04 or debian-12)" ;;
esac
[[ -n "$IMAGE_URL" ]] || die "No image URL. Pass --image-url or set it in the env file."
NAME="${NAME:-tmpl-$OS}"

if qm status "$VMID" >/dev/null 2>&1; then
  die "VMID $VMID already exists. Remove it first (qm destroy $VMID) or choose another ID."
fi
if [[ -n "$SSH_KEY_FILE" ]]; then
  [[ -f "$SSH_KEY_FILE" ]] || die "SSH key file $SSH_KEY_FILE not found"
  grep -q "PRIVATE KEY" "$SSH_KEY_FILE" && die "$SSH_KEY_FILE is a PRIVATE key. Use the .pub file."
fi

# 1. Download the official cloud image (cached, checksum-friendly filename)
mkdir -p "$WORKDIR"
IMAGE="$WORKDIR/$(basename "${IMAGE_URL%%\?*}")"
if [[ -f "$IMAGE" ]]; then
  log "Using cached image $IMAGE"
else
  log "Downloading $IMAGE_URL"
  curl -fL --retry 3 -o "$IMAGE.part" "$IMAGE_URL"
  mv "$IMAGE.part" "$IMAGE"
fi

WORK_IMAGE="$WORKDIR/${NAME}.qcow2"
cp -f "$IMAGE" "$WORK_IMAGE"

# Optional: bake qemu-guest-agent into the image so IPs are reported on first boot.
if [[ "$INSTALL_AGENT" -eq 1 ]]; then
  command -v virt-customize >/dev/null || die "virt-customize missing: apt install libguestfs-tools"
  log "Installing qemu-guest-agent into the image (virt-customize)"
  virt-customize -a "$WORK_IMAGE" --install qemu-guest-agent --run-command 'systemctl enable qemu-guest-agent' \
    --truncate /etc/machine-id
fi

# 2. Create the temporary VM
NET="virtio,bridge=${BRIDGE}"
[[ -n "$VLAN" ]] && NET="${NET},tag=${VLAN}"
log "Creating VM $VMID ($NAME)"
qm create "$VMID" --name "$NAME" --memory 2048 --cores 2 --cpu x86-64-v2-AES \
  --net0 "$NET" --scsihw virtio-scsi-single --ostype l26 \
  --description "Cloud-init template built from $(basename "$IMAGE") on $(date -u +%F)"

# 3 + 4. Import the cloud image as a SCSI disk
log "Importing disk into $STORAGE as scsi0"
qm set "$VMID" --scsi0 "${STORAGE}:0,import-from=${WORK_IMAGE},discard=on,iothread=1"

# 5. Boot from that disk
qm set "$VMID" --boot order=scsi0

# 6. Cloud-init drive + serial console (cloud images expect a serial console)
log "Adding cloud-init drive"
qm set "$VMID" --ide2 "${STORAGE}:cloudinit" --serial0 socket --vga serial0

# 7. QEMU guest agent
qm set "$VMID" --agent enabled=1,fstrim_cloned_disks=1

# 8. Networking via cloud-init (DHCP default, static optional)
qm set "$VMID" --ipconfig0 "$IP_CONFIG" --ciuser "$CI_USER"

# 9. SSH public key
if [[ -n "$SSH_KEY_FILE" ]]; then
  log "Adding SSH public key from $SSH_KEY_FILE"
  qm set "$VMID" --sshkeys "$SSH_KEY_FILE"
fi

# 10. Convert to template
log "Converting VM $VMID to a template"
qm template "$VMID"
rm -f "$WORK_IMAGE"

# 11. Result
log "Template ready"
echo "TEMPLATE_ID=$VMID"
echo "TEMPLATE_NAME=$NAME"
case "$OS" in
  ubuntu-24-04) echo "Set TEMPLATE_UBUNTU_2404_ID=$VMID in .env" ;;
  debian-12) echo "Set TEMPLATE_DEBIAN_12_ID=$VMID in .env" ;;
esac
