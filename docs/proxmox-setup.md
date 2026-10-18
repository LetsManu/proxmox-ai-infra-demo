# Proxmox preparation

Checklist for a Proxmox VE 8.x/9.x node before the console runs in live mode. Names below are examples; use your own and mirror them in `.env`.

## 1. Automation user and API token

Follow [api-token-setup.md](api-token-setup.md). Summary:

- user `automation@pve` (no password, no root)
- custom role `InfraDemo` with VM/datastore/SDN privileges only
- token `automation@pve!infra-demo` with `--privsep 1`
- ACLs on `/vms`, `/storage/<pool>`, `/sdn/zones/localnetwork`, `/nodes/<node>` for both user and token

## 2. Storage pools

| Purpose | Example | Required content types | `.env` |
|---|---|---|---|
| VM disks + cloud-init drives (TEST) | `local-lvm` (LVM-thin) | `images` | `TEST_STORAGE` |
| VM disks + cloud-init drives (PROD) | `local-lvm` or a separate pool | `images` | `PROD_STORAGE` |
| Template disks | same as TEST (linked clones need the template on the same storage) | `images` | `TEMPLATE_STORAGE` |
| Downloaded cloud images | `local` (directory) | `import` (8.4+), `iso` | `IMAGE_STORAGE` |
| Optional cloud-init snippets | `local` | `snippets` | `SNIPPETS_DATASTORE` |

```bash
pvesm status
pvesm set local --content iso,vztmpl,backup,import,snippets   # adjust to what you need
```

Linked clones (TEST) need a storage that supports them (LVM-thin, ZFS, Ceph RBD, qcow2 on directory). Production uses full clones, so it may live on a different pool.

## 3. Network: bridges and VLANs

The demo assumes one VLAN-aware bridge with two VLANs:

| Environment | Bridge | VLAN | Requirements |
|---|---|---|---|
| TEST | `vmbr0` | 30 | isolated from production; DHCP; DNS + outbound HTTP(S) to package mirrors so cloud-init can install packages |
| PROD | `vmbr0` | 10 | production network; DHCP or reservations |

Make the bridge VLAN-aware (*Node → System → Network → vmbr0 → VLAN aware*) or in `/etc/network/interfaces`:

```
auto vmbr0
iface vmbr0 inet static
    address 192.0.2.2/24
    gateway 192.0.2.1
    bridge-ports eno1
    bridge-stp off
    bridge-fd 0
    bridge-vlan-aware yes
    bridge-vids 2-4094
```

The switch port must trunk VLANs 10 and 30. If you prefer separate bridges (e.g. `vmbr1` for test), set `TEST_BRIDGE=vmbr1` and `TEST_VLAN=0`.

Firewall recommendation: TEST VLAN may not reach PROD VLAN. The console host must reach the Proxmox API (8006) and, for the optional service health check, the TEST/PROD VM IPs.

## 4. SSH keys

- Generate a dedicated key pair for VM access on your workstation: `ssh-keygen -t ed25519 -C "infra-demo" -f ~/.ssh/infra-demo`.
- Only the **public** key (`~/.ssh/infra-demo.pub`) goes into the template (`--ssh-key`) and/or `DEFAULT_SSH_PUBLIC_KEY`.
- The private key stays on your workstation. The console never needs it; the UI and backend reject anything that looks like a private key.

## 5. Templates

Build one template per OS with `infra/scripts/create-cloudinit-template.sh` on the node, see [cloud-images.md](cloud-images.md). Set the resulting IDs in `.env` (`TEMPLATE_UBUNTU_2404_ID`, `TEMPLATE_DEBIAN_12_ID`).

## 6. Optional: cloud-init package installs (snippets)

Packages from the VM form (e.g. `docker.io`) are rendered into a cloud-init vendor-data snippet only if `SNIPPETS_DATASTORE` is set. Uploading snippets is done by the provider over **SSH** to the node (Proxmox has no API for snippets), so it also needs an SSH user for the provider, e.g. by mounting an agent socket and setting `PROXMOX_VE_SSH_USERNAME` / `PROXMOX_VE_SSH_AGENT=true` for the backend. Without it, VMs still get the template's packages (including `qemu-guest-agent` if baked in with `--install-agent`). For the demo this stays off.

## 7. Pre-demo smoke test

```bash
qm list | grep -E '9000|9001'                 # templates exist
qm config 9000 | grep -E 'agent|ide2|scsi0'   # agent=1, cloudinit drive, disk
pvesm status                                  # pools active, free space
curl -sS -H "Authorization: PVEAPIToken=automation@pve!infra-demo=$SECRET" \
  https://<proxmox-host>:8006/api2/json/version
```
