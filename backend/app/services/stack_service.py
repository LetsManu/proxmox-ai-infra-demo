"""Draft a stack (VMs, LXC containers, Docker services) from a plain-language request.

Claude proposes an architecture as JSON; without an API key, local recipes do.
Either way the draft is validated by StackSpec (limits, templates, profiles,
Docker rules), packages are checked against the repositories, and it always
starts in TEST. The operator edits and approves it by planning it.
"""

from __future__ import annotations

import re

from pydantic import ValidationError

from ..config import CT_CATALOG, STACK_LIMITS, TEMPLATE_CATALOG, Settings, template_entry
from ..schemas import StackSpec
from . import package_index
from .profile_service import load_profiles

SERVICE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "image": {"type": "string"},
        "ports": {"type": "array", "items": {"type": "string"}},
        "env": {"type": "object", "additionalProperties": {"type": "string"}},
        "volumes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "image", "ports", "env", "volumes"],
    "additionalProperties": False,
}

STACK_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": ["vm", "lxc"]},
                    "template": {"type": "string"},
                    "cores": {"type": "integer"},
                    "memory_mb": {"type": "integer"},
                    "disk_gb": {"type": "integer"},
                    "description": {"type": "string"},
                    "profiles": {"type": "array", "items": {"type": "string"}},
                    "packages": {"type": "array", "items": {"type": "string"}},
                    "services": {"type": "array", "items": SERVICE_SCHEMA},
                },
                "required": ["name", "kind", "template", "cores", "memory_mb", "disk_gb", "description",
                             "profiles", "packages", "services"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "description", "components", "notes"],
    "additionalProperties": False,
}


def system_prompt(settings: Settings) -> str:
    limits = STACK_LIMITS["test"]
    vm_t = ", ".join(f"{t['key']} ({t['os_family']})" for t in TEMPLATE_CATALOG)
    ct_t = ", ".join(c["key"] for c in CT_CATALOG)
    profiles = "; ".join(f"{p['key']} ({p['os_family']}): {p['description'] or p['label']}"
                         for p in load_profiles(settings))
    return f"""You design a small Proxmox deployment ("stack") for a request. Components are VMs (kind vm,
templates: {vm_t}) or LXC containers (kind lxc, templates: {ct_t}; Linux only, lighter, good for single
services). Docker services run on a component that has the "docker" profile; put containers that talk
to each other on the same Docker host (they reach each other by service name).
Rules: stack name and component names lowercase letters/digits/hyphens (stack <= 20, component <= 12
chars). TEST limits per machine: 4 vCPU, 8192 MB, 64 GB; whole stack: {limits['cores']} vCPU,
{limits['memory_mb']} MB, {limits['disk_gb']} GB, max {limits['components']} components. Size modestly.
Software profiles (only these keys): {profiles}. Extra packages: exact apt names (Linux) or Chocolatey
IDs (Windows). Docker: official images with a pinned major tag (e.g. postgres:17), ports "HOST:CONTAINER",
named volumes only ("data:/path"), env values plain text; every password/secret/token MUST be
"secret:<name>" (the host generates it; reuse the same name where two services share it).
Never invent real hostnames, IPs or secrets. Put assumptions and trade-offs in notes (max 5)."""


# ---- local recipes -----------------------------------------------------------

def _wordpress(lxc: bool, monitoring: bool) -> dict:
    comps = [{
        "name": "app", "kind": "vm", "template": "ubuntu-24-04", "cores": 2, "memory_mb": 4096, "disk_gb": 32,
        "description": "Docker host: WordPress + MariaDB", "profiles": ["docker"], "packages": [],
        "services": [
            {"name": "db", "image": "mariadb:11.4", "ports": [],
             "env": {"MARIADB_DATABASE": "wordpress", "MARIADB_USER": "wordpress",
                     "MARIADB_PASSWORD": "secret:db_password", "MARIADB_ROOT_PASSWORD": "secret:db_root_password"},
             "volumes": ["db-data:/var/lib/mysql"]},
            {"name": "wordpress", "image": "wordpress:6.8-apache", "ports": ["80:80"],
             "env": {"WORDPRESS_DB_HOST": "db", "WORDPRESS_DB_USER": "wordpress",
                     "WORDPRESS_DB_PASSWORD": "secret:db_password", "WORDPRESS_DB_NAME": "wordpress"},
             "volumes": ["wp-data:/var/www/html"]},
        ]}]
    if monitoring:
        comps.append(_monitor())
    notes = ["WordPress and MariaDB share one Docker host so they talk over the private compose network; "
             "the database port is not published.",
             "Database passwords are generated on the host (/opt/stacks/<stack>/.env) and never pass the console."]
    return {"name": "wordpress", "description": "WordPress site with MariaDB", "components": comps, "notes": notes}


def _monitor() -> dict:
    return {"name": "monitor", "kind": "lxc", "template": "debian-12-lxc", "cores": 1, "memory_mb": 1024,
            "disk_gb": 8, "description": "Prometheus + Grafana", "profiles": ["docker"], "packages": [],
            "services": [
                {"name": "prometheus", "image": "prom/prometheus:v3.5.0", "ports": ["9090:9090"], "env": {},
                 "volumes": ["prom-data:/prometheus"]},
                {"name": "grafana", "image": "grafana/grafana:12.1.0", "ports": ["3000:3000"],
                 "env": {"GF_SECURITY_ADMIN_PASSWORD": "secret:grafana_admin"}, "volumes": ["grafana-data:/var/lib/grafana"]},
            ]}


def _web_db(text: str, lxc: bool, monitoring: bool) -> dict:
    m = re.search(r"(\d+)\s*(?:x\s*)?(?:web|frontend|app)\s*(?:servers?|nodes?|vms?|containers?)?", text)
    n = max(1, min(int(m.group(1)), 4)) if m else 2
    kind = "lxc" if lxc else "vm"
    template = "debian-12-lxc" if lxc else "ubuntu-24-04"
    comps = [{"name": f"web{i + 1}", "kind": kind, "template": template, "cores": 1, "memory_mb": 1024,
              "disk_gb": 8 if lxc else 16, "description": f"Web server {i + 1} (Nginx)", "profiles": ["nginx"],
              "packages": [], "services": []} for i in range(n)]
    comps.append({"name": "db", "kind": "vm", "template": "ubuntu-24-04", "cores": 2, "memory_mb": 4096,
                  "disk_gb": 32, "description": "PostgreSQL database", "profiles": ["postgresql"], "packages": [],
                  "services": []})
    if monitoring:
        comps.append(_monitor())
    return {"name": "webapp", "description": f"{n} web servers and a PostgreSQL database", "components": comps,
            "notes": [f"{n} identical web nodes; put a load balancer or DNS round robin in front of them.",
                      "The database is a VM (not LXC): stateful data, full kernel, simpler backups.",
                      "PostgreSQL listens on localhost by default; open it to the web nodes deliberately."]}


def _single(settings: Settings, prompt: str) -> dict:
    from .ai_service import _local_spec

    spec = _local_spec(settings, prompt)
    return {"name": re.sub(r"-test$", "", spec["name"])[:20].strip("-") or "app",
            "description": spec["description"][:200],
            "components": [{"name": "app", "kind": "vm", "template": spec["template"], "cores": min(spec["cores"], 4),
                            "memory_mb": min(spec["memory_mb"], 8192), "disk_gb": min(spec["disk_gb"], 64),
                            "description": spec["description"][:200], "profiles": spec["profiles"],
                            "packages": spec["packages"], "services": []}],
            "notes": ["Single machine: nothing in the request needs several components."]}


def local_stack(settings: Settings, prompt: str) -> dict:
    text = prompt.lower()
    lxc = bool(re.search(r"\b(lxc|containers?)\b", text))
    monitoring = bool(re.search(r"\b(monitor\w*|prometheus|grafana|metrics)\b", text))
    if re.search(r"\b(wordpress|blog|cms)\b", text):
        return _wordpress(lxc, monitoring)
    if re.search(r"\b(web|frontend)\b", text) and re.search(r"\b(database|db|postgres\w*)\b", text):
        return _web_db(text, lxc, monitoring)
    draft = _single(settings, prompt)
    if monitoring:
        draft["components"].append(_monitor())
    return draft


# ---- validation --------------------------------------------------------------

def finalize(settings: Settings, raw: dict) -> dict:
    """Validate a drafted stack. Returns {stack, warnings, notes} or raises StackRejected."""
    warnings: list[str] = []
    name = re.sub(r"[^a-z0-9-]", "-", str(raw.get("name", "stack")).lower()).strip("-")[:20].strip("-") or "stack"
    name = re.sub(r"-test$", "", name)
    if len(name) < 3:
        name = f"{name}-app"
    comps = []
    for c in raw.get("components") or []:
        c = dict(c)
        c["name"] = re.sub(r"[^a-z0-9-]", "-", str(c.get("name", "app")).lower()).strip("-")[:12].strip("-") or "app"
        t = template_entry(c.get("template", ""))
        if c.get("kind") == "lxc" and t and t["os_family"] == "linux":
            c["template"] = "debian-12-lxc" if "debian" in c["template"] else "ubuntu-24-04-lxc"
        # check packages against the repositories; drop what does not exist
        family = "windows" if t and t["os_family"] == "windows" else "linux"
        pkgs = c.get("packages") or []
        if pkgs:
            lookup = package_index.check(settings, c["template"] if c.get("kind") == "vm" else
                                         c["template"].removesuffix("-lxc"), pkgs)
            missing = [p for p, r in lookup.items() if r["status"] == "missing"]
            if missing:
                warnings.append(f"{c['name']}: dropped packages not found in the {family} repository: "
                                f"{', '.join(missing)}")
            c["packages"] = [p for p in pkgs if p not in missing]
        comps.append(c)
    data = {"name": name, "environment": "test", "description": str(raw.get("description", ""))[:500],
            "components": comps}
    if str(raw.get("environment", "test")).lower() in ("prod", "production"):
        warnings.append("Drafts always start in TEST; production needs a validated TEST stack and approval.")
    try:
        stack = StackSpec(**data)
    except ValidationError as exc:
        errors = [str(e["msg"]).removeprefix("Value error, ") for e in exc.errors()]
        raise StackRejected(errors, data) from exc
    return {"stack": stack.model_dump(), "warnings": warnings, "notes": list(raw.get("notes") or [])[:5]}


class StackRejected(ValueError):
    def __init__(self, errors: list[str], draft: dict):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.draft = draft
