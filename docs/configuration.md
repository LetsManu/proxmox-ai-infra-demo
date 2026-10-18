# Software configuration (Linux and Windows)

After a VM is created, the console installs software and configuration with **Ansible**
(`infra/ansible`). It runs automatically after *Deploy to Test*, *Recreate* and an approved *Promotion*,
and can be re-run with **Configure** (idempotent: unchanged things stay unchanged).

## Profiles

Software is chosen from a fixed catalog of profiles. Each profile is an Ansible role. Neither users nor the AI
can run arbitrary commands through the console; the AI can only pick profiles from this list.

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

Add a profile: create `infra/ansible/roles/<name>/tasks/main.yml` and an entry in `PROFILE_CATALOG`
(`backend/app/config.py`) with its OS family.

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
"Software configured: skipped" and fails if profiles were requested.

## Validation

Validation adds a **Software configured** check (last Ansible run succeeded) and uses the profile's port for the
service check by default (80 for `nginx`/`iis`).

## Mock mode

In mock mode the Ansible run is simulated with realistic `TASK` / `PLAY RECAP` output, so the flow can be shown
without VMs.
