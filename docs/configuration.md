# Software configuration (Linux and Windows)

After a VM is created, the console installs software and configuration with **Ansible**
(`infra/ansible`). It runs automatically after *Deploy to Test*, *Recreate* and an approved *Promotion*,
and can be re-run with **Install software again** on the machine page (idempotent: unchanged things stay unchanged).

## Software is per project, not a fixed list

Three ways to get software onto a VM, from most to least reusable:

1. **Profiles** – Ansible roles that carry a `profile.yml`. The backend discovers them on every request from
   the built-in `infra/ansible/roles` and from every folder in `EXTRA_PROFILE_DIRS` (by default the repository's
   `profiles/` folder, mounted read-only at `/profiles`; point `PROFILES_DIR` at a project repository to use its
   roles). Add a folder → click **Refresh catalog** in the Software step → it is a checkbox. No code change, no rebuild.
2. **Extra packages** – any package name, typed per VM: apt names for Linux (`redis-server`, `git`,
   `nginx-extras=1.24.0-2`), Chocolatey IDs for Windows (`googlechrome`, `vscode`). Installed by the generic roles
   `packages_linux` / `packages_windows` through the package manager only.
3. **The assistant** works out what a description needs (required and optional), matches each need to a profile or a repository-checked package, and drafts a new role for the rest. Drafted roles wait in the **Review queue**; once approved they are stored in `APPROVED_PROFILES_DIR` and appear as profiles.

What is *not* possible, on purpose: arbitrary shell commands. Package names are syntax-checked (no spaces,
pipes, URLs), installed only via apt/Chocolatey, and `PACKAGE_DENYLIST` blocks names nobody may install.
Everything else is a reviewed role in a repository.

### Writing a project profile

```
profiles/redis/
├── profile.yml          # label, os_family (linux|windows), description, optional port
├── tasks/main.yml
└── handlers/main.yml    # optional
```

```yaml
# profile.yml
label: Redis
os_family: linux
description: Redis server, listening on localhost
port: 6379        # default port for the validation health check
```

Folder names must match `^[a-z][a-z0-9_]{1,40}$`; built-in roles win on name clashes; roles may use
`ansible.builtin`, `ansible.windows` and `chocolatey.chocolatey`. See `profiles/README.md`.

### Built-in profiles

| Profile | OS | What it does | Health port |
|---|---|---|---|
| *(base, always)* | Linux | apt updates, QEMU guest agent, unattended security upgrades, UTC, SSH keys-only/no root | 22 |
| `docker` | Linux | Docker Engine + Compose, cloud-init user in the `docker` group | – |
| `nginx` | Linux | Nginx with a landing page | 80 |
| `postgresql` | Linux | PostgreSQL (localhost only) | – |
| `node_exporter` | Linux | Prometheus node exporter | 9100 |
| *(base, always)* | Windows | QEMU guest agent service, UTC, ICMP allowed | 5986 |
| `iis` | Windows | IIS with a landing page, HTTP allowed in the firewall | 80 |
| `windows_tools` | Windows | 7-Zip, Git, Notepad++ via Chocolatey | – |
| `redis` *(example project profile)* | Linux | Redis bound to localhost | 6379 |

## How the console connects

| | Linux | Windows |
|---|---|---|
| Transport | SSH (`ansible_user` = `CI_USER`) | WinRM HTTPS 5986, NTLM |
| Credential | private key in `ANSIBLE_SSH_KEY_FILE` (Docker secret `ansible_ssh_key`), public half in `DEFAULT_SSH_PUBLIC_KEY` | `WINDOWS_ADMIN_PASSWORD` (Docker secret), set at first boot by cloudbase-init |
| Host keys | pinned per VM (`accept-new`), forgotten on recreate | self-signed listener (pin a CA in production) |
| Waits for | SSH + `cloud-init status --wait` | WinRM answering (up to 15 min) |

The inventory holds only the VM's IP (from the QEMU guest agent), its group and the profile list.
Passwords are read by Ansible from the environment, never written to disk, and masked in job logs.

If credentials are missing, configuration is **skipped** (logged) instead of failing; validation then reports
"Software installed: skipped" and fails if profiles were requested.

## Validation

Validation adds a **Software installed** check (last Ansible run succeeded) and runs the security baseline and
application tests, see [testing.md](testing.md).

## LXC containers and Docker services

Containers (stacks) are configured the same way, over SSH as `root` with the same key; Docker services run on a
machine with the `docker` profile through the `docker_services` role. See [stacks.md](stacks.md).

## Demo mode (mock)

In mock mode the Ansible run is simulated with realistic `TASK` / `PLAY RECAP` output, so the flow can be shown
without VMs.
