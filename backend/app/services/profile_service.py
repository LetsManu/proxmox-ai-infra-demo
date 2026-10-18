"""Software profiles, discovered at runtime.

A profile is any Ansible role that carries a `profile.yml` next to its
`tasks/main.yml`:

    label: Redis
    os_family: linux          # linux | windows
    description: Redis server on localhost
    port: 6379                # optional: default health-check port

Roles are searched in the built-in `infra/ansible/roles` and in every
directory listed in EXTRA_PROFILE_DIRS (e.g. a project's own `profiles/`
folder mounted into the container). A directory may hold the roles directly
or in a `roles/` subfolder. Adding software for a project therefore means
adding a role folder, not changing the console.
"""

from __future__ import annotations

import logging
import os
import re

import yaml

from ..config import Settings

log = logging.getLogger(__name__)

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
RESERVED = {"linux_base", "windows_base", "packages_linux", "packages_windows"}


def _roots(settings: Settings) -> list[tuple[str, str]]:
    """(roles directory, source label) in priority order: built-in first."""
    roots = [(os.path.join(settings.ansible_dir, "roles"), "built-in"),
             (settings.approved_profiles_dir or os.path.join(settings.workspace_dir, "profiles"), "approved")]
    for raw in re.split(r"[:,]", settings.extra_profile_dirs or ""):
        d = raw.strip()
        if not d:
            continue
        sub = os.path.join(d, "roles")
        roots.append((sub if os.path.isdir(sub) else d, os.path.basename(os.path.normpath(d)) or "project"))
    return roots


def roles_path(settings: Settings) -> str:
    """Value for ANSIBLE_ROLES_PATH so Ansible finds project roles too."""
    return ":".join(r for r, _ in _roots(settings) if os.path.isdir(r))


def load_profiles(settings: Settings) -> list[dict]:
    seen: dict[str, dict] = {}
    for root, source in _roots(settings):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            meta_path = os.path.join(root, name, "profile.yml")
            if name in RESERVED or not os.path.isfile(meta_path):
                continue
            if not os.path.isfile(os.path.join(root, name, "tasks", "main.yml")):
                log.warning("Profile %s in %s has no tasks/main.yml; ignored", name, root)
                continue
            try:
                with open(meta_path, encoding="utf-8") as fh:
                    meta = yaml.safe_load(fh) or {}
            except (OSError, yaml.YAMLError) as exc:
                log.warning("Cannot read %s: %s", meta_path, exc)
                continue
            if not KEY_RE.fullmatch(name) or meta.get("os_family") not in ("linux", "windows"):
                log.warning("Profile %s ignored: name must match %s and os_family be linux|windows", name, KEY_RE.pattern)
                continue
            if name in seen:
                log.warning("Profile %s from %s shadowed by %s", name, source, seen[name]["source"])
                continue
            port = meta.get("port")
            seen[name] = {
                "key": name,
                "label": str(meta.get("label") or name)[:60],
                "os_family": meta["os_family"],
                "description": str(meta.get("description") or "")[:200],
                "port": int(port) if isinstance(port, int) and 0 < port < 65536 else None,
                "source": source,
                "tests": meta.get("tests") if isinstance(meta.get("tests"), list) else [],
            }
    return sorted(seen.values(), key=lambda p: (p["os_family"], p["source"] != "built-in", p["label"].lower()))


def get_profiles(settings: Settings) -> dict[str, dict]:
    return {p["key"]: p for p in load_profiles(settings)}


# ---- free-form packages ------------------------------------------------------
# Installed only through the OS package manager (apt / Chocolatey), never a shell.
PACKAGE_RE = {
    "linux": re.compile(r"^[a-z0-9][a-z0-9.+\-]{0,62}(=[A-Za-z0-9.+:~\-]{1,40})?$"),
    "windows": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,99}$"),
}


def package_errors(settings: Settings, os_family: str, packages: list[str]) -> list[str]:
    errors = []
    deny = {d.strip().lower() for d in (settings.package_denylist or "").split(",") if d.strip()}
    manager = "apt" if os_family == "linux" else "Chocolatey"
    for p in packages:
        if not PACKAGE_RE[os_family].fullmatch(p):
            errors.append(f"'{p}' is not a valid {manager} package name")
        elif p.split("=")[0].lower() in deny:
            errors.append(f"Package '{p}' is not allowed on this platform")
    if len(set(packages)) != len(packages):
        errors.append("Packages must not repeat")
    return errors
