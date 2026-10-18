"""Post-deployment validation of a VM.

Checks (all must pass, the health check only if requested):
  1. VM is running                          (Proxmox status/current)
  2. QEMU guest agent reports an IPv4       (agent/network-get-interfaces)
  3. cloud-init completed                   (agent/file-read boot-finished)
  4. optional TCP service health check      (backend -> VM IP:port)
"""

from __future__ import annotations

import socket
import time
from typing import Callable

import httpx

from ..config import Settings
from .proxmox_service import MockProxmox, ProxmoxError, get_proxmox

Log = Callable[[str], None]


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def _poll(fn, timeout: float, interval: float):
    deadline = time.time() + timeout
    last_exc: Exception | None = None
    while True:
        try:
            result = fn()
            if result:
                return result
        except ProxmoxError as exc:
            last_exc = exc
        if time.time() >= deadline:
            if last_exc:
                raise last_exc
            return None
        time.sleep(interval)


def validate_vm(settings: Settings, *, vmid: int, env: str, health_check_port: int | None,
                health_check_path: str | None, simulate_failure: bool, log: Log, os_family: str = "linux",
                kind: str = "vm") -> dict:
    px = get_proxmox(settings)
    mock = isinstance(px, MockProxmox)
    if mock:
        px.set_failure(vmid, simulate_failure or settings.mock_fail_validation)
    timeout = 3 if mock else settings.validation_timeout_seconds
    interval = 0.4 / max(settings.mock_speed, 0.01) if mock else 5
    checks: list[dict] = []

    # 1. running
    log(f"[1/4] Checking that VM {vmid} is running")
    try:
        st = px.vm_status(vmid, kind)
        running = st["status"] == "running"
        checks.append(_check("vm_running", running, f"status={st['status']} uptime={st.get('uptime')}s"))
    except ProxmoxError as exc:
        checks.append(_check("vm_running", False, str(exc)))
        running = False
    log(f"      -> {'OK' if running else 'FAIL'}: {checks[-1]['detail']}")

    # 2. guest agent IP
    ip = None
    log("[2/4] Waiting for " + ("the container to get an IPv4 address" if kind == "lxc"
                                 else "QEMU guest agent to report an IPv4 address"))
    if running:
        try:
            ips = _poll(lambda: px.guest_ips(vmid, kind), timeout, interval)
            ip = ips[0] if ips else None
        except ProxmoxError as exc:
            log(f"      guest agent error: {exc}")
    checks.append(_check("guest_agent_ip", bool(ip), ip or "no IPv4 reported by qemu-guest-agent"))
    log(f"      -> {'OK' if ip else 'FAIL'}: {checks[-1]['detail']}")

    # 3. guest initialisation: cloud-init (Linux) / guest OS ready via agent (Windows)
    if kind == "lxc":
        log("[3/4] Container booted (LXC has no cloud-init; Ansible prepares it)")
        ready = bool(ip) and (px.ct_ready(vmid) if mock else True)
        checks.append(_check("cloud_init_completed", ready, "container up with network" if ready else
                             "container has no network or did not boot"))
    elif os_family == "windows":
        log("[3/4] Waiting for Windows to finish setup (guest agent get-osinfo)")
        os_name = _poll(lambda: px.guest_os(vmid), timeout, interval) if running else None
        if mock and (simulate_failure or settings.mock_fail_validation):
            os_name = None
        checks.append(_check("cloud_init_completed", bool(os_name),
                             os_name or "Windows setup not finished (no OS info from the guest agent)"))
    else:
        log("[3/4] Waiting for cloud-init to finish (/var/lib/cloud/instance/boot-finished)")
        ci_done = bool(running and _poll(lambda: px.cloud_init_done(vmid), timeout, interval))
        checks.append(_check("cloud_init_completed", ci_done,
                             "boot-finished present" if ci_done else
                             "cloud-init has not completed (boot-finished missing) within timeout"))
    guest_ready = checks[-1]["ok"]
    log(f"      -> {'OK' if guest_ready else 'FAIL'}: {checks[-1]['detail']}")

    # 4. optional service check
    if health_check_port:
        log(f"[4/4] Service health check on port {health_check_port}")
        ok, detail = False, "skipped: no IP"
        if ip and mock:
            ok, detail = guest_ready, (f"tcp://{ip}:{health_check_port} open" if guest_ready
                                   else f"tcp://{ip}:{health_check_port} connection refused")
        elif ip:
            ok, detail = _service_check(ip, health_check_port, health_check_path)
        checks.append(_check("service_health", ok, detail))
        log(f"      -> {'OK' if ok else 'FAIL'}: {detail}")
    else:
        log("[4/4] Service health check not requested (skipped)")

    return {"checks": checks, "ip_address": ip, "vmid": vmid, "environment": env}


def finish(result: dict, *, config_status: str | None, profiles: list[str], log: Log) -> dict:
    """Add the configuration check and the overall verdict."""
    checks = result["checks"]
    ok = config_status == "success" or (config_status == "skipped" and not profiles)
    detail = {
        "success": f"Ansible applied: base{''.join(', ' + p for p in profiles)}",
        "skipped": "skipped (no credentials configured)" + ("; profiles not installed" if profiles else ""),
        "failed": "Ansible run failed; see the deploy job log",
        None: "not configured yet",
    }.get(config_status, config_status)
    checks.append(_check("configuration_applied", ok, detail))
    log(f"[+]   Configuration -> {'OK' if ok else 'FAIL'}: {detail}")
    overall = "PASS" if all(c["ok"] for c in checks) else "FAIL"
    log(f"Validation result: {overall}")
    return {**result, "overall": overall, "checks": checks}


def _service_check(ip: str, port: int, path: str | None) -> tuple[bool, str]:
    if path:
        url = f"http://{ip}:{port}{path if path.startswith('/') else '/' + path}"
        try:
            r = httpx.get(url, timeout=5)
            return r.status_code < 500, f"GET {url} -> {r.status_code}"
        except httpx.HTTPError as exc:
            return False, f"GET {url} failed: {exc}"
    try:
        with socket.create_connection((ip, port), timeout=5):
            return True, f"tcp://{ip}:{port} open"
    except OSError as exc:
        return False, f"tcp://{ip}:{port} {exc}"
