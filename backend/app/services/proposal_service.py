"""Review queue for AI-drafted artefacts.

Kinds
  role   a new Ansible role (= software profile) for needs no existing profile covers
  tests  a test suite for one VM / stack (see test_service)

Every proposal gets automated safety checks first; nothing is used until a
person approves it. Approved roles are written to APPROVED_PROFILES_DIR, which
profile discovery includes, so they appear as regular software profiles.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

import yaml

from ..config import Settings
from ..database import session_scope
from ..models import Proposal
from ..workers.job_runner import add_history
from .profile_service import KEY_RE, RESERVED, get_profiles

# Modules a drafted role may use: package managers, files, services, downloads over
# HTTPS. No shell, command, raw, script, win_shell, win_command or win_powershell.
ALLOWED_MODULES = {
    "linux": {
        "apt", "package", "service", "systemd", "systemd_service", "copy", "lineinfile", "blockinfile",
        "file", "user", "group", "get_url", "unarchive", "uri", "wait_for", "debug", "set_fact", "stat",
        "assert", "apt_key", "apt_repository", "deb822_repository", "replace", "pip",
    },
    "windows": {
        "win_feature", "win_service", "win_copy", "win_file", "win_chocolatey", "win_get_url", "win_regedit",
        "win_package", "win_environment", "win_path", "debug", "set_fact", "assert", "win_stat", "win_uri",
        "win_wait_for",
    },
}
TASK_KEYWORDS = {
    "name", "become", "become_user", "notify", "when", "loop", "loop_control", "register", "vars", "tags",
    "changed_when", "failed_when", "ignore_errors", "until", "retries", "delay", "no_log", "environment",
    "with_items", "args", "check_mode",
}
PREFIXES = ("ansible.builtin.", "ansible.windows.", "chocolatey.chocolatey.", "ansible.legacy.")


def approved_dir(settings: Settings) -> str:
    return settings.approved_profiles_dir or os.path.join(settings.workspace_dir, "profiles")


def _module_of(task: dict) -> str | None:
    mods = [k for k in task if k not in TASK_KEYWORDS]
    if "block" in task or "include_role" in task or "import_tasks" in task or "include_tasks" in task:
        return "<include/block>"
    return mods[0] if len(mods) == 1 else (None if not mods else "<several>")


def review_role(settings: Settings, *, name: str, os_family: str, tasks_yaml: str,
                handlers_yaml: str = "") -> dict:
    """Automated checks for a drafted role. Returns {ok, checks:[{name, ok, detail}]}."""
    checks: list[dict] = []

    def add(n, ok, detail=""):
        checks.append({"name": n, "ok": bool(ok), "detail": detail})

    add("Valid profile name", KEY_RE.fullmatch(name) and name not in RESERVED,
        f"'{name}' must match {KEY_RE.pattern} and not be reserved")
    add("Name not taken", name not in get_profiles(settings), f"profile '{name}' already exists")
    parsed = {}
    for label, text in (("tasks", tasks_yaml), ("handlers", handlers_yaml)):
        try:
            data = yaml.safe_load(text) if text.strip() else []
            ok = isinstance(data, list) and all(isinstance(t, dict) for t in data)
            add(f"{label}/main.yml is a YAML task list", ok, "" if ok else "expected a list of tasks")
            parsed[label] = data if ok else []
        except yaml.YAMLError as exc:
            add(f"{label}/main.yml is valid YAML", False, str(exc).splitlines()[0])
            parsed[label] = []
    add("Has at least one task", len(parsed.get("tasks") or []) > 0)

    allowed = ALLOWED_MODULES[os_family]
    bad, insecure = [], []
    for task in (parsed.get("tasks") or []) + (parsed.get("handlers") or []):
        mod = _module_of(task)
        short = (mod or "").split(".")[-1] if mod and mod.startswith(PREFIXES) else mod
        if short not in allowed:
            bad.append(mod or "<none>")
            continue
        body = task.get(mod) if isinstance(task.get(mod), dict) else {}
        url = str(body.get("url", "")) if short in ("get_url", "win_get_url", "uri", "win_uri") else ""
        src = str(body.get("src", "")) if short == "unarchive" else ""
        for u in (url, src):
            if u and "://" in u and not u.startswith("https://"):
                insecure.append(u)
    add("Only allowed modules (no shell/command/raw/script)", not bad,
        "not allowed: " + ", ".join(sorted(set(bad))) if bad else "")
    add("Downloads use HTTPS", not insecure, ", ".join(insecure))
    secret_like = re.search(r"(?i)(password|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9/+]{8,}", tasks_yaml + handlers_yaml)
    add("No hard-coded secrets", not secret_like, "looks like a literal secret" if secret_like else "")

    if shutil.which("ansible-playbook") and all(c["ok"] for c in checks):
        ok, detail = _syntax_check(name, os_family, tasks_yaml, handlers_yaml)
        add("ansible-playbook --syntax-check", ok, detail)
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def _syntax_check(name: str, os_family: str, tasks_yaml: str, handlers_yaml: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "roles", name, "tasks"))
        with open(os.path.join(d, "roles", name, "tasks", "main.yml"), "w") as fh:
            fh.write(tasks_yaml)
        if handlers_yaml.strip():
            os.makedirs(os.path.join(d, "roles", name, "handlers"))
            with open(os.path.join(d, "roles", name, "handlers", "main.yml"), "w") as fh:
                fh.write(handlers_yaml)
        with open(os.path.join(d, "play.yml"), "w") as fh:
            fh.write(f"- hosts: {os_family}\n  gather_facts: false\n  roles: [{name}]\n")
        with open(os.path.join(d, "inv.ini"), "w") as fh:
            fh.write(f"[{os_family}]\nh\n")
        env = dict(os.environ, ANSIBLE_ROLES_PATH=os.path.join(d, "roles"), ANSIBLE_LOCAL_TEMP=os.path.join(d, "tmp"),
                   ANSIBLE_HOME=os.path.join(d, "home"))
        r = subprocess.run(["ansible-playbook", "-i", "inv.ini", "play.yml", "--syntax-check"], cwd=d, env=env,
                           capture_output=True, text=True, timeout=60)
        out = (r.stderr or r.stdout).strip().splitlines()
        return r.returncode == 0, "" if r.returncode == 0 else (out[-1] if out else "syntax error")


# ---- store -------------------------------------------------------------------

def _out(p: Proposal) -> dict:
    return {"id": p.id, "kind": p.kind, "name": p.name, "status": p.status, "target": p.target,
            "content": p.content, "review": p.review, "source": p.source, "created_by": p.created_by,
            "decided_by": p.decided_by, "decided_at": p.decided_at.isoformat() if p.decided_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None}


def create(*, kind: str, name: str, content: dict, review: dict, source: str, user: str, target: str = "") -> dict:
    with session_scope() as db:
        p = Proposal(kind=kind, name=name, content=content, review=review, source=source, created_by=user,
                     target=target)
        db.add(p)
        db.flush()
        return _out(p)


def get(pid: str) -> dict | None:
    with session_scope() as db:
        p = db.get(Proposal, pid)
        return _out(p) if p else None


def list_(kind: str | None = None, target: str | None = None, status: str | None = None) -> list[dict]:
    with session_scope() as db:
        q = db.query(Proposal)
        if kind:
            q = q.filter_by(kind=kind)
        if target:
            q = q.filter_by(target=target)
        if status:
            q = q.filter_by(status=status)
        return [_out(p) for p in q.order_by(Proposal.created_at.desc()).all()]


def supersede(pid: str) -> None:
    with session_scope() as db:
        p = db.get(Proposal, pid)
        if p and p.status == "pending":
            p.status = "superseded"


def decide(settings: Settings, pid: str, approve: bool, user: str) -> dict:
    with session_scope() as db:
        p = db.get(Proposal, pid)
        if not p:
            raise KeyError(pid)
        if p.status != "pending":
            raise ValueError(f"Proposal already {p.status}")
        if approve and not p.review.get("ok", False):
            raise ValueError("Automated checks failed; this proposal cannot be approved. Redraft it.")
        if approve and p.kind == "role":
            _install_role(settings, p)
        if approve and p.kind == "tests":
            for old in db.query(Proposal).filter_by(kind="tests", target=p.target, status="approved").all():
                old.status = "superseded"
        p.status = "approved" if approve else "rejected"
        p.decided_by = user
        p.decided_at = datetime.now(timezone.utc)
        out = _out(p)
    add_history(vm_name=p.target or p.name, environment="infra", action=f"{p.kind}-{out['status']}",
                status="success", user=user, plan_summary=f"{p.kind} proposal '{p.name}' {out['status']}")
    return out


def _install_role(settings: Settings, p: Proposal) -> None:
    c = p.content
    root = os.path.join(approved_dir(settings), p.name)
    if os.path.exists(root):
        raise ValueError(f"Profile folder {root} already exists")
    os.makedirs(os.path.join(root, "tasks"))
    with open(os.path.join(root, "tasks", "main.yml"), "w") as fh:
        fh.write(c["tasks_yaml"])
    if c.get("handlers_yaml", "").strip():
        os.makedirs(os.path.join(root, "handlers"))
        with open(os.path.join(root, "handlers", "main.yml"), "w") as fh:
            fh.write(c["handlers_yaml"])
    meta = {"label": c["label"], "os_family": c["os_family"], "description": c.get("description", "")}
    if c.get("port"):
        meta["port"] = int(c["port"])
    if c.get("tests"):
        meta["tests"] = c["tests"]
    meta["approved_by"] = p.decided_by or ""
    with open(os.path.join(root, "profile.yml"), "w") as fh:
        yaml.safe_dump(meta, fh, sort_keys=False)
