"""Software configuration of deployed VMs with Ansible.

Linux VMs are reached over SSH as the cloud-init user with the private key
mounted from ANSIBLE_SSH_KEY_FILE; Windows VMs over WinRM as Administrator
with WINDOWS_ADMIN_PASSWORD (read by Ansible from the environment, never
written to disk). The inventory contains only the host, its group and the
selected profiles. Profiles map 1:1 to roles in infra/ansible/roles.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Callable

from ..config import Settings
from . import compose_service
from .profile_service import get_profiles, roles_path
from .proxmox_service import MockProxmox, get_proxmox

Log = Callable[[str], None]


class ConfigSkipped(Exception):
    """Configuration cannot run (missing credentials); not a failure of the VM."""


def known_hosts_path(settings: Settings, env: str, name: str) -> str:
    return os.path.join(settings.workspace_dir, "known_hosts", f"{env}-{name}")


def forget_host(settings: Settings, env: str, name: str) -> None:
    """A recreated VM has new SSH host keys: drop the pinned ones."""
    try:
        os.remove(known_hosts_path(settings, env, name))
    except FileNotFoundError:
        pass


def wait_for_ip(settings: Settings, vmid: int, log: Log, timeout: int | None = None, kind: str = "vm") -> str:
    px = get_proxmox(settings)
    mock = isinstance(px, MockProxmox)
    deadline = time.time() + (5 if mock else timeout or settings.validation_timeout_seconds)
    log("Waiting for " + ("the container's IPv4 address" if kind == "lxc"
                          else "the QEMU guest agent to report an IPv4 address"))
    while True:
        try:
            ips = px.guest_ips(vmid, kind)
            if ips:
                log(f"Guest agent reports {ips[0]}")
                return ips[0]
        except Exception:  # noqa: BLE001 - agent not up yet
            pass
        if time.time() > deadline:
            raise RuntimeError("No IPv4 address reported; cannot configure the machine")
        time.sleep(0.2 if mock else 5)


def inventory_for(settings: Settings, *, name: str, env: str, ip: str | None, os_family: str, job_id: str,
                  kind: str = "vm") -> str:
    """Write a one-host inventory for this job; raises ConfigSkipped without credentials."""
    if not ip:
        raise ConfigSkipped("the VM has no IP address")
    if os_family == "windows" and not settings.windows_admin_password.get_secret_value():
        raise ConfigSkipped("WINDOWS_ADMIN_PASSWORD is not set; skipping configuration")
    key = settings.ansible_ssh_key_file
    if os_family == "linux" and not (key and os.path.exists(key) and os.path.getsize(key) > 0):
        raise ConfigSkipped("ANSIBLE_SSH_KEY_FILE is not set or missing; skipping configuration")

    run_dir = os.path.join(settings.workspace_dir, "ansible", job_id)
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(os.path.dirname(known_hosts_path(settings, env, name)), exist_ok=True)
    host = {"ansible_host": ip}
    if os_family == "linux":
        host.update({
            "ansible_user": "root" if kind == "lxc" else settings.ci_user,  # LXC: root with key only
            "ansible_ssh_private_key_file": settings.ansible_ssh_key_file,
            "ansible_ssh_common_args": (f"-o StrictHostKeyChecking=accept-new "
                                        f"-o UserKnownHostsFile={known_hosts_path(settings, env, name)}"),
        })
    inv_path = os.path.join(run_dir, "inventory.json")
    with open(inv_path, "w") as fh:
        json.dump({os_family: {"hosts": {name: host}}}, fh)
    return inv_path


def ansible_env(settings: Settings) -> dict:
    env_vars = dict(os.environ)
    env_vars.update({
        "ANSIBLE_CONFIG": os.path.join(settings.ansible_dir, "ansible.cfg"),
        "ANSIBLE_ROLES_PATH": roles_path(settings),
        "ANSIBLE_FORCE_COLOR": "0",
        "ANSIBLE_NOCOLOR": "1",
        "WINDOWS_ADMIN_PASSWORD": settings.windows_admin_password.get_secret_value(),
    })
    return env_vars


def configure_vm(settings: Settings, *, name: str, env: str, ip: str, os_family: str, profiles: list[str],
                 job_id: str, log: Log, packages: list[str] | None = None, kind: str = "vm",
                 services: list[dict] | None = None, stack: str = "") -> dict:
    packages = packages or []
    services = services or []
    catalog = get_profiles(settings)
    labels = ", ".join(catalog.get(p, {}).get("label", p) for p in profiles) or "base only"
    log(f"Configuring {name} ({os_family}) with Ansible: {labels}"
        + (f"; packages: {', '.join(packages)}" if packages else ""))
    if not settings.live_mode:
        return _mock_run(settings, name, os_family, profiles, log, packages, services)

    inv_path = inventory_for(settings, name=name, env=env, ip=ip, os_family=os_family, job_id=job_id, kind=kind)
    vars_path = os.path.join(os.path.dirname(inv_path), "vars.json")
    with open(vars_path, "w") as fh:
        extra = {}
        if services:
            compose_yaml, secrets = compose_service.render(services)
            extra = {"compose_yaml": compose_yaml, "stack_secrets": secrets, "stack_name": stack or name}
        json.dump({"profiles": profiles, "packages": packages, **extra}, fh)
    env_vars = ansible_env(settings)
    cmd = ["ansible-playbook", "-i", inv_path, "-e", f"@{vars_path}", os.path.join(settings.ansible_dir, "site.yml")]
    log("$ " + " ".join(cmd))
    secret = settings.windows_admin_password.get_secret_value()
    proc = subprocess.Popen(cmd, cwd=settings.ansible_dir, env=env_vars, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                            stdin=subprocess.DEVNULL)
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if len(secret) >= 8:
            line = line.replace(secret, "***")
        if line.strip():
            log(line)
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ansible-playbook failed with exit code {rc}")
    return {"profiles": profiles, "packages": packages, "services": [x["name"] for x in services or []]}


def _mock_run(settings: Settings, name: str, os_family: str, profiles: list[str], log: Log,
              packages: list[str], services: list[dict] | None = None) -> dict:
    delay = 0.12 / max(settings.mock_speed, 0.01)
    base = {
        "linux": ["Wait until the VM accepts SSH", "Wait for cloud-init to finish", "Install base packages",
                  "Enable QEMU guest agent", "Enable automatic security updates", "SSH - keys only, no root login"],
        "windows": ["Wait until WinRM answers", "QEMU guest agent running", "Set time zone to UTC",
                    "Allow ICMP echo for monitoring"],
    }[os_family]
    per_profile = {
        "docker": ["Install Docker Engine and Compose", "Start Docker", "Let the cloud-init user run Docker"],
        "nginx": ["Install Nginx", "Landing page", "Start Nginx"],
        "postgresql": ["Install PostgreSQL", "Start PostgreSQL"],
        "node_exporter": ["Install Prometheus node exporter", "Start node exporter (port 9100)"],
        "iis": ["Install IIS", "Landing page", "Open HTTP in the firewall"],
        "windows_tools": ["Install admin tools with Chocolatey"],
    }
    log("")
    log(f"PLAY [Configure {'Linux' if os_family == 'linux' else 'Windows'} VMs] " + "*" * 40)
    changed = ok = 0
    tasks = base + [t for p in profiles for t in per_profile.get(p, [f"{p} : main"])]
    if packages:
        tasks.append(f"Install extra packages ({', '.join(packages)})")
    if services:
        tasks += ["docker_services : Write compose.yaml", "docker_services : Generate missing secrets (kept on the host)",
                  f"docker_services : docker compose up -d ({', '.join(s['name'] for s in services)})"]
    for task in tasks:
        time.sleep(delay)
        log(f"TASK [{task}] " + "*" * max(4, 50 - len(task)))
        status = "ok" if task.startswith("Wait") else "changed"
        changed += status == "changed"
        ok += 1
        log(f"{status}: [{name}]")
    log("")
    log("PLAY RECAP " + "*" * 50)
    log(f"{name:<24} : ok={ok}    changed={changed}    unreachable=0    failed=0    skipped=0")
    return {"profiles": profiles, "packages": packages, "services": [x["name"] for x in services or []]}
