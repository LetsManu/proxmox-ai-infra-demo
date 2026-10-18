# Cloud images and cloud-init templates

## What cloud images are

Distributions publish small, pre-installed disk images for clouds: no installer, a generic kernel, `cloud-init` already inside. On first boot cloud-init reads a configuration source (on Proxmox: the cloud-init drive) and sets the hostname, user, SSH key, network and optional packages.

A Proxmox **template** made from such an image can be cloned in seconds. Every clone is configured individually through cloud-init. This is what the console's OpenTofu module does.

| OS | Official image (default in `.env.example`) |
|---|---|
| Ubuntu 24.04 LTS (Noble) | `https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img` |
| Debian 12 (Bookworm) | `https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2` |

URLs live in configuration (`UBUNTU_2404_IMAGE_URL`, `DEBIAN_12_IMAGE_URL`), never in code. Checksums are published next to the images (`SHA256SUMS`, `SHA512SUMS`); verify them for production templates.

## Option A (recommended): the platform stack, from the console

`infra/platform` declares, per Linux template, a `proxmox_download_file` (the official image, content type
`import`) and a `proxmox_virtual_environment_vm` with `template = true` whose disk is `import_from` that file,
plus agent, serial console and a cloud-init drive. In the console: **Platform → Check what is missing** (plan) →
**Prepare platform** (apply). The console's token is enough (the bootstrap grants `Datastore.AllocateTemplate`
on the image storage). Requires PVE 8.4+.

Cloud images lack the QEMU guest agent. With `SNIPPETS_DATASTORE` set (and node SSH for the provider), every
Linux VM gets a vendor-data snippet that installs it on first boot; Ansible's base role installs it too.

## Option B: script on the Proxmox node (PVE 7.2+, or to bake the agent into the image)

`infra/scripts/create-cloudinit-template.sh` performs all steps:

1. download the official image (cached in `/var/tmp/cloud-images`)
2. optionally bake `qemu-guest-agent` into it (`--install-agent`, needs `libguestfs-tools`)
3. create a temporary VM (2 vCPU, 2 GB, virtio NIC on the bridge/VLAN)
4. import the image into the storage pool as `scsi0` (`import-from=`)
5. set `scsi0` as boot disk
6. add a cloud-init drive (`ide2`) and a serial console
7. enable the QEMU guest agent
8. set DHCP (default) or a static IP via cloud-init
9. add your SSH **public** key and the default user
10. convert the VM to a template
11. print `TEMPLATE_ID` and `TEMPLATE_NAME`

```bash
apt install -y libguestfs-tools          # once, for --install-agent
./create-cloudinit-template.sh --os ubuntu-24-04 --vmid 9000 --storage local-lvm \
    --bridge vmbr0 --ssh-key /root/infra-demo.pub --env-file ./.env --install-agent
./create-cloudinit-template.sh --os debian-12 --vmid 9001 --storage local-lvm \
    --bridge vmbr0 --ssh-key /root/infra-demo.pub --env-file ./.env --install-agent
```

Static IP instead of DHCP: `--static 192.0.2.50/24,192.0.2.1`. (Clones get their own IP config from OpenTofu; DHCP is the default there.)

The script only reads the two `*_IMAGE_URL` lines from the env file; it never sources it.

## Option C: manual commands

```bash
wget https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
virt-customize -a noble-server-cloudimg-amd64.img --install qemu-guest-agent --truncate /etc/machine-id
qm create 9000 --name tmpl-ubuntu-24-04 --memory 2048 --cores 2 --cpu x86-64-v2-AES \
   --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-single --ostype l26
qm set 9000 --scsi0 local-lvm:0,import-from=$PWD/noble-server-cloudimg-amd64.img,discard=on
qm set 9000 --boot order=scsi0 --ide2 local-lvm:cloudinit --serial0 socket --vga serial0
qm set 9000 --agent enabled=1 --ipconfig0 ip=dhcp --ciuser ops --sshkeys ~/.ssh/infra-demo.pub
qm template 9000
```

## QEMU guest agent

Without the agent Proxmox cannot report the VM's IP, and validation fails at "QEMU guest agent reports IP". Two parts are needed:

- **Proxmox side**: `agent: enabled=1` on the template (set by the script; clones inherit it, the OpenTofu module also sets `agent.enabled = true`).
- **Guest side**: the `qemu-guest-agent` package installed and running. Ubuntu/Debian cloud images do not include it. Bake it in with `--install-agent`, or install it via a cloud-init snippet.

## Verify a template

```bash
qm config 9000            # agent: enabled=1, ide2: ...cloudinit, scsi0, boot: order=scsi0, template: 1
qm clone 9000 950 --name tmpl-check
qm set 950 --ipconfig0 ip=dhcp && qm start 950
sleep 60
qm guest cmd 950 network-get-interfaces | jq '.[].["ip-addresses"][]?."ip-address"'
qm guest exec 950 -- cloud-init status --wait
qm stop 950 && qm destroy 950 --purge
```

Or in the console: **Create VM**, deploy to Test, then **Validate**.

## Update or recreate a template

Cloud images are rebuilt frequently (security updates). Templates are immutable, so rebuild:

1. Build the new template under a new ID (e.g. `9010`).
2. Set `TEMPLATE_UBUNTU_2404_ID=9010` and restart the backend.
3. New plans use the new template. Existing VMs show **replace** (template change forces a new clone) in their next plan: review it, recreate TEST VMs, promote with approval.
4. Remove the old template only after no **linked clone** depends on it (`qm list`, check `base-9000-disk-*` usage). Full clones (production) are independent.
