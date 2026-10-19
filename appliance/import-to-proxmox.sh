#!/usr/bin/env bash
# Create the console VM from the appliance disk. Run as root on the Proxmox node (docs/appliance.md).
#   ./import-to-proxmox.sh --image proxmox-ai-infra-appliance-<version>.qcow2 --ssh-key ~/.ssh/id_ed25519.pub [options]
# Options (defaults in brackets):
#   --vmid N [first free from 300]   --name NAME [infra-console]   --storage STORAGE [local-lvm]
#   --bridge BRIDGE [vmbr0]          --vlan TAG [none]             --ip dhcp|CIDR [dhcp]   --gw GATEWAY
#   --user NAME [admin]              --cores N [2]                 --memory MB [4096]      --disk SIZE [32G]
#   --start                          start the VM when done
set -euo pipefail
die() { echo "Error: $*" >&2; exit 1; }

IMAGE=""; KEY=""; VMID=""; NAME=infra-console; STORAGE=local-lvm; BRIDGE=vmbr0; VLAN=""; IP=dhcp; GW=""
USER_NAME="admin"; CORES=2; MEMORY=4096; DISK=32G; START=0
while [ $# -gt 0 ]; do
  case "$1" in
    --image) IMAGE=$2; shift 2 ;; --ssh-key) KEY=$2; shift 2 ;; --vmid) VMID=$2; shift 2 ;;
    --name) NAME=$2; shift 2 ;; --storage) STORAGE=$2; shift 2 ;; --bridge) BRIDGE=$2; shift 2 ;;
    --vlan) VLAN=$2; shift 2 ;; --ip) IP=$2; shift 2 ;; --gw) GW=$2; shift 2 ;; --user) USER_NAME=$2; shift 2 ;;
    --cores) CORES=$2; shift 2 ;; --memory) MEMORY=$2; shift 2 ;; --disk) DISK=$2; shift 2 ;;
    --start) START=1; shift ;; -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done
command -v qm >/dev/null || die "run this on a Proxmox VE node"
[ -f "$IMAGE" ] || die "--image: file not found"
[ -f "$KEY" ] || die "--ssh-key: public key file needed (the appliance has no password login)"
grep -q "PRIVATE KEY" "$KEY" && die "--ssh-key must be the PUBLIC key (.pub)"
if [ -z "$VMID" ]; then VMID=300; while qm status "$VMID" >/dev/null 2>&1; do VMID=$((VMID + 1)); done; fi
qm status "$VMID" >/dev/null 2>&1 && die "VM $VMID exists already"

net="virtio,bridge=$BRIDGE"; [ -n "$VLAN" ] && net="$net,tag=$VLAN"
if [ "$IP" = dhcp ]; then ipcfg="ip=dhcp"; else ipcfg="ip=$IP${GW:+,gw=$GW}"; fi

echo "Creating VM $VMID ($NAME) on $STORAGE"
qm create "$VMID" --name "$NAME" --ostype l26 --machine q35 --cpu x86-64-v2-AES --cores "$CORES" --memory "$MEMORY" \
  --scsihw virtio-scsi-single --net0 "$net" --agent enabled=1 --serial0 socket --vga serial0 \
  --description "Proxmox AI Infra Console appliance. First login: ssh $USER_NAME@<ip>, then sudo pac-setup."
qm disk import "$VMID" "$IMAGE" "$STORAGE" >/dev/null
disk=$(qm config "$VMID" | sed -n 's/^unused0: //p')
[ -n "$disk" ] || die "import did not produce a disk"
qm set "$VMID" --scsi0 "$disk,discard=on,iothread=1" --boot order=scsi0 --ide2 "$STORAGE:cloudinit" \
  --ciuser "$USER_NAME" --sshkeys "$KEY" --ipconfig0 "$ipcfg" >/dev/null
qm disk resize "$VMID" scsi0 "$DISK" >/dev/null
echo "VM $VMID ready. Start it, then: ssh $USER_NAME@<ip> and sudo pac-setup"
if [ "$START" = 1 ]; then qm start "$VMID"; fi
