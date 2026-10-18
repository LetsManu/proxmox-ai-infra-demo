# Proxmox API token setup

The console authenticates to Proxmox VE with an **API token** of a dedicated, unprivileged user. It never uses root and never uses a password.

## Token format

| Part | Example | `.env` variable |
|---|---|---|
| User + realm | `automation@pve` | `PROXMOX_USER` |
| Token ID (name only) | `infra-demo` | `PROXMOX_TOKEN_ID` |
| Full token ID | `automation@pve!infra-demo` | (derived) |
| Secret (UUID) | `xxxxxxxx-xxxx-…` | `PROXMOX_TOKEN_SECRET` |

Every API request carries:

```
Authorization: PVEAPIToken=automation@pve!infra-demo=<secret>
```

OpenTofu gets the same token through `PROXMOX_VE_API_TOKEN=automation@pve!infra-demo=<secret>`, set by the backend in the child process environment only.

## 1. User

The `pve` realm (Proxmox VE authentication server) keeps the account local to Proxmox and separate from Linux users.

```bash
pveum user add automation@pve --comment "proxmox-ai-infra-demo automation"
```

No password is set: the user cannot log in to the web UI, it can only be used through tokens.

## 2. Role (least privilege)

Proxmox VE 8.x:

```bash
pveum role add InfraDemo -privs "\
VM.Allocate VM.Clone VM.Audit VM.PowerMgmt \
VM.Config.CDROM VM.Config.CPU VM.Config.Cloudinit VM.Config.Disk VM.Config.HWType \
VM.Config.Memory VM.Config.Network VM.Config.Options VM.Monitor \
Datastore.AllocateSpace Datastore.Audit SDN.Use Sys.Audit"
```

Proxmox VE 9.x split guest-agent access out of `VM.Monitor`:

```bash
pveum role add InfraDemo -privs "\
VM.Allocate VM.Clone VM.Audit VM.PowerMgmt \
VM.Config.CDROM VM.Config.CPU VM.Config.Cloudinit VM.Config.Disk VM.Config.HWType \
VM.Config.Memory VM.Config.Network VM.Config.Options \
VM.GuestAgent.Audit VM.GuestAgent.FileRead \
Datastore.AllocateSpace Datastore.Audit SDN.Use Sys.Audit"
```

| Privilege | Why |
|---|---|
| `VM.Allocate`, `VM.Clone` | create VMs by cloning templates, delete them on destroy/recreate |
| `VM.Config.*` | set CPU, memory, disk size, NIC/VLAN, cloud-init, options |
| `VM.PowerMgmt` | start/stop |
| `VM.Audit` | read VM status/config |
| `VM.Monitor` (8.x) / `VM.GuestAgent.Audit` + `VM.GuestAgent.FileRead` (9.x) | read guest-agent IPs and cloud-init's `boot-finished` file |
| `Datastore.AllocateSpace`, `Datastore.Audit` | allocate disks and the cloud-init drive |
| `SDN.Use` | attach NICs to the bridge/VLAN |
| `Sys.Audit` | list nodes, storage and network bridges |

Deliberately **not** granted: `Sys.Modify`, `Permissions.Modify`, `User.Modify`, `Sys.Console`, `VM.Console`, `Realm.*`.

Template building through the API (`POST /api/templates/build`) additionally needs `Datastore.AllocateTemplate` on the image storage. The recommended path is the shell script on the node, which needs no extra API rights.

## 3. Token (privilege separated)

```bash
pveum user token add automation@pve infra-demo --privsep 1 --comment "proxmox-ai-infra-demo"
```

The secret is printed **once**. Put it into `.env` (`PROXMOX_TOKEN_SECRET=`) or into `secrets/proxmox_token_secret` for the Docker-secrets override. Never paste it into chat, tickets or git.

With `--privsep 1` the token's effective rights are the **intersection** of the user's ACLs and the token's own ACLs, so both need entries. You can revoke or rotate the token without touching the user.

Optional expiry for demos: `--expire $(date -d '+7 days' +%s)`.

## 4. ACLs (scope)

```bash
for who in "-user automation@pve" '-token automation@pve!infra-demo'; do
  pveum acl modify /vms                     $who -role InfraDemo
  pveum acl modify /storage/local-lvm       $who -role InfraDemo   # TEST_STORAGE / PROD_STORAGE
  pveum acl modify /sdn/zones/localnetwork  $who -role InfraDemo   # plain Linux bridges (vmbr0)
  pveum acl modify /nodes/pve               $who -role InfraDemo   # node name
done
```

Tighter alternative: put the templates and all managed VMs into a resource pool (`pveum pool add infra-demo`) and grant `/pool/infra-demo` instead of `/vms`.

## 5. Verify

```bash
pveum user permissions automation@pve
pveum user token permissions automation@pve infra-demo

# From the machine that runs the console:
curl -sS -H "Authorization: PVEAPIToken=automation@pve!infra-demo=$PROXMOX_TOKEN_SECRET" \
  https://<proxmox-host>:8006/api2/json/nodes | jq
```

Then start the console with `LIVE_MODE=true`; the header shows `PVE 8.x · <node>` and the operating-system field shows no "not found on the node" warning.

## Rotation

```bash
pveum user token remove automation@pve infra-demo
pveum user token add automation@pve infra-demo --privsep 1
# re-run the token ACL lines, update .env / secret file, then:
docker compose up -d backend
```
