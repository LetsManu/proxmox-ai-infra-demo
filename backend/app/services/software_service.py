"""What software does a request need, and how can each need be met?

The assistant (Claude, or local recipes offline) lists *needs*, each marked
required or optional. Deterministic code then resolves every need to one of

  profile   an existing software profile (built-in, approved or project role)
  package   an apt / Chocolatey package, checked against the real repository
  role      a new role draft, put through automated review and into the
            proposals queue; usable only after a person approves it

Nothing the assistant says is trusted as-is: unknown profiles are dropped,
package names are validated and looked up, role drafts are reviewed.
"""

from __future__ import annotations

import os
import re

import yaml

from ..config import Settings, template_entry
from . import package_index, proposal_service
from .profile_service import get_profiles, package_errors

NEED_SCHEMA = {
    "type": "object",
    "properties": {
        "needs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "need": {"type": "string"},
                    "required": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "kind": {"type": "string", "enum": ["profile", "package", "role"]},
                    "name": {"type": "string"},
                    "role": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "description": {"type": "string"},
                            "port": {"type": "integer"},
                            "tasks_yaml": {"type": "string"},
                            "handlers_yaml": {"type": "string"},
                        },
                        "required": ["label", "description", "port", "tasks_yaml", "handlers_yaml"],
                        "additionalProperties": False,
                    },
                },
                "required": ["need", "required", "reason", "kind", "name"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["needs"],
    "additionalProperties": False,
}


def _system(settings: Settings, os_family: str) -> str:
    catalog = "; ".join(f"{k}: {p['description'] or p['label']}" for k, p in get_profiles(settings).items()
                        if p["os_family"] == os_family)
    manager = "Debian/Ubuntu apt package names" if os_family == "linux" else "Chocolatey package IDs"
    modules = ", ".join(sorted(proposal_service.ALLOWED_MODULES[os_family]))
    return f"""You plan the software for a {os_family} VM. List every need of the request.
required=true for what the request cannot work without; required=false for useful extras
(monitoring, backup, admin tools). For each need pick ONE way to meet it, in this order:
1. kind=profile, name = a key from this catalog: {catalog}
2. kind=package, name = exact {manager}, no versions unless asked
3. kind=role only if neither fits: name = snake_case, and fill "role" with an Ansible task list
   (tasks_yaml) and handlers (handlers_yaml, may be empty). Use only these modules: {modules}.
   No shell/command/raw/script. Downloads must be https. No secrets.
Do not list what a chosen profile already installs. Keep reasons to one sentence."""


# ---- local recipes (offline) -------------------------------------------------

def _role_template(name: str) -> dict | None:
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "role_templates", f"{name}.yml")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _need(need, required, reason, kind, name, role=None) -> dict:
    out = {"need": need, "required": required, "reason": reason, "kind": kind, "name": name}
    if role:
        out["role"] = role
    return out


RECIPES: list[tuple[str, str, list[dict]]] = [
    (r"\bwordpress\b", "linux", [
        _need("Web server", True, "Serves the WordPress site.", "profile", "nginx"),
        _need("PHP runtime", True, "WordPress is written in PHP; Nginx talks to PHP-FPM.", "package", "php-fpm"),
        _need("PHP MySQL driver", True, "WordPress stores its data in MySQL/MariaDB.", "package", "php-mysql"),
        _need("PHP GD", True, "Image uploads and thumbnails.", "package", "php-gd"),
        _need("PHP XML", True, "Needed by the WordPress editor and feeds.", "package", "php-xml"),
        _need("PHP cURL", True, "Plugin and core updates download over HTTPS.", "package", "php-curl"),
        _need("PHP mbstring", True, "Multibyte text handling.", "package", "php-mbstring"),
        _need("Database", True, "WordPress needs a MySQL-compatible database.", "package", "mariadb-server"),
        _need("WordPress itself", True, "No profile installs WordPress, so a role is drafted.", "role", "wordpress"),
        _need("Backups", False, "Encrypted file backups of uploads and database dumps.", "package", "restic"),
    ]),
    (r"\b(gitea|git server)\b", "linux", [
        _need("Git", True, "Gitea shells out to git.", "package", "git"),
        _need("Database", True, "Gitea stores metadata in PostgreSQL.", "profile", "postgresql"),
        _need("Reverse proxy", True, "TLS termination and port 80.", "profile", "nginx"),
    ]),
]

OPTIONAL_EXTRAS = {
    "linux": [_need("Monitoring", False, "Exposes CPU, memory and disk metrics for Prometheus.", "profile",
                    "node_exporter"),
              _need("Brute-force protection", False, "Bans IPs after repeated failed SSH logins.", "package",
                    "fail2ban")],
    "windows": [_need("Admin tools", False, "Git, 7-Zip and Notepad++ for operators.", "profile", "windows_tools")],
}


def _local_needs(settings: Settings, prompt: str, os_family: str, spec: dict) -> list[dict]:
    text = prompt.lower()
    needs: list[dict] = []
    for pattern, family, items in RECIPES:
        if family == os_family and re.search(pattern, text):
            for n in items:
                n = dict(n)
                if n["kind"] == "role":
                    n["role"] = _role_template(n["name"]) or {}
                needs.append(n)
    taken = {n["name"] for n in needs}
    catalog = get_profiles(settings)
    for key in spec.get("profiles") or []:
        if key not in taken:
            needs.append(_need(catalog.get(key, {}).get("label", key), True, "Asked for in the request.",
                               "profile", key))
    for pkg in spec.get("packages") or []:
        if pkg not in taken:
            needs.append(_need(pkg, True, "Asked for in the request.", "package", pkg))
    taken = {n["name"] for n in needs}
    needs += [dict(n) for n in OPTIONAL_EXTRAS[os_family] if n["name"] not in taken]
    return needs


# ---- resolution --------------------------------------------------------------

def _resolve(settings: Settings, needs: list[dict], template: str, os_family: str, *, user: str,
             source: str) -> list[dict]:
    catalog = get_profiles(settings)
    out: list[dict] = []
    packages = [n["name"] for n in needs if n["kind"] == "package"]
    valid = [p for p in packages if not package_errors(settings, os_family, [p])]
    lookup = package_index.check(settings, template, valid) if valid else {}
    pending_roles = {p["name"]: p for p in proposal_service.list_(kind="role")}
    seen: set[tuple[str, str]] = set()

    for n in needs:
        kind, name = n["kind"], str(n["name"]).strip()
        if (kind, name) in seen:
            continue
        seen.add((kind, name))
        item = {"need": n["need"][:80], "required": bool(n["required"]), "reason": n["reason"][:200],
                "kind": kind, "name": name}
        if kind == "profile":
            p = catalog.get(name)
            if not p or p["os_family"] != os_family:
                item.update(status="unknown", detail="No such profile for this OS; ignored.")
            else:
                item.update(status="ready", label=p["label"], detail=f"{p['source']} profile")
        elif kind == "package":
            errs = package_errors(settings, os_family, [name])
            if errs:
                item.update(status="invalid", detail=errs[0])
            else:
                r = lookup.get(name, {"status": "unverified", "source": "offline"})
                item.update(status=r["status"], detail={
                    "available": f"found in the {'Chocolatey' if os_family == 'windows' else 'distribution'} "
                                 f"repository ({r['source']})",
                    "missing": "not found in the repository; it will not be installed",
                    "unverified": "could not be verified offline; installed if the repository has it",
                }[r["status"]])
        else:  # role
            if name in catalog:  # already approved earlier: use it as a profile
                item.update(kind="profile", status="ready", label=catalog[name]["label"],
                            detail=f"{catalog[name]['source']} profile")
            elif name in pending_roles and pending_roles[name]["status"] == "pending":
                prop = pending_roles[name]
                item.update(status="pending_review", proposal_id=prop["id"],
                            detail="Role draft waits for review in Proposals.")
            else:
                item.update(_propose_role(settings, n, name, os_family, user=user, source=source))
        out.append(item)
    return out


def _propose_role(settings: Settings, need: dict, name: str, os_family: str, *, user: str, source: str) -> dict:
    draft = need.get("role") or {}
    if not draft.get("tasks_yaml"):
        return {"status": "unresolved", "detail": "No profile or package covers this; add a project profile."}
    content = {"label": str(draft.get("label") or name)[:60], "os_family": os_family,
               "description": str(draft.get("description") or need["reason"])[:200],
               "port": draft.get("port") if isinstance(draft.get("port"), int) and 0 < draft["port"] < 65536 else None,
               "tasks_yaml": draft["tasks_yaml"], "handlers_yaml": draft.get("handlers_yaml") or "",
               "tests": draft.get("tests") or []}
    review = proposal_service.review_role(settings, name=name, os_family=os_family, tasks_yaml=content["tasks_yaml"],
                                          handlers_yaml=content["handlers_yaml"])
    prop = proposal_service.create(kind="role", name=name, content=content, review=review, source=source, user=user)
    if not review["ok"]:
        failed = next(c for c in review["checks"] if not c["ok"])
        return {"status": "rejected_by_checks", "proposal_id": prop["id"],
                "detail": f"Draft failed automated review: {failed['name']}"}
    return {"status": "pending_review", "proposal_id": prop["id"],
            "detail": "Role drafted and passed automated checks; waits for your review in Proposals."}


USABLE = {"ready", "available", "unverified"}


def analyze(settings: Settings, prompt: str, spec: dict, *, ai_call=None, user: str = "operator") -> dict:
    """Return {"items": [...], "source"}; `ai_call(system, schema)` returns the model's JSON or raises."""
    t = template_entry(spec.get("template", "")) or {}
    os_family = t.get("os_family", "linux")
    source = "local-rules"
    needs = None
    if ai_call is not None:
        try:
            needs = ai_call(_system(settings, os_family), NEED_SCHEMA)["needs"]
            source = f"anthropic:{settings.ai_model}"
        except Exception:  # noqa: BLE001 - fall back to the local recipes
            needs = None
    if needs is None:
        needs = _local_needs(settings, prompt, os_family, spec)
    items = _resolve(settings, needs, spec.get("template", ""), os_family, user=user, source=source)
    return {"items": items, "source": source, "os_family": os_family}


def apply_to_spec(spec: dict, analysis: dict) -> dict:
    """Required + usable items go into the spec; optional ones wait for the operator to tick them."""
    chosen = [i for i in analysis["items"] if i["required"] and i["status"] in USABLE]
    return {**spec,
            "profiles": list(dict.fromkeys(i["name"] for i in chosen if i["kind"] == "profile")),
            "packages": list(dict.fromkeys(i["name"] for i in chosen if i["kind"] == "package"))}
