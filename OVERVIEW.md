# Setup overview: from a bare Proxmox node to production

This guide takes you through every step, in order, from an empty Proxmox VE node to:

- a running console,
- templates built by the console itself,
- a first VM deployed to Test, tested and promoted to Production,
- a first stack (VM + container + Docker services).

Each step ends with a **Check** so you know it worked before you continue. Steps 11, 13 and 14 show every screen, from an empty environment to Test to Production. All names, hosts and addresses below are examples (`pve.example.internal`, `192.0.2.x`); use your own.

> **Only want to try it?** Skip to [Appendix A: demo mode](#appendix-a-demo-mode-no-proxmox). It runs the whole workflow without Proxmox.

---

## What you will end up with

```
 Your workstation                     Console host (Docker)                     Proxmox VE node
 ────────────────                     ─────────────────────                     ───────────────
 Step 5: bootstrap (admin, once) ───────────────────────────────────────────▶  user, role, API token, pool,
                                                                                image storage, SDN vnets
 Browser ──▶ :8080 frontend ──▶ backend (holds the API token) ── :8006 ──▶   templates, VMs, containers
                                       │                                          │
                                       └── SSH 22 / WinRM 5986 / app ports ──▶  Test VLAN 30 · Prod VLAN 10
```

| Who | Runs | With which rights |
|---|---|---|
| An administrator, once | `infra/scripts/bootstrap.sh` (OpenTofu, `infra/bootstrap`) | Proxmox admin, only in their shell |
| The console | platform stack (templates), machine stacks (VMs, containers), Ansible | the least-privilege API token from the bootstrap |
| Operators | the web console | no Proxmox credentials at all |

## Step overview

| # | Step | Where | Time |
|---|---|---|---|
| 1 | [Check requirements](#step-1-check-requirements) | – | 5 min |
| 2 | [Prepare the Proxmox network](#step-2-prepare-the-proxmox-network) | Proxmox node, switch | 15 min |
| 3 | [Check Proxmox storage](#step-3-check-proxmox-storage) | Proxmox node | 5 min |
| 4 | [Prepare the console host and get the code](#step-4-prepare-the-console-host-and-get-the-code) | console host | 10 min |
| 5 | [Run the bootstrap (admin, once)](#step-5-run-the-bootstrap-admin-once) | workstation | 10 min |
| 6 | [Create the SSH key for Ansible](#step-6-create-the-ssh-key-for-ansible) | workstation | 2 min |
| 7 | [Write `.env`](#step-7-write-env) | console host | 10 min |
| 8 | [Put the secrets in place](#step-8-put-the-secrets-in-place) | console host | 5 min |
| 9 | [Check network reachability](#step-9-check-network-reachability) | console host | 5 min |
| 10 | [Start the console](#step-10-start-the-console) | console host | 5 min |
| 11 | [Prepare the platform (templates)](#step-11-prepare-the-platform-templates) | browser | 5–15 min |
| 12 | [Optional: Windows, AI, project software](#step-12-optional-windows-ai-project-software) | various | – |
| 13 | [First VM: Test → validation → Production](#step-13-first-vm-test--validation--production) | browser | 15 min |
| 14 | [First stack](#step-14-first-stack) | browser | 15 min |
| 15 | [Before you hand it to others](#step-15-before-you-hand-it-to-others) | – | – |

Reference: [Day-2 operations](#day-2-operations) · [Troubleshooting](#troubleshooting) · [Appendix A: demo mode](#appendix-a-demo-mode-no-proxmox) · [Appendix B: without the bootstrap](#appendix-b-manual-setup-without-the-bootstrap)

---

## Step 1: Check requirements

| Component | Requirement |
|---|---|
| Proxmox VE | 8.4 or newer (the console builds templates through the API with content type `import`). 9.x works; set `pve_major=9` in step 5. On 7.2–8.3 build templates with the script instead (see [docs/cloud-images.md](docs/cloud-images.md), option B). |
| Proxmox resources | Free space for templates (~3 GB each) and machines. Test machines are limited to 4 vCPU / 8 GB / 64 GB each, a stack in Test to 16 vCPU / 32 GB / 384 GB. |
| Network | One VLAN-aware bridge (e.g. `vmbr0`) with a trunk to your switch; one VLAN for Test, one for Production; DHCP and DNS on both; outbound HTTP(S) from both (package mirrors, Docker Hub, Chocolatey). |
| Console host | Linux with Docker Engine and Docker Compose v2, 2 vCPU / 2 GB RAM; must reach the Proxmox API (8006) **and** the Test/Production VLANs (step 9). It can be a VM on the same Proxmox. |
| Workstation (admin) | `git`, [OpenTofu](https://opentofu.org/docs/intro/install/) 1.6+ (`tofu`), `python3`, `ssh-keygen`. Only for steps 5–6. |
| Optional | An Anthropic API key (AI assistance; without it, local rules are used). A Windows Server 2022 ISO and license (Windows machines). |

**Check:** `pveversion` on the node shows 8.4+ (or 9.x); `docker compose version` on the console host shows v2.

## Step 2: Prepare the Proxmox network

The bootstrap (step 5) creates an **SDN VLAN zone** with two virtual networks on top of your bridge:

| Virtual network | VLAN | Used for |
|---|---|---|
| `vtest` | 30 | Test machines (disposable, isolated) |
| `vprod` | 10 | Production machines |

Before that, the bridge must be VLAN-aware and the switch must trunk both VLANs.

1. **Make the bridge VLAN-aware.** In the Proxmox UI: *Node → System → Network → vmbr0 → Edit → VLAN aware ✓ → Apply Configuration*. Or in `/etc/network/interfaces`:
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
   Apply with `ifreload -a`.
2. **SDN prerequisites** (default on fresh 8.x/9.x installs): package `ifupdown2` installed, and `/etc/network/interfaces` ends with `source /etc/network/interfaces.d/*`.
3. **Switch:** the port of the Proxmox node is a trunk carrying VLANs 10 and 30.
4. **DHCP and DNS** on both VLANs (your router/firewall). Machines get their address by DHCP.
5. **Firewall rules** (recommended):
   - Test VLAN may **not** reach the Production VLAN.
   - Both VLANs may reach the internet over HTTP(S) (package mirrors, Docker Hub, Chocolatey).
   - The console host may reach both VLANs on SSH 22, WinRM 5986 and the application ports you publish (80, 443, …).

Different VLAN numbers or plain bridges are fine: pass `-var 'vnets={vtest=31,vprod=11}'` or `-var create_sdn=false` in step 5 (then set `TEST_BRIDGE`/`TEST_VLAN` yourself).

**Check:** a manually created VM on VLAN 30 gets an address by DHCP and can `curl https://deb.debian.org`.

## Step 3: Check Proxmox storage

| Purpose | Default | Content type needed | Setting |
|---|---|---|---|
| Disks of Test machines and templates | `local-lvm` | `images`, `rootdir` | `TEST_STORAGE`, `TEMPLATE_STORAGE` |
| Disks of Production machines | `local-lvm` (or a separate pool) | `images`, `rootdir` | `PROD_STORAGE` |
| Downloaded cloud images, LXC templates, cloud-init snippets | `infra-demo` (directory, **created by the bootstrap**) | `import`, `vztmpl`, `snippets`, `iso` | `IMAGE_STORAGE`, `CT_STORAGE`, `SNIPPETS_DATASTORE` |

Test machines are **linked clones**, so the template and Test disks must be on the same storage, and that storage must support linked clones (LVM-thin, ZFS, Ceph RBD or qcow2 on a directory). Production uses full clones.

**Check:** `pvesm status` on the node lists the storages as `active` with enough free space.

## Step 4: Prepare the console host and get the code

On the console host:

```bash
git clone https://github.com/LetsManu/proxmox-ai-infra-demo.git
cd proxmox-ai-infra-demo
cp .env.example .env
```

Clone it on the admin workstation too (for steps 5–6), or run those steps on the console host if OpenTofu is installed there.

**Check:** `ls` shows `docker-compose.yml`, `infra/`, `.env`.

## Step 5: Run the bootstrap (admin, once)

The bootstrap creates everything the console is **not** allowed to create itself:

- user `automation@pve`, without a password,
- role `InfraDemo`, with only the privileges the console needs,
- a privilege-separated API token `automation@pve!infra-demo`,
- ACLs on `/vms`, the pool, the storages, the SDN zone and the node,
- resource pool `infra-demo`,
- directory storage `infra-demo` (content import, vztmpl, snippets, iso),
- SDN zone `infrazn` with vnets `vtest` and `vprod`.

Run it from a repository checkout with a Proxmox admin login. The admin credentials only live in this shell:

```bash
export PROXMOX_VE_ENDPOINT=https://pve.example.internal:8006/
export PROXMOX_VE_USERNAME=root@pam
read -rs PROXMOX_VE_PASSWORD && export PROXMOX_VE_PASSWORD     # typed, not echoed
# self-signed Proxmox certificate (lab only):  export PROXMOX_VE_INSECURE=true

infra/scripts/bootstrap.sh -var node_name=pve -var pve_major=8 -var 'vm_storages=["local-lvm"]'
```

- `pve_major=9` on Proxmox VE 9 (guest-agent privileges differ).
- `vm_storages` lists every storage the console may put disks on: the Test, Production and template storages from step 3.
- Optional: `-var token_expiration_date=2027-12-31`, `-var create_sdn=false`, `-var create_image_storage=false`; see `infra/bootstrap/variables.tf`.

The script shows the OpenTofu plan and asks you to type `BOOTSTRAP`. Afterwards it writes the token secret to `secrets/proxmox_token_secret` and prints the values for `.env`, for example:

```
PROXMOX_USER=automation@pve
PROXMOX_TOKEN_ID=infra-demo
PROXMOX_NODE=pve
POOL_ID=infra-demo
IMAGE_STORAGE=infra-demo
SNIPPETS_DATASTORE=infra-demo
TEST_BRIDGE=vtest
TEST_VLAN=0
PROD_BRIDGE=vprod
PROD_VLAN=0
LIVE_MODE=true
```

Keep this output for step 7. If you ran the bootstrap on your workstation, copy `secrets/proxmox_token_secret` to the console host's `secrets/` folder (e.g. `scp`).

`infra/bootstrap/terraform.tfstate` also contains the token secret. Keep it private, never commit it (it is gitignored). You need it again only to change or remove the bootstrap resources.

**Check:** in the Proxmox UI, *Datacenter → Permissions → Users* shows `automation@pve`, and *API Tokens* shows `infra-demo`. *Datacenter → SDN* shows the vnets `vtest` and `vprod`. On the node: `pvesm status` lists `infra-demo`.

## Step 6: Create the SSH key for Ansible

The console installs software over SSH (Linux VMs, as the cloud-init user `ops`; containers, as `root`). Create a dedicated key pair:

```bash
ssh-keygen -t ed25519 -N '' -C infra-console -f ./infra-console
```

- `infra-console.pub` (public key): goes into `.env` as `DEFAULT_SSH_PUBLIC_KEY` and is put on every machine.
- `infra-console` (private key): becomes the secret `secrets/ansible_ssh_key` (step 8). It never goes into `.env`, the browser or git.

**Check:** `cat infra-console.pub` starts with `ssh-ed25519 `.

## Step 7: Write `.env`

Edit `.env` on the console host. `.env.example` explains every line. Set at least:

| Setting | Value |
|---|---|
| `LIVE_MODE` | `true` |
| `APP_USER` | name shown in the history, e.g. `it-operations` |
| `PROXMOX_HOST` | your node's DNS name or IP, e.g. `pve.example.internal` |
| `PROXMOX_VERIFY_SSL` | `true` with a trusted certificate; `false` only for a self-signed lab certificate |
| `PROXMOX_USER`, `PROXMOX_TOKEN_ID`, `PROXMOX_NODE`, `POOL_ID` | from the bootstrap output |
| `PROXMOX_TOKEN_SECRET` | **leave empty**: it comes from `secrets/` (step 8) |
| `TEST_BRIDGE`, `TEST_VLAN`, `PROD_BRIDGE`, `PROD_VLAN` | from the bootstrap output (`vtest`/`vprod`, VLAN `0` because the vnet tags the VLAN) |
| `TEST_STORAGE`, `PROD_STORAGE`, `TEMPLATE_STORAGE` | your disk storages from step 3 |
| `IMAGE_STORAGE`, `SNIPPETS_DATASTORE` | from the bootstrap output (`infra-demo`) |
| `UBUNTU_2404_IMAGE_URL`, `DEBIAN_12_IMAGE_URL` | keep the official defaults |
| `DEBIAN_12_CT_URL`, `UBUNTU_2404_CT_URL` | keep the defaults; check current file names with `pveam update && pveam available --section system` on the node |
| `TEMPLATE_UBUNTU_2404_ID`, `TEMPLATE_DEBIAN_12_ID`, `TEMPLATE_WINDOWS_2022_ID` | `9000`, `9001`, `9002`: change only if these IDs are taken |
| `DEFAULT_SSH_PUBLIC_KEY` | content of `infra-console.pub` |
| `ANSIBLE_SSH_KEY_FILE`, `WINDOWS_ADMIN_PASSWORD`, `ANTHROPIC_API_KEY` | **leave empty**: they come from `secrets/` |
| `AI_PROVIDER` | `anthropic` to use Claude (key in step 8), `none` for local rules |
| `PACKAGE_DENYLIST` | packages nobody may install, e.g. `telnetd,rsh-server` |
| `FRONTEND_BIND` | `127.0.0.1` (default): only reachable on the console host, publish it through your SSO/reverse proxy (step 15). `0.0.0.0` only on a trusted network: the console has no login of its own |

Leave `SNIPPETS_DATASTORE` empty if you don't give the console SSH access to the node (`PROXMOX_SSH_*`, see [docs/proxmox-setup.md](docs/proxmox-setup.md) section 6). Ansible installs the guest agent anyway; snippets only make the first boot report its IP sooner.

**Check:** `grep -E '^(LIVE_MODE|PROXMOX_HOST|TEST_BRIDGE|DEFAULT_SSH_PUBLIC_KEY)=' .env` shows your values; `grep '^PROXMOX_TOKEN_SECRET=' .env` is empty.

## Step 8: Put the secrets in place

Secrets are files in `secrets/` (gitignored), mounted into the backend as Docker secrets. All five files must exist; an **empty file means "not used"**.

```bash
mkdir -p secrets && chmod 700 secrets
# proxmox_token_secret: already written by the bootstrap (or copied in step 5)
cp ./infra-console secrets/ansible_ssh_key                            # private key from step 6
printf '%s' 'sk-ant-…'          > secrets/anthropic_api_key           # or: : > secrets/anthropic_api_key
printf '%s' '<12+ characters>'  > secrets/windows_admin_password      # or: : > secrets/windows_admin_password
: > secrets/proxmox_ssh_key                                           # node SSH for snippets; empty = off

# The backend runs as uid 10001 and must be able to read them:
sudo chown 10001:10001 secrets/*
sudo chmod 600 secrets/*
```

The `chown` matters: with files owned by your user and mode 600, the backend cannot read them and refuses to start, naming the file it cannot read.

Then delete the private key copy from places you don't need it (`shred -u ./infra-console` on the console host if you created it there).

**Check:** `sudo ls -ln secrets/` shows five files owned by `10001`, mode `-rw-------`, and `proxmox_token_secret` is not empty.

## Step 9: Check network reachability

The backend container reaches Proxmox and the machines through the console host's network. From the console host:

```bash
# Proxmox API with the console token (expect JSON with "version")
curl -sS -H "Authorization: PVEAPIToken=automation@pve!infra-demo=$(sudo cat secrets/proxmox_token_secret)" \
  https://pve.example.internal:8006/api2/json/version

# Routes to the machine networks: use the gateway (or any host) of each VLAN
ip route get 198.51.100.1          # example: Test VLAN gateway
ip route get 203.0.113.1           # example: Production VLAN gateway
nc -zv 198.51.100.20 22            # a VM in the Test VLAN, SSH reachable?
```

The console must reach Test and Production machines on SSH 22, WinRM 5986 and the ports your applications publish. If the console host is not in those VLANs, add routes and firewall rules accordingly.

**Check:** the `curl` returns `{"data":{"version":"8.x…"}}`. A `401` means a wrong user, token ID or secret; a `403` means missing ACLs (see [docs/api-token-setup.md](docs/api-token-setup.md)).

## Step 10: Start the console

```bash
docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d --build
docker compose ps                 # backend and frontend "healthy" after ~30 s
```

Open `http://localhost:8080` on the console host (or through your reverse proxy / an SSH tunnel: `ssh -L 8080:127.0.0.1:8080 <console-host>`). Both ports are bound to `127.0.0.1` by default; set `FRONTEND_BIND=0.0.0.0` only on a trusted network.

**Check:**

- The header shows a green **Connected to Proxmox** badge, not *Demo mode*.
- The resource tree shows your node name.
- `docker compose logs backend | grep -i error` is empty.

If the backend restarts in a loop, run `docker compose logs backend`. It usually reports an unreadable secret (step 8) or a wrong value in `.env`.

> The console has **no login of its own**. `APP_USER` is only a name for the audit trail. Before other people use it, put it behind your SSO or reverse proxy (step 15).

## Step 11: Prepare the platform (templates)

> The pictures in steps 11, 13 and 14 were taken in demo mode, so the header says *Demo mode* and addresses come from documentation ranges. In live mode the screens are the same, with **Connected to Proxmox** in the header. A red frame with a number marks what to click next.

**11.1 First start.** The dashboard tells you the platform is not ready yet: no templates exist, so no machines can be created. Click **Open Platform**.

![First start: platform not ready](docs/images/overview/01-dashboard-first-start.jpg)

**11.2 What the console needs.** The table lists every resource and who creates it:
- networks, storage and pool come from the admin bootstrap and should be **Present**;
- templates are created by this console and are **Missing**.

Click **Check what is missing**.

![Platform resources, templates missing](docs/images/overview/02-platform-missing.jpg)

**11.3 Review the plan.** OpenTofu plans 6 resources: two cloud images, two VM templates and two LXC templates. Risk is *Low* (nothing is changed or destroyed); **Why?** explains it. Click **Prepare platform**.

![Platform plan](docs/images/overview/03-platform-plan.jpg)

**11.4 Confirm.** The dialog lists exactly what will happen.

![Confirm the platform build](docs/images/overview/04-platform-confirm.jpg)

**11.5 Building.** Downloading the images takes a few minutes in live mode. The status card shows progress, and **Show details** opens the live log. You can leave the page.

![Platform building](docs/images/overview/05-platform-building.jpg)

**11.6 Ready.** Every resource is **Present**.

![Platform ready](docs/images/overview/06-platform-ready.jpg)

**Check:** the banner says *Ready. All templates and storage exist.* In Proxmox you see templates `9000 (tmpl-ubuntu-24-04)` and `9001 (tmpl-debian-12)` in pool `infra-demo`, and two `.tar.zst` files under `infra-demo → CT Templates`.

## Step 12: Optional: Windows, AI, project software

You can do any of these now or later.

- **Windows Server 2022.** There is no redistributable cloud image, so an administrator builds template `9002` once: [docs/windows-template.md](docs/windows-template.md). Requirements: VirtIO drivers, QEMU guest agent, cloudbase-init (reads the `configdrive2` cloud-init drive and creates the WinRM HTTPS listener with a new certificate on every clone), no unencrypted WinRM 5985, sysprep. Do not create the WinRM certificate in the template. Put a 12+ character password in `secrets/windows_admin_password`, then restart the backend: `docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d backend`.
- **AI assistance (Claude).** Set `AI_PROVIDER=anthropic` in `.env`, put the key in `secrets/anthropic_api_key` and restart the backend. Drafts, plan reviews and diagnoses then say *Claude* instead of *local rules*. The AI can draft and explain, never deploy or approve: [docs/ai-operations.md](docs/ai-operations.md).
- **Project software.** Put your own Ansible roles, each with a `profile.yml`, into `profiles/` (or point `PROFILES_DIR` at another folder). Click **Refresh catalog** in the Software step and they appear. See [profiles/README.md](profiles/README.md) and [docs/configuration.md](docs/configuration.md).

## Step 13: First VM: Test → validation → Production

The full life of one machine: describe it, deploy it to **Test**, prove it works, review the AI drafts, and promote it to **Production** with a person's approval.

### 13.1 Describe it

**Create VM** in the navigation. Describe the need in plain language and click **Draft with assistant**. **Skip, fill in myself** works too.

![Describe the machine](docs/images/overview/07-vm-describe.jpg)

### 13.2 Basics

Check name, operating system and size.
- The name must end in `-test`. Production gets the name without it (`wpsite-test` → `wpsite`), so use at least 3 characters before `-test`.
- Limits are shown next to each field.
- **Advanced options** holds the description and an optional per-machine SSH key.

![Basics](docs/images/overview/08-vm-basics.jpg)

### 13.3 Software

The assistant listed what the request **needs**, split into *Required* and *Optional*:

| Badge | Meaning |
|---|---|
| **Ready** | an existing software profile (Ansible role) |
| **In repository** | a package that was looked up in the official repository |
| **Waiting for review** | no profile covers it, so a role was drafted. It can be used only after approval in the **Review queue** |

Optional items (backups, monitoring, fail2ban) are your choice. **Other software profiles** and **Extra packages** are below.

![Software recommendations](docs/images/overview/09-vm-software.jpg)

### 13.4 Review and create the plan

A summary of everything you chose. Click **Create plan**; nothing changes on Proxmox yet.

![Review](docs/images/overview/10-vm-review.jpg)

### 13.5 Read the plan, then deploy

The plan in one sentence, the list of changes and a risk badge:
- **Why?** explains the rating and lists what to check;
- **View full plan** shows the raw OpenTofu output in a side panel.

Click **Deploy to Test**. It applies exactly this plan.

![Plan and risk](docs/images/overview/11-vm-plan.jpg)

### 13.6 Deploying

The status card shows progress; **Show details** opens the live log.

![Deploying](docs/images/overview/12-vm-deploying.jpg)

The log shows the OpenTofu apply, then Ansible installing the base configuration and the software:

![Live log](docs/images/overview/13-vm-deploy-log.jpg)

### 13.7 The Test machine

When the deployment finishes, the page switches to the machine. The lifecycle at the top shows where it stands. Click **Validate**.

![Deployed to Test](docs/images/overview/14-test-deployed.jpg)

### 13.8 Validation passed

One line per check: machine running, network address, first boot finished, **security baseline**, **application tests** and software installed. **Show details** lists every single test and where it ran (on the machine or from the network).

![Validation passed](docs/images/overview/15-test-validated.jpg)

### 13.9 If something fails

Failed checks turn red and the lifecycle step *Validated* turns red. Production stays locked. **Ask for a diagnosis** explains the likely cause.

![Validation failed](docs/images/overview/16-test-failed.jpg)

The diagnosis is advice only: what to check, a safe fix, and whether recreating the machine is safe or it may hold data. Fix the cause and **Validate** again, or **Recreate** a broken Test machine.

![Diagnosis](docs/images/overview/17-test-diagnosis.jpg)

### 13.10 Optional: AI-drafted tests

**Draft tests with assistant** proposes application tests for this machine. They are used only after someone approves them.

![Draft tests](docs/images/overview/18-test-draft-tests.jpg)

### 13.11 Review queue

Everything that waits for a person:
- production requests,
- drafted software roles,
- drafted test suites.

Each draft first passed automated safety checks. Click **Show details** to read one.

![Review queue](docs/images/overview/19-review-queue.jpg)

The side panel shows the automated checks first (allowed modules only, HTTPS downloads, no secrets, syntax check), then the role itself:

![Draft details](docs/images/overview/20-review-role-details.jpg)

**Approve** records your name. An approved role becomes a software profile; an approved test suite is used by every following validation.

![Approve a draft](docs/images/overview/21-review-approve.jpg)

### 13.12 Request production approval

Back on the Test machine, **Validate** again (now with the approved tests). When it passes, the next step is **Request production approval**. The console creates the Production plan, and nothing changes yet.

![Request production approval](docs/images/overview/22-prod-request.jpg)

### 13.13 Approve: the production dialog

The dialog lists exactly what will happen and how old the plan is (plans are valid for 60 minutes). **Approve and deploy** stays disabled until both are done:
- the checkbox *I understand this will affect the production environment.* is ticked;
- `PROMOTE` is typed exactly.

![Production dialog](docs/images/overview/23-prod-dialog.jpg)

![Production dialog filled in](docs/images/overview/24-prod-dialog-filled.jpg)

If you close the dialog instead, the request waits in the **Review queue**, so a colleague can approve or reject it. The API checks every rule again; the browser cannot skip them.

### 13.14 Deploying to Production

A full clone on the Production network, then the same software installation.

![Deploying to Production](docs/images/overview/25-prod-deploying.jpg)

### 13.15 In Production

All lifecycle steps are green. The resource tree shows `100 wpsite` under *Production*. Click **Open** to see the production machine.

![Promoted](docs/images/overview/26-prod-promoted.jpg)

### 13.16 Validate Production

Production machines are validated the same way, on the production network.

![Production machine](docs/images/overview/27-prod-machine.jpg)

![Production validated](docs/images/overview/28-prod-validated.jpg)

**Check:**
- Both machines show *Passed*.
- Proxmox shows VM `9xx wpsite-test` (linked clone, `vtest`) and VM `1xx wpsite` (full clone, `vprod`).
- **Activity** lists every step with your `APP_USER`.

## Step 14: First stack

A stack is several machines handled as one: one plan, one deployment, one validation verdict, one production approval. Details: [docs/stacks.md](docs/stacks.md).

### 14.1 Create stack

**Stacks** in the navigation → **Create stack**.

![Stacks](docs/images/overview/29-stacks-empty.jpg)

### 14.2 Describe the application

![Describe the stack](docs/images/overview/30-stack-describe.jpg)

### 14.3 Edit the architecture

The assistant proposes two machines:
- a **VM** `app` with the Docker profile, running `wordpress` and `db`;
- an **LXC container** `monitor` running Prometheus and Grafana.

You can change everything: type, OS, size, profiles, packages, services, ports and volumes. Passwords are `secret:<name>` references. The machine generates them into `/opt/stacks/<stack>/.env`, and they never pass through the console.

![Architecture editor](docs/images/overview/31-stack-architecture.jpg)

### 14.4 Review and plan

One plan for all machines of the stack.

![Stack review](docs/images/overview/32-stack-review.jpg)

![Stack plan](docs/images/overview/33-stack-plan.jpg)

### 14.5 Deployed to Test

Every machine is created, then gets its software and Docker services. Click **Validate stack**.

![Stack deployed](docs/images/overview/34-stack-deployed.jpg)

### 14.6 Validated

Each machine runs its checks: containers running, published ports open, security baseline. The stack passes only if every machine passes. Click **Request production approval**.

![Stack validated](docs/images/overview/35-stack-validated.jpg)

### 14.7 Approve the whole stack

Same dialog, one decision for all machines.

![Stack production dialog](docs/images/overview/36-stack-prod-dialog.jpg)

### 14.8 Stack in Production

![Stack promoted](docs/images/overview/37-stack-promoted.jpg)

**Check:**
- `http://<wordpress-app-test address>/` shows the WordPress installer.
- The stack page lists both members with *Installed* and *Passed*.

If the container fails with `only root can set 'features'`, the API token may not enable Docker nesting on your Proxmox version. Run the Docker host as a VM instead (change *Type* in the editor), or have an administrator enable nesting ([docs/stacks.md](docs/stacks.md)).

### 14.9 The end state

The dashboard per environment. **Test**:

![Dashboard Test](docs/images/overview/38-dashboard-test.jpg)

**Production**:

![Dashboard Production](docs/images/overview/39-dashboard-production.jpg)

**Activity**: every step, with who did it. Select a row to open its job log.

![Activity](docs/images/overview/40-activity.jpg)

## Step 15: Before you hand it to others

- [ ] Put the console behind SSO/a reverse proxy with TLS (e.g. oauth2-proxy, Authentik, your company IdP) and bind the frontend to that proxy only (`FRONTEND_BIND=127.0.0.1`).
- [ ] Set `APP_USER` per deployment, or pass the authenticated user name from the proxy if you extend the backend.
- [ ] Back up: the Docker volumes `proxmox-ai-infra_app-data` (history, machines, approvals) and `proxmox-ai-infra_tf-workspace` (OpenTofu state for Test and Production), and `infra/bootstrap/terraform.tfstate` (admin side).
- [ ] Give the API token an expiry date (`token_expiration_date`) and note when to rotate it.
- [ ] Set `PACKAGE_DENYLIST` for your policy; review which project profiles are mounted.
- [ ] Enable the secret-scanning pre-commit hook in your clone: `git config core.hooksPath .githooks`.
- [ ] Read [SECURITY.md](SECURITY.md) and the security model in [README.md](README.md#security-model).

---

## Day-2 operations

| Task | How |
|---|---|
| Update the console | `git pull && docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d --build` (data and state live in volumes) |
| Change a setting | edit `.env`, then `docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d backend` |
| Rotate the API token | re-run the bootstrap with a new `token_expiration_date` (or `pveum user token remove/add`), write the new secret to `secrets/proxmox_token_secret`, `chown 10001`, restart the backend |
| New cloud image version | build a new template under a new ID, change `TEMPLATE_*_ID`, restart; existing machines show *Replace* in their next plan ([docs/cloud-images.md](docs/cloud-images.md#update-or-recreate-a-template)) |
| Broken Test machine | machine page → **Recreate** (destroys and rebuilds from the template) |
| Software changed on a machine | machine page → **Install software again** (idempotent) |
| Watch what happened | **Activity**; job logs via **Show details**; `docker compose logs -f backend` |
| Back up | `docker run --rm -v proxmox-ai-infra_app-data:/d -v proxmox-ai-infra_tf-workspace:/w -v "$PWD":/b alpine tar czf /b/console-backup.tgz /d /w` |
| Remove everything the bootstrap created | `tofu -chdir=infra/bootstrap destroy` (admin shell, after removing all machines) |

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend restarts, log says *Cannot read /run/secrets/…* | secret files not readable by uid 10001 | `sudo chown 10001:10001 secrets/* && sudo chmod 600 secrets/*` |
| Header shows *Demo mode* | `LIVE_MODE` not `true`, or `.env` not next to `docker-compose.yml` | fix `.env`, restart the backend |
| Platform page: *Proxmox is not reachable* | DNS, firewall, TLS | `curl` from step 9; `PROXMOX_VERIFY_SSL=false` only for a self-signed lab cert |
| `401` in a job log | wrong `PROXMOX_USER` / `PROXMOX_TOKEN_ID` / secret | token ID is the name only (`infra-demo`) |
| `403 Permission denied` | ACL missing (often for the privilege-separated token) | re-run the bootstrap; [docs/api-token-setup.md](docs/api-token-setup.md) |
| Platform plan fails on `import` | Proxmox older than 8.4, or storage without content `import` | use the bootstrap storage, or build templates with the script |
| LXC template download fails (404) | template version on the mirror changed | `pveam available --section system`, update `*_CT_URL` |
| Validation: no network address | no DHCP on the VLAN, or guest agent not running yet | check DHCP; wait and validate again |
| Validation: first boot not finished | cloud-init can't reach package mirrors (DNS, outbound HTTP) | open the VM console: `cloud-init status --long` |
| *Software installed: skipped* | no SSH key / Windows password secret | step 8, restart, **Install software again** |
| Ansible `UNREACHABLE` | console host can't reach the machine's VLAN on 22/5986 | step 9: routes and firewall |
| Plan says `VM ID … outside the allowed range` | IDs 900–999 (Test) or 100–299 (Production) used by other VMs | free IDs or adjust `environments/*.tfvars` and the policy in `backend/app/config.py` |
| Assistant shows *local rules* | no key or `AI_PROVIDER=none` | step 12 |

More: [README.md#troubleshooting](README.md#troubleshooting), [docs/proxmox-setup.md](docs/proxmox-setup.md).

---

## Appendix A: demo mode (no Proxmox)

Everything runs simulated, with realistic plans, logs, IPs from 192.0.2.0/24, package lookups from a bundled index, and AI from local rules:

```bash
git clone https://github.com/LetsManu/proxmox-ai-infra-demo.git && cd proxmox-ai-infra-demo
cp .env.example .env              # LIVE_MODE=false is the default; no .env works too
docker compose up -d --build
# browse to http://localhost:8080
```

Follow steps 11, 13 and 14 in the browser. **Simulate a failure (demo mode)** on the machine page shows the diagnosis flow. Reset everything with `docker compose down -v && docker compose up -d`. The presenter script is [DEMO.md](DEMO.md).

## Appendix B: manual setup without the bootstrap

If you can't run OpenTofu with admin rights, create the same things by hand:

- user, role, token and ACLs: [docs/api-token-setup.md](docs/api-token-setup.md)
- storage, network and templates: [docs/proxmox-setup.md](docs/proxmox-setup.md) and [docs/cloud-images.md](docs/cloud-images.md)

Then continue with step 6. Set `POOL_ID=` (empty) if you didn't create a pool, and use your bridge and VLAN numbers directly (`TEST_BRIDGE=vmbr0`, `TEST_VLAN=30`, …). Add the privilege `Datastore.AllocateTemplate` on the image storage so the console can build templates.

## Where to read more

| Topic | Document |
|---|---|
| Architecture, data model, the three OpenTofu stacks | [docs/architecture.md](docs/architecture.md) |
| Proxmox details (storage, VLANs, snippets) | [docs/proxmox-setup.md](docs/proxmox-setup.md) |
| API token and privileges | [docs/api-token-setup.md](docs/api-token-setup.md) |
| Cloud images and templates | [docs/cloud-images.md](docs/cloud-images.md) |
| Windows template | [docs/windows-template.md](docs/windows-template.md) |
| Software profiles, packages, Ansible | [docs/configuration.md](docs/configuration.md) |
| Stacks, LXC, Docker services | [docs/stacks.md](docs/stacks.md) |
| Automated tests and review queue | [docs/testing.md](docs/testing.md) |
| AI features and guardrails | [docs/ai-operations.md](docs/ai-operations.md) |
| UI rules | [UI_GUIDELINES.md](UI_GUIDELINES.md) |
| Demo script | [DEMO.md](DEMO.md) |
