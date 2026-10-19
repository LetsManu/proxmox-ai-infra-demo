# Proxmox appliance (VM disk)

Each release from 2.1.0 on also has a ready-made VM disk: `proxmox-ai-infra-appliance-<version>.qcow2`. It is the
official Debian 12 cloud image with Docker, the console (frontend and backend) of that version, its container images
and Caddy for HTTPS. Import it on the Proxmox node, start it, run `sudo pac-setup` once, done. No registry access or
Docker knowledge needed.

| | |
|---|---|
| OS | Debian 12 (bookworm), cloud-init, QEMU guest agent, unattended security updates (no automatic reboots) |
| Console | `/opt/proxmox-ai-infra` (same layout as the install archive), started by `proxmox-ai-infra.service` |
| Images | backend, frontend, Caddy, loaded at build time (works offline) |
| Size | 16 GB virtual (grow it with `--disk`), about 1 GB download |
| Resources | 2 vCPU, 4 GB RAM is enough; OpenTofu and Ansible runs are the peak |

## 1. Import on the Proxmox node

Copy the disk, its `.sha256` and `import-to-proxmox.sh` (all on the release page) to the node, then as root:

```bash
sha256sum -c proxmox-ai-infra-appliance-<version>.qcow2.sha256
./import-to-proxmox.sh --image proxmox-ai-infra-appliance-<version>.qcow2 \
  --ssh-key ~/.ssh/id_ed25519.pub --storage local-lvm --bridge vmbr0 --start
```

Options: `--vmid` (default: first free from 300), `--name`, `--vlan`, `--ip 192.0.2.10/24 --gw 192.0.2.1` (default
DHCP), `--user` (default `admin`), `--cores`, `--memory`, `--disk` (default 32G). The script creates the VM (q35,
VirtIO SCSI, guest agent, serial console), imports the disk, adds a cloud-init drive with your user, SSH key and IP,
and grows the disk.

By hand, the same in the GUI: create a VM without disk, `qm disk import <vmid> <file> <storage>`, attach the unused
disk as `scsi0`, add a *CloudInit Drive*, set user, SSH key and IP under *Cloud-Init*, boot order `scsi0`.

Place the VM where it reaches the Proxmox API (8006) and, for Ansible, the Test and Production VLANs on SSH 22 and
WinRM 5986 (OVERVIEW.md, step 2).

## 2. First login and setup

```bash
ssh admin@<vm-ip>
sudo pac-setup
```

`pac-setup` is `scripts/install.sh` with the images already on the VM. It asks for:

- the Proxmox connection (live or demo mode, host, node, API token; [api-token-setup.md](api-token-setup.md)),
- the sign-in: `oidc` (Authentik, Entra ID, AD FS) or `ldap` (Active Directory, OpenLDAP) and the groups per role
  ([authentication.md](authentication.md)),
- the address people use, default `https://<vm-ip>`.

With sign-in configured, Caddy serves the console on **https://&lt;address&gt;** (port 80 redirects). Run `sudo pac-setup`
again at any time to change these answers; other settings are in `/opt/proxmox-ai-infra/.env` (then
`sudo systemctl restart proxmox-ai-infra`).

**Before setup, and with `AUTH_MODE=none`, nothing is published on the network.** The console listens on
`127.0.0.1:8080` only; reach it with an SSH tunnel: `ssh -L 8080:127.0.0.1:8080 admin@<vm-ip>`, then
http://localhost:8080 (demo mode until you connect Proxmox).

## Certificates

Default: Caddy's internal CA issues the certificate, so browsers warn until you trust that CA. Better:

- your own certificate: copy `console.crt` (with chain) and `console.key` to `/opt/proxmox-ai-infra/certs/`, set
  `CONSOLE_TLS=/certs/console.crt /certs/console.key` in `.env`, restart the service;
- or trust Caddy's root once: `sudo docker compose -f docker-compose.yml -f docker-compose.appliance.yml exec caddy cat /data/caddy/pki/authorities/local/root.crt`.

`PUBLIC_URL` must match what people type (OIDC redirect URI, sign-in origin check).

## Secrets on the appliance

Same as any installation: files in `/opt/proxmox-ai-infra/secrets/` (owned by uid 10001, mode 600). `pac-setup` writes
the Proxmox token and the OIDC client secret or LDAP bind password. Add the Ansible SSH key and the Windows password
as described in [configuration.md](configuration.md), then restart the service.

## Operations

| Task | How |
|---|---|
| Status, logs | `cd /opt/proxmox-ai-infra && sudo docker compose ps`, `sudo docker compose logs -f backend` |
| Backup | daily at 02:15 by cron to `/opt/proxmox-ai-infra/backups/` (keeps 14); copy them off the VM, or back up the whole VM with Proxmox (vzdump) |
| Restore | `sudo /opt/proxmox-ai-infra/scripts/restore.sh backups/console-<time>.tar.gz` |
| Upgrade | download the release archive to the VM, extract it over `/opt/proxmox-ai-infra`, then `sudo UPGRADE_BUILD=1 scripts/upgrade.sh` (builds on the VM), or with registry access (`docker login ghcr.io`) `sudo scripts/upgrade.sh`. Alternatively import the new appliance and restore a backup into it. |
| OS updates | security updates install automatically; reboot when convenient (`needrestart`, or `sudo reboot`) |

A Proxmox snapshot before `pac-setup` changes or upgrades is a cheap way back.

## How the disk is built

`appliance/build.sh <version> <out.qcow2>` (run by the release workflow): downloads the Debian 12 generic cloud image
and checks it against Debian's `SHA512SUMS`, boots it once in QEMU with a cloud-init seed that runs
`appliance/provision.sh` (Docker from Docker's apt repository, `docker load` of the images, the console under
`/opt/proxmox-ai-infra`, the systemd service, cron backup), then seals it: SSH host keys, machine ID and cloud-init
state are removed so every VM made from it gets its own. The result is compressed with zstd.
