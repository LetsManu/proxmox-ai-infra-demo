"""Automated acceptance tests for deployed VMs.

Tests are *declarative checks*, not code: each one is a typed record such as
{"type": "http", "port": 80, "path": "/", "contains": "WordPress"}. The AI (or
the local rules) only fills these fields; every field is validated here, and
the code that executes a type is our own reviewed code.

Where a check runs
  inside    via Ansible over SSH/WinRM (infra/ansible/tests.yml), sees local-only services
  external  from the console over the network: what other machines would see

A suite = built-in security baseline (always) + approved app checks.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import time
import uuid
from typing import Callable

import httpx

from ..config import Settings

Log = Callable[[str], None]

NAME_RE = re.compile(r"^[A-Za-z0-9@._-]{1,64}$")
LINUX_PATH_RE = re.compile(r"^/[A-Za-z0-9._/@-]{1,200}$")
WIN_PATH_RE = re.compile(r"^[A-Za-z]:\\[A-Za-z0-9 ._\\-]{1,200}$")
HTTP_PATH_RE = re.compile(r"^/[A-Za-z0-9._~/?&=%-]{0,200}$")

# type -> where, os families, required fields
CHECK_TYPES: dict[str, dict] = {
    "service_running": {"where": "inside", "os": {"linux", "windows"}, "fields": ["service"]},
    "port_listening": {"where": "inside", "os": {"linux", "windows"}, "fields": ["port"]},
    "package_installed": {"where": "inside", "os": {"linux", "windows"}, "fields": ["package"]},
    "http_local": {"where": "inside", "os": {"linux", "windows"}, "fields": ["port", "path"]},
    "file_contains": {"where": "inside", "os": {"linux", "windows"}, "fields": ["path", "pattern"]},
    "windows_feature": {"where": "inside", "os": {"windows"}, "fields": ["feature"]},
    "sshd_setting": {"where": "inside", "os": {"linux"}, "fields": ["key", "value"]},
    "auto_updates": {"where": "inside", "os": {"linux"}, "fields": []},
    "firewall_enabled": {"where": "inside", "os": {"windows"}, "fields": []},
    "container_running": {"where": "inside", "os": {"linux"}, "fields": ["service"]},
    "tcp_open": {"where": "external", "os": {"linux", "windows"}, "fields": ["port"]},
    "tcp_closed": {"where": "external", "os": {"linux", "windows"}, "fields": ["port"]},
    "http": {"where": "external", "os": {"linux", "windows"}, "fields": ["port", "path"]},
}

# Ports nothing should expose to the network unless a profile declares them.
SENSITIVE_PORTS = {21: "FTP", 23: "Telnet", 3306: "MySQL", 5432: "PostgreSQL", 6379: "Redis", 27017: "MongoDB",
                   9200: "Elasticsearch", 11211: "Memcached"}


# Files tests may not read (file_contains runs with root rights on the machine).
SENSITIVE_PATH_RE = re.compile(r"(?i)(/etc/(g?shadow|sudoers)|/root/|/\.ssh/|ssh_host_.*key|/opt/stacks/|/run/secrets|"
                               r"\.env$|\\config\\SAM|\.pem$|\.key$)")


def _port(v) -> bool:
    return isinstance(v, int) and 0 < v < 65536


def validate_checks(checks: list[dict], os_family: str) -> list[str]:
    errors = []
    for i, c in enumerate(checks):
        t = c.get("type")
        spec = CHECK_TYPES.get(t)
        label = f"check {i + 1} ({t})"
        if not spec:
            errors.append(f"{label}: unknown type; allowed: {sorted(CHECK_TYPES)}")
            continue
        if os_family not in spec["os"]:
            errors.append(f"{label}: not available on {os_family}")
        for f in spec["fields"]:
            if f not in c:
                errors.append(f"{label}: missing '{f}'")
        if "port" in c and not _port(c["port"]):
            errors.append(f"{label}: invalid port")
        for f in ("service", "package", "feature", "key"):
            if f in c and not NAME_RE.fullmatch(str(c[f])):
                errors.append(f"{label}: invalid {f}")
        if "value" in c and not NAME_RE.fullmatch(str(c["value"])):
            errors.append(f"{label}: invalid value")
        if "path" in c:
            rx = HTTP_PATH_RE if t in ("http", "http_local") else (WIN_PATH_RE if os_family == "windows" else LINUX_PATH_RE)
            if not rx.fullmatch(str(c["path"])):
                errors.append(f"{label}: invalid path")
        if "pattern" in c and not str(c["pattern"]).strip():
            errors.append(f"{label}: pattern must not be empty")
        for f in ("contains", "pattern", "title"):
            if f in c and (not isinstance(c[f], str) or len(c[f]) > 120 or "\n" in c[f]):
                errors.append(f"{label}: invalid {f}")
        # defence in depth: checks are passed to Ansible tagged !unsafe, and templates have no business here
        if any(isinstance(v, str) and re.search(r"[{}]|\{%|%\}", v) for v in c.values()):
            errors.append(f"{label}: '{{', '}}' are not allowed")
        if t == "file_contains" and "path" in c and SENSITIVE_PATH_RE.search(str(c["path"])):
            errors.append(f"{label}: this file may not be read by tests")
        if "status" in c and not (isinstance(c["status"], int) and 100 <= c["status"] < 600):
            errors.append(f"{label}: invalid status")
    return errors


def _norm(checks: list[dict], origin: str) -> list[dict]:
    out = []
    for c in checks:
        c = {k: v for k, v in c.items() if k in {"type", "title", "port", "path", "status", "contains", "service",
                                                  "package", "feature", "key", "value", "pattern"}}
        c.setdefault("title", _default_title(c))
        c["id"] = c.get("id") or uuid.uuid4().hex[:8]
        c["where"] = CHECK_TYPES[c["type"]]["where"]
        c["origin"] = origin
        out.append(c)
    return out


def _default_title(c: dict) -> str:
    t = c["type"]
    return {
        "service_running": f"Service {c.get('service')} is running",
        "port_listening": f"Something listens on port {c.get('port')}",
        "package_installed": f"Package {c.get('package')} is installed",
        "http_local": f"Local HTTP on port {c.get('port')} answers",
        "file_contains": f"{c.get('path')} contains {c.get('pattern')}",
        "windows_feature": f"Windows feature {c.get('feature')} is installed",
        "sshd_setting": f"SSH: {c.get('key')} {c.get('value')}",
        "auto_updates": "Automatic security updates are enabled",
        "firewall_enabled": "Windows Firewall is on for all profiles",
        "container_running": f"Container {c.get('service')} is running",
        "tcp_open": f"Port {c.get('port')} is reachable from the network",
        "tcp_closed": f"Port {c.get('port')} is NOT reachable from the network",
        "http": f"HTTP on port {c.get('port')} answers from the network",
    }[t]


def baseline(os_family: str, expected_ports: set[int], kind: str = "vm") -> list[dict]:
    """Security baseline: always part of validation, not AI-drafted."""
    if kind == "lxc":  # no guest agent; Ansible logs in as root with a key, never a password
        checks = [{"type": "sshd_setting", "key": "passwordauthentication", "value": "no",
                   "title": "SSH password login is disabled"},
                  {"type": "sshd_setting", "key": "permitrootlogin", "value": "without-password",
                   "title": "SSH root login only with a key"},
                  {"type": "auto_updates"}]
    elif os_family == "windows":
        checks = [{"type": "firewall_enabled"},
                  {"type": "tcp_closed", "port": 5985, "title": "Unencrypted WinRM (5985) is not reachable"},
                  {"type": "service_running", "service": "QEMU-GA", "title": "QEMU guest agent is running"}]
    else:
        checks = [{"type": "sshd_setting", "key": "passwordauthentication", "value": "no",
                   "title": "SSH password login is disabled"},
                  {"type": "sshd_setting", "key": "permitrootlogin", "value": "no", "title": "SSH root login is disabled"},
                  {"type": "auto_updates"},
                  {"type": "service_running", "service": "qemu-guest-agent", "title": "QEMU guest agent is running"}]
    checks += [{"type": "tcp_closed", "port": p, "title": f"{name} ({p}) is not exposed to the network"}
               for p, name in SENSITIVE_PORTS.items() if p not in expected_ports]
    return _norm(checks, "baseline")


def from_profiles(catalog: dict, profiles: list[str], packages: list[str], os_family: str) -> list[dict]:
    """Deterministic app checks: profile-declared tests, profile ports, installed packages."""
    checks: list[dict] = []
    for key in profiles:
        p = catalog.get(key) or {}
        declared = p.get("tests") or []
        if declared and not validate_checks(declared, os_family):
            checks += declared
        if p.get("port"):  # listening locally; network exposure is decided by explicit tcp_open/http checks
            checks.append({"type": "port_listening", "port": p["port"], "title": f"{p['label']} listens on port {p['port']}"})
    checks += [{"type": "package_installed", "package": pkg.split("=")[0]} for pkg in packages]
    return _norm(checks, "rules")


# ---- running -----------------------------------------------------------------

def run_external(ip: str | None, checks: list[dict], *, mock: bool, fail: bool) -> list[dict]:
    results = []
    for c in checks:
        if c["where"] != "external":
            continue
        if not ip:
            results.append({**c, "ok": False, "detail": "no IP address"})
            continue
        if mock:
            ok = not (fail and c["origin"] != "baseline")
            results.append({**c, "ok": ok, "detail": f"{'as expected' if ok else 'unexpected result'} (simulated)"})
            continue
        if c["type"] in ("tcp_open", "tcp_closed"):
            try:
                with socket.create_connection((ip, c["port"]), timeout=3):
                    is_open = True
            except OSError:
                is_open = False
            ok = is_open if c["type"] == "tcp_open" else not is_open
            results.append({**c, "ok": ok, "detail": f"tcp/{c['port']} {'open' if is_open else 'closed'}"})
        else:
            url = f"http://{ip}:{c['port']}{c['path']}"
            try:
                r = httpx.get(url, timeout=5, follow_redirects=True)
                ok = r.status_code == c.get("status", 200) and (c.get("contains", "") in r.text)
                results.append({**c, "ok": ok, "detail": f"GET {url} -> {r.status_code}"
                                + ("" if ok or c.get("contains", "") in r.text else f", '{c['contains']}' not found")})
            except httpx.HTTPError as exc:
                results.append({**c, "ok": False, "detail": f"GET {url} failed: {type(exc).__name__}"})
    return results


def run_inside(settings: Settings, *, name: str, env: str, ip: str | None, os_family: str, checks: list[dict],
               job_id: str, log: Log, mock: bool, fail: bool, kind: str = "vm") -> list[dict]:
    inside = [c for c in checks if c["where"] == "inside"]
    if not inside:
        return []
    if mock:
        time.sleep(0.2 / max(settings.mock_speed, 0.01))
        return [{**c, "ok": not (fail and c["origin"] != "baseline"),
                 "detail": "passed (simulated)" if not (fail and c["origin"] != "baseline") else "failed (simulated)"}
                for c in inside]
    from . import ansible_vars
    from .config_service import ConfigSkipped, ansible_env, inventory_for

    try:
        inv_path, env_vars = inventory_for(settings, name=name, env=env, ip=ip, os_family=os_family, job_id=job_id,
                                           kind=kind), \
            ansible_env(settings)
    except ConfigSkipped as exc:
        return [{**c, "ok": True, "skipped": True, "detail": f"not run: {exc}"} for c in inside]
    run_dir = os.path.dirname(inv_path)
    vars_path = os.path.join(run_dir, "checks.yml")
    ansible_vars.write(vars_path, {"checks": inside})  # never templated by Ansible
    cmd = ["ansible-playbook", "-i", inv_path, "-e", f"@{vars_path}", os.path.join(settings.ansible_dir, "tests.yml")]
    log("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=settings.ansible_dir, env=env_vars, capture_output=True, text=True, timeout=900,
                          stdin=subprocess.DEVNULL)
    found: dict[str, tuple[bool, str]] = {}
    for m in re.finditer(r"CHECK\|([0-9a-f]{8})\|(PASS|FAIL)\|([^\"\n]*)", proc.stdout):
        found[m.group(1)] = (m.group(2) == "PASS", m.group(3).strip())
    if proc.returncode not in (0, 2) and not found:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        for line in tail:
            log(line)
    return [{**c, "ok": found.get(c["id"], (False, ""))[0],
             "detail": found.get(c["id"], (False, "no result (host unreachable?)"))[1]} for c in inside]


# ---- suites ------------------------------------------------------------------

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": sorted(CHECK_TYPES)},
                    "title": {"type": "string"},
                    "port": {"type": "integer"},
                    "path": {"type": "string"},
                    "status": {"type": "integer"},
                    "contains": {"type": "string"},
                    "service": {"type": "string"},
                    "package": {"type": "string"},
                    "feature": {"type": "string"},
                    "pattern": {"type": "string"},
                },
                "required": ["type", "title"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["checks"],
    "additionalProperties": False,
}


def suite_key(vm_name: str) -> str:
    """TEST and PRODUCTION copies of a VM share one suite (name without -test)."""
    return re.sub(r"-test$", "", vm_name)


def _draft_system(os_family: str, spec: dict, catalog: dict) -> str:
    software = ", ".join([catalog.get(k, {}).get("label", k) for k in spec.get("profiles") or []]
                         + list(spec.get("packages") or [])) or "base system only"
    types = ", ".join(f"{t} ({v['where']}: {', '.join(v['fields']) or 'no fields'})"
                      for t, v in CHECK_TYPES.items() if os_family in v["os"])
    return f"""You write acceptance tests for a {os_family} VM: "{spec.get('description', '')}".
Installed software: {software}. Write 3-10 checks that prove the software works for its purpose,
using only these check types: {types}. "inside" checks run on the VM, "external" ones from the
network. Prefer one http/tcp_open check per service meant to be reachable, and service_running /
port_listening / http_local for internal ones. Security checks are added separately; do not repeat
them. Short titles stating what must be true."""


def draft_suite(settings: Settings, *, vm_name: str, spec: dict, ai_call=None, user: str = "operator") -> dict:
    """Draft app checks (AI or rules), validate them and queue them for review."""
    from . import proposal_service
    from .profile_service import get_profiles
    from .template_service import os_family_for

    os_family = os_family_for(spec.get("template", ""))
    catalog = get_profiles(settings)
    checks = from_profiles(catalog, spec.get("profiles") or [], spec.get("packages") or [], os_family)
    source, dropped = "local-rules", []
    if ai_call is not None:
        try:
            drafted = ai_call(_draft_system(os_family, spec, catalog), DRAFT_SCHEMA)["checks"][:20]
            ok = [c for c in drafted if not validate_checks([c], os_family)]
            dropped = [f"{c.get('title', c.get('type'))}: {validate_checks([c], os_family)[0]}"
                       for c in drafted if validate_checks([c], os_family)]
            checks += _norm(ok, "ai")
            source = f"anthropic:{settings.ai_model}"
        except Exception:  # noqa: BLE001 - rules-only suite
            pass
    seen, unique = set(), []
    for c in checks:
        sig = tuple(sorted((k, str(v)) for k, v in c.items() if k not in ("id", "title", "origin")))
        if sig not in seen:
            seen.add(sig)
            unique.append(c)
    errors = validate_checks(unique, os_family)
    review = {"ok": not errors and bool(unique), "checks": [
        {"name": "Every check uses a known type with valid fields", "ok": not errors, "detail": "; ".join(errors)},
        {"name": "At least one check", "ok": bool(unique), "detail": ""},
        {"name": "Invalid AI checks dropped", "ok": True, "detail": "; ".join(dropped) or "none"},
    ]}
    key = suite_key(vm_name)
    for old in proposal_service.list_(kind="tests", target=key, status="pending"):
        proposal_service.supersede(old["id"])
    return proposal_service.create(kind="tests", name=f"Tests for {key}", target=key,
                                   content={"os_family": os_family, "checks": unique}, review=review,
                                   source=source, user=user)


def approved_checks(vm_name: str) -> list[dict] | None:
    from . import proposal_service

    approved = proposal_service.list_(kind="tests", target=suite_key(vm_name), status="approved")
    return approved[0]["content"]["checks"] if approved else None


def build_suite(settings: Settings, vm_name: str, spec: dict, os_family: str) -> dict:
    from .profile_service import get_profiles

    app = approved_checks(vm_name)
    approved = app is not None
    if app is None:  # no reviewed suite yet: deterministic checks from the approved profiles only
        app = from_profiles(get_profiles(settings), spec.get("profiles") or [], spec.get("packages") or [], os_family)
    app = app + service_checks(spec.get("services") or [])
    exposed = {c["port"] for c in app if c["type"] in ("tcp_open", "http")}
    return {"checks": baseline(os_family, exposed, spec.get("kind", "vm")) + app, "approved": approved}


def service_checks(services: list[dict]) -> list[dict]:
    """Docker services on this host: each container runs, each published port answers."""
    checks: list[dict] = []
    for svc in services:
        checks.append({"type": "container_running", "service": svc["name"]})
        for p in svc.get("ports") or []:
            host_port = int(str(p).split(":")[0])
            checks.append({"type": "tcp_open", "port": host_port,
                           "title": f"{svc['name']} reachable on port {host_port}"})
    return _norm(checks, "rules")


def run_suite(settings: Settings, *, vm_name: str, env: str, spec: dict, os_family: str, ip: str | None,
              job_id: str, log: Log, mock: bool, fail: bool) -> dict:
    suite = build_suite(settings, vm_name, spec, os_family)
    checks = suite["checks"]
    log(f"Running {len(checks)} automated checks ({'reviewed suite' if suite['approved'] else 'rules only, no reviewed suite yet'})")
    results = run_inside(settings, name=vm_name, env=env, ip=ip, os_family=os_family, checks=checks,
                         job_id=job_id, log=log, mock=mock, fail=fail, kind=spec.get("kind", "vm")) + \
        run_external(ip, checks, mock=mock, fail=fail)
    order = {c["id"]: i for i, c in enumerate(checks)}
    results.sort(key=lambda r: order.get(r["id"], 0))
    for r in results:  # passing checks are listed in the result, not repeated in the log
        if r.get("skipped") or not r["ok"]:
            log(f"      {'SKIP' if r.get('skipped') else 'FAIL'}  [{r['where']}] {r['title']} - {r['detail']}")
    log(f"      {sum(1 for r in results if r['ok'] and not r.get('skipped'))}/{len(results)} checks passed")
    summary = {}
    for group, origins in (("security_baseline", {"baseline"}), ("app_tests", {"rules", "ai", "profile"})):
        rs = [r for r in results if r["origin"] in origins]
        failed = [r for r in rs if not r["ok"]]
        skipped = sum(1 for r in rs if r.get("skipped"))
        detail = (f"{len(rs) - len(failed) - skipped}/{len(rs)} passed" + (f", {skipped} skipped" if skipped else "")
                  + (f"; failed: {', '.join(r['title'] for r in failed[:3])}" if failed else ""))
        summary[group] = {"ok": not failed, "detail": detail if rs else "no checks"}
    return {"results": results, "summary": summary, "approved": suite["approved"]}
