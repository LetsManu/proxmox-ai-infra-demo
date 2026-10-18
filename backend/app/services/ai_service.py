"""AI assistance: VM spec generation, plan explanation, troubleshooting.

Design rules
------------
* The AI is advisory only. Nothing here can approve, apply or promote anything.
* Every AI response is parsed, validated and post-processed by deterministic
  code. Unsafe values are rejected; risk levels can only be raised, never
  lowered, by the AI.
* If no API key is configured (or the provider fails), a deterministic local
  fallback produces conservative output, so the demo always works offline.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from ..config import ENVIRONMENTS, TEMPLATE_CATALOG, Settings, template_entry
from . import software_service
from .profile_service import load_profiles
from ..schemas import VmSpec

HUMAN_APPROVAL_NOTE = ("A human must review and explicitly approve every production change. "
                       "This assistant cannot approve or execute changes.")
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
DANGEROUS_COMMANDS = [r"rm\s+-rf\s+/(\s|$)", r"mkfs", r"\bdd\s+if=", r"curl[^|]*\|\s*(ba)?sh",
                      r"wget[^|]*\|\s*(ba)?sh", r":\(\)\s*\{", r"chmod\s+-R\s+777\s+/", r"shutdown|reboot|poweroff"]


class SpecRejected(ValueError):
    def __init__(self, errors: list[str], spec: dict | None = None):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.spec = spec


# ---------------------------------------------------------------------------
# Provider call
# ---------------------------------------------------------------------------

def _call_claude(settings: Settings, system: str, user: str, schema: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value(),
                                 timeout=60.0, max_retries=1)
    response = client.messages.create(
        model=settings.ai_model,
        max_tokens=settings.ai_max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model declined the request")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("response truncated (raise AI_MAX_TOKENS)")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def ai_caller(settings: Settings, user: str):
    """A `(system, schema) -> dict` callable bound to one user message, for services that build prompts."""
    return lambda system, schema: _call_claude(settings, system, user, schema)


def _with_fallback(settings: Settings, ai_fn, local_fn) -> dict:
    if not settings.ai_enabled:
        out = local_fn()
        out["source"] = "local-fallback"
        return out
    try:
        out = ai_fn()
        out["source"] = f"anthropic:{settings.ai_model}"
        return out
    except SpecRejected:
        raise
    except Exception as exc:  # provider down, bad key, network: fall back, never break the demo
        out = local_fn()
        out["source"] = "local-fallback"
        out.setdefault("warnings", []).append(f"AI provider unavailable ({type(exc).__name__}); used local analysis.")
        return out


# ---------------------------------------------------------------------------
# Plan parsing (deterministic) and summarisation
# ---------------------------------------------------------------------------

_ACTION_RE = re.compile(r"#\s+(\S+)\s+(?:will be|must be)\s+(created|updated in-place|destroyed|replaced)")
_PLAN_RE = re.compile(r"Plan:\s+(\d+) to add,\s+(\d+) to change,\s+(\d+) to destroy")


def parse_plan(plan_text: str) -> dict:
    create, update, destroy = [], [], []
    for addr, verb in _ACTION_RE.findall(plan_text):
        if verb == "created":
            create.append(addr)
        elif verb == "updated in-place":
            update.append(addr)
        elif verb == "destroyed":
            destroy.append(addr)
        elif verb == "replaced":
            destroy.append(addr)
            create.append(addr)
    m = _PLAN_RE.search(plan_text)
    counts = ({"create": int(m[1]), "update": int(m[2]), "destroy": int(m[3])} if m else
              {"create": len(create), "update": len(update), "destroy": len(destroy)})
    return {"create": create, "update": update, "destroy": destroy, "counts": counts,
            "no_changes": "No changes." in plan_text and not (create or update or destroy)}


def _baseline_risk(parsed: dict, env: str) -> str:
    if parsed["counts"]["destroy"] or parsed["destroy"]:
        return "high"
    if env == "prod" and (parsed["create"] or parsed["update"]):
        return "medium"
    if parsed["update"]:
        return "medium"
    return "low"


def _local_plan_summary(plan_text: str, env: str) -> dict:
    p = parse_plan(plan_text)
    label = ENVIRONMENTS[env].label
    risk = _baseline_risk(p, env)
    c = p["counts"]
    if p["no_changes"]:
        summary = f"No infrastructure changes in {label}. Nothing will be created, changed or destroyed."
    else:
        summary = (f"This {label} plan creates {c['create']}, updates {c['update']} and destroys "
                   f"{c['destroy']} resource(s). ")
        if c["destroy"]:
            summary += ("At least one VM will be DESTROYED (or destroyed and recreated). Any data on its "
                        "disks that is not backed up will be lost. ")
        elif c["update"]:
            summary += "Existing VMs are modified in place; some changes (CPU/RAM) may require a reboot. "
        else:
            summary += "Only new resources are added; existing VMs are not touched. "
    checks = ["Confirm the VM name and VM ID are the intended ones",
              "Confirm the template ID exists and is the expected OS version",
              "Confirm the network/VLAN matches the target environment"]
    if c["destroy"]:
        checks.insert(0, "Take and verify a backup/snapshot of every VM being destroyed")
        checks.append("Confirm no stateful data (databases, uploads) lives only on the destroyed VM")
    if env == "prod":
        checks.append("Confirm the TEST VM with the same spec passed validation")
        checks.append("Confirm a change window / stakeholder sign-off exists")
    return {
        "summary": summary.strip(),
        "resources_to_create": p["create"],
        "resources_to_update": p["update"],
        "resources_to_destroy": p["destroy"],
        "risk_level": risk,
        "recommended_checks": checks,
        "approval_recommendation": _approval_text(env, risk),
    }


def _approval_text(env: str, risk: str) -> str:
    if env != "prod":
        return ("TEST change: may be deployed after the operator reviews the plan." if risk != "high" else
                "TEST change includes a destroy: operator should confirm the VM is disposable before deploying.")
    if risk == "high":
        return "Do NOT approve until backups are verified and the destroy is understood. " + HUMAN_APPROVAL_NOTE
    return "Eligible for human review once TEST validation passed. " + HUMAN_APPROVAL_NOTE


PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "resources_to_create": {"type": "array", "items": {"type": "string"}},
        "resources_to_update": {"type": "array", "items": {"type": "string"}},
        "resources_to_destroy": {"type": "array", "items": {"type": "string"}},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "recommended_checks": {"type": "array", "items": {"type": "string"}},
        "approval_recommendation": {"type": "string"},
    },
    "required": ["summary", "resources_to_create", "resources_to_update", "resources_to_destroy",
                 "risk_level", "recommended_checks", "approval_recommendation"],
    "additionalProperties": False,
}

PLAN_SYSTEM = """You are a cautious infrastructure reviewer for a Proxmox VE platform managed with
Terraform/OpenTofu (bpg/proxmox provider). Explain the plan for an operator in plain English.
Rules: one short paragraph summary; list resource addresses per action; any destroy or replace is
HIGH risk; production changes are at least MEDIUM; recommend concrete pre-flight checks.
You can never approve or execute changes. Never say a change is approved. A human must approve
every production change."""


def summarize_plan(settings: Settings, plan_text: str, env: str) -> dict:
    local = _local_plan_summary(plan_text, env)

    def ai():
        out = _call_claude(settings, PLAN_SYSTEM,
                           f"Environment: {ENVIRONMENTS[env].label}\n\nPlan output:\n```\n{plan_text[:60000]}\n```",
                           PLAN_SCHEMA)
        # Safety post-processing: AI may only raise risk, never lower it.
        if RISK_ORDER.get(out.get("risk_level"), 0) < RISK_ORDER[local["risk_level"]]:
            out["risk_level"] = local["risk_level"]
        out["resources_to_destroy"] = sorted(set(out.get("resources_to_destroy", [])) |
                                             set(local["resources_to_destroy"]))
        out["approval_recommendation"] = re.sub(r"(?i)\bapproved\b", "eligible for review",
                                                out.get("approval_recommendation", ""))
        return out

    out = _with_fallback(settings, ai, lambda: dict(local))
    out["human_approval_required"] = env == "prod"
    out["human_approval_note"] = HUMAN_APPROVAL_NOTE
    out["environment"] = env
    return out


# ---------------------------------------------------------------------------
# VM spec generation
# ---------------------------------------------------------------------------

def _spec_schema(settings: Settings) -> dict:
    """JSON schema for drafts; the profile enum is the live, discovered catalog."""
    schema = json.loads(json.dumps(SPEC_SCHEMA))
    keys = [p["key"] for p in load_profiles(settings)]
    schema["properties"]["profiles"]["items"] = {"type": "string", "enum": keys} if keys else {"type": "string"}
    return schema


SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "environment": {"type": "string", "enum": ["test", "production"]},
        "template": {"type": "string"},
        "cores": {"type": "integer"},
        "memory_mb": {"type": "integer"},
        "disk_gb": {"type": "integer"},
        "network": {"type": "string"},
        "description": {"type": "string"},
        "cloud_init": {
            "type": "object",
            "properties": {
                "packages": {"type": "array", "items": {"type": "string"}},
                "commands": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["packages", "commands"],
            "additionalProperties": False,
        },
        "profiles": {"type": "array", "items": {"type": "string"}},
        "packages": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "environment", "template", "cores", "memory_mb", "disk_gb", "network",
                 "description", "cloud_init", "profiles", "packages", "warnings"],
    "additionalProperties": False,
}


def _spec_system(settings: Settings) -> str:
    t = ENVIRONMENTS["test"]
    templates = ", ".join(f"{x['key']} ({x['label']}, {x['os_family']})" for x in TEMPLATE_CATALOG)
    profiles = "; ".join(f"{p['key']} ({p['os_family']}): {p['description']}" for p in load_profiles(settings))
    return f"""You convert a natural-language VM request into a JSON VM definition for a Proxmox platform.
Allowed templates: {templates}. Name: lowercase letters, digits and hyphens, 3-42 chars (Windows: max 15),
ends with "-test" for test VMs. environment is "test" unless the user explicitly asks for production.
network must equal the environment ("test" or "prod"). TEST limits: max {t.max_cores} vCPU,
{t.max_memory_mb} MB RAM, {t.max_disk_gb} GB disk.
Software: first choose profiles ONLY from this catalog, matching the template's OS family: {profiles}.
For software no profile covers, add exact package names to "packages": Debian/Ubuntu apt names for Linux
(e.g. redis-server, git), Chocolatey package IDs for Windows (e.g. googlechrome, vscode). Only real package
names, no commands, no URLs. Leave cloud_init.packages and cloud_init.commands empty.
Report anything you changed or could not satisfy in warnings. Never invent secrets or SSH keys."""


def _local_spec(settings: Settings, prompt: str) -> dict:
    text = prompt.lower()

    def num(pattern: str, default: int) -> int:
        m = re.search(pattern, text)
        return int(m.group(1)) if m else default

    windows = bool(re.search(r"\b(windows|win\s?server|iis)\b", text))
    template = "windows-2022" if windows else "debian-12" if "debian" in text else "ubuntu-24-04"
    cores = num(r"(\d+)\s*(?:v?cpus?|cores?|vcores?)", 2)
    mem_gb = num(r"(\d+)\s*gb\s*(?:of\s*)?(?:ram|memory)", 4)
    disk = num(r"(\d+)\s*gb\s*(?:of\s*)?(?:disk|storage|ssd)", 32)
    env = "production" if re.search(r"\b(production|prod)\b", text) else "test"
    packages = [] if windows else ["qemu-guest-agent"]
    profiles: list[str] = []
    rules = ([(r"\b(iis|web)", "iis"), (r"\b(tools|git|7-?zip|chocolatey)", "windows_tools")] if windows else
             [(r"\bdocker", "docker"), (r"\b(nginx|web)", "nginx"), (r"\b(postgres|database)", "postgresql"),
              (r"\b(monitor|prometheus|metrics)", "node_exporter")])
    catalog = {p["key"]: p for p in load_profiles(settings)}
    family = "windows" if windows else "linux"
    for pattern, profile in rules:
        if re.search(pattern, text) and profile not in profiles and profile in catalog:
            profiles.append(profile)
    # Discovered project profiles: match their key or label
    for key, p in catalog.items():
        if p["os_family"] == family and key not in profiles and (
                re.search(rf"\b{re.escape(key.replace('_', ' '))}\b", text)
                or re.search(rf"\b{re.escape(p['label'].lower())}\b", text)):
            profiles.append(key)
    known = ({"git": "git", "7zip": "7zip", "vscode": "vscode", "chrome": "googlechrome", "firefox": "firefox"} if windows
             else {"git": "git", "htop": "htop", "redis": "redis-server", "curl": "curl", "jq": "jq", "vim": "vim"})
    covered = " ".join(f"{k} {catalog[k]['label'].lower()}" for k in profiles if k in catalog)
    extra = [pkg for word, pkg in known.items()
             if re.search(rf"\b{word}\b", text) and not re.search(rf"\b{word}\b", covered)]
    if windows and "windows_tools" in profiles:
        extra = [x for x in extra if x not in ("git", "7zip")]
    purpose = "web" if re.search(r"\bweb|\biis", text) else "db" if "database" in text or "postgres" in text else "app"
    name = f"win-{purpose}-test" if windows else f"demo-{purpose}-test"
    return {"name": name, "environment": env, "template": template, "cores": cores,
            "memory_mb": mem_gb * 1024, "disk_gb": max(disk, 40) if windows else disk, "network": "test",
            "description": prompt.strip()[:200], "profiles": profiles, "packages": extra,
            "cloud_init": {"packages": packages, "commands": []}, "warnings": []}


def validate_generated_spec(raw: dict) -> dict:
    """Validate an AI-produced spec. Returns {spec, warnings} or raises SpecRejected."""
    warnings = list(raw.get("warnings") or [])
    errors: list[str] = []
    env = str(raw.get("environment", "test")).lower()
    if env in ("production", "prod"):
        warnings.append("AI-generated specs always start in TEST. Production requires a passing TEST "
                        "validation and explicit human approval via the promotion workflow.")
    raw = {**raw, "environment": "test", "network": "test"}
    ci = raw.get("cloud_init") or {}
    for cmd in ci.get("commands", []):
        if any(re.search(p, cmd) for p in DANGEROUS_COMMANDS):
            errors.append(f"Unsafe cloud-init command rejected: '{cmd}'")
    t = template_entry(str(raw.get("template", ""))) or {}
    windows = t.get("os_family") == "windows"
    if windows:
        if ci.get("packages") or ci.get("commands"):
            warnings.append("Windows software is installed through profiles; packages/commands were dropped.")
        ci = {"packages": [], "commands": []}
    elif "qemu-guest-agent" not in ci.get("packages", []):
        ci.setdefault("packages", []).append("qemu-guest-agent")
        warnings.append("Added qemu-guest-agent (required for IP reporting and validation).")
    raw["cloud_init"] = ci
    raw["profiles"] = list(dict.fromkeys(raw.get("profiles") or []))
    raw["packages"] = list(dict.fromkeys(raw.get("packages") or []))
    policy = ENVIRONMENTS["test"]
    for key, limit, unit in (("cores", policy.max_cores, "vCPU"), ("memory_mb", policy.max_memory_mb, "MB RAM"),
                             ("disk_gb", policy.max_disk_gb, "GB disk")):
        if isinstance(raw.get(key), int) and raw[key] > limit:
            errors.append(f"Test: max {limit} {unit} (requested {raw[key]})")
    if not str(raw.get("name", "")).endswith("-test"):
        raw["name"] = re.sub(r"[^a-z0-9-]", "-", str(raw.get("name", "vm")).lower()).strip("-")[:37] + "-test"
    if windows and len(raw["name"]) > 15:
        raw["name"] = raw["name"][:10].rstrip("-") + "-test"
        warnings.append("Shortened the name: Windows computer names are limited to 15 characters.")
    if errors:
        raise SpecRejected(errors, raw)
    try:
        spec = VmSpec(**{k: v for k, v in raw.items() if k != "warnings"})
    except ValidationError as exc:
        errors += [f"{'.'.join(map(str, e['loc']))}: {str(e['msg']).removeprefix('Value error, ')}"
                   for e in exc.errors()]
        spec = None
    if errors:
        raise SpecRejected(errors, raw)
    return {"spec": spec.model_dump(), "warnings": warnings}


def generate_vm_spec(settings: Settings, prompt: str) -> dict:
    out = _with_fallback(
        settings,
        lambda: validate_generated_spec(_call_claude(settings, _spec_system(settings), prompt, _spec_schema(settings))),
        lambda: validate_generated_spec(_local_spec(settings, prompt)),
    )
    # Software: needs -> profiles / verified packages / reviewed role drafts
    ai_call = ai_caller(settings, prompt) if settings.ai_enabled else None
    analysis = software_service.analyze(settings, prompt, out["spec"], ai_call=ai_call, user=settings.app_user)
    try:
        out["spec"] = VmSpec(**software_service.apply_to_spec(out["spec"], analysis)).model_dump()
    except ValidationError as exc:
        out.setdefault("warnings", []).append(f"Software plan not applied: {exc.errors()[0]['msg']}")
    out["software"] = analysis
    out["note"] = "Generated spec is a draft. Review it, then Generate Plan. Nothing is deployed automatically."
    return out


def generate_stack(settings: Settings, prompt: str) -> dict:
    """Architecture draft: VMs / LXC / Docker services. Validated; nothing is deployed."""
    from . import stack_service

    def checked(raw: dict) -> dict:
        try:
            return stack_service.finalize(settings, raw)
        except stack_service.StackRejected as exc:
            raise SpecRejected(exc.errors, exc.draft) from exc

    out = _with_fallback(
        settings,
        lambda: checked(_call_claude(settings, stack_service.system_prompt(settings), prompt,
                                     stack_service.STACK_SCHEMA)),
        lambda: checked(stack_service.local_stack(settings, prompt)),
    )
    out["note"] = "Draft architecture. Edit it, then plan it: nothing is created until you deploy the reviewed plan."
    return out


# ---------------------------------------------------------------------------
# Troubleshooting
# ---------------------------------------------------------------------------

TROUBLE_SCHEMA = {
    "type": "object",
    "properties": {
        "likely_cause": {"type": "string"},
        "immediate_checks": {"type": "array", "items": {"type": "string"}},
        "safe_remediation_steps": {"type": "array", "items": {"type": "string"}},
        "recreate_appropriate": {"type": "boolean"},
        "recreate_reasoning": {"type": "string"},
        "stateful_risk": {"type": "boolean"},
        "stateful_notes": {"type": "string"},
    },
    "required": ["likely_cause", "immediate_checks", "safe_remediation_steps", "recreate_appropriate",
                 "recreate_reasoning", "stateful_risk", "stateful_notes"],
    "additionalProperties": False,
}

TROUBLE_SYSTEM = """You are an SRE helping debug a Proxmox VM deployed from a cloud-init template via
Terraform/OpenTofu. Given logs and validation output, give the most likely cause, immediate read-only
checks, and SAFE remediation steps (no destructive commands without a backup step first). Say whether
recreating the VM is appropriate (only for stateless/disposable VMs) and whether the issue may be
stateful, requiring backup/restore instead. Never recommend deleting production data."""

_RULES: list[tuple[str, dict]] = [
    (r"template .* does not exist|prepare the platform", {
        "likely_cause": "The template for this OS has not been built on the node yet.",
        "immediate_checks": ["Open the Platform panel and look for missing resources"],
        "safe_remediation_steps": ["Click Prepare Platform: OpenTofu downloads the cloud image and builds the template",
                                   "For Windows, provide the template once (docs/windows-template.md)"],
        "recreate_appropriate": False}),
    (r"ansible-playbook failed|unreachable=[1-9]|winrm|configuration failed", {
        "likely_cause": "Ansible could not finish the software configuration (VM unreachable over SSH/WinRM, "
                        "or a package/feature install failed).",
        "immediate_checks": ["Read the TASK that failed in the job log",
                             "Linux: ssh with the console key to the VM IP; Windows: Test-WSMan on port 5986",
                             "Check DNS and outbound HTTP from the VM (package mirrors, Chocolatey)"],
        "safe_remediation_steps": ["Fix the cause, then use Configure to re-run (it is idempotent)",
                                   "If the VM is disposable and the failure persists, recreate it"],
        "recreate_appropriate": False}),
    (r"401|token|authentication", {
        "likely_cause": "Proxmox API token rejected (wrong user, token ID or secret, or token expired).",
        "immediate_checks": ["Verify PROXMOX_USER uses USER@REALM format (e.g. automation@pve)",
                             "Verify PROXMOX_TOKEN_ID is the token name only (e.g. infra-demo)",
                             "Run: pveum user token list automation@pve"],
        "safe_remediation_steps": ["Regenerate the token secret and update .env", "Restart the backend container"],
        "recreate_appropriate": False}),
    (r"403|permission|privilege", {
        "likely_cause": "API token lacks a required privilege (privilege separation or missing ACL).",
        "immediate_checks": ["Run: pveum user permissions automation@pve",
                             "Check the token was created with --privsep 0, or has its own ACL entries"],
        "safe_remediation_steps": ["Assign the InfraDemo role on /vms, /storage/<pool> and /sdn or the node bridge",
                                   "Re-run the plan"],
        "recreate_appropriate": False}),
    (r"cloud-init has not completed|boot-finished|cloud_init_completed", {
        "likely_cause": "cloud-init did not finish: usually package installation failing (no DNS/Internet on the "
                        "test VLAN) or a broken user-data/vendor-data snippet.",
        "immediate_checks": ["Open the VM console in Proxmox and run: cloud-init status --long",
                             "Check /var/log/cloud-init-output.log",
                             "Verify the test VLAN has DHCP, DNS and outbound HTTP to the package mirror"],
        "safe_remediation_steps": ["Fix network/DNS on the test VLAN or the cloud-init snippet",
                                   "Recreate the TEST VM so cloud-init runs again from a clean state"],
        "recreate_appropriate": True}),
    (r"guest agent|guest_agent_ip|no ipv4", {
        "likely_cause": "QEMU guest agent is not running in the VM, or the VM got no DHCP lease.",
        "immediate_checks": ["Confirm the template has agent enabled: qm config <template-id> | grep agent",
                             "In the VM: systemctl status qemu-guest-agent",
                             "Check the DHCP server for the test VLAN"],
        "safe_remediation_steps": ["Install qemu-guest-agent in the template (virt-customize) and rebuild it",
                                   "Recreate the TEST VM"],
        "recreate_appropriate": True}),
    (r"already exists|vmid", {
        "likely_cause": "VM ID collision: a VM with the chosen ID already exists outside of Terraform state.",
        "immediate_checks": ["Run: qm list", "Compare with tofu state list for this environment"],
        "safe_remediation_steps": ["Pick a free ID in the environment range or import the existing VM into state"],
        "recreate_appropriate": False}),
    (r"timeout|timed out|cannot reach|connection refused|name or service", {
        "likely_cause": "Network path from the backend to the Proxmox API or VM is down (VPN, DNS, firewall).",
        "immediate_checks": ["curl -k https://<proxmox-host>:8006/api2/json/version from the backend host",
                             "Check VPN/DNS resolution of PROXMOX_HOST"],
        "safe_remediation_steps": ["Restore connectivity, or switch to LIVE_MODE=false for the demo"],
        "recreate_appropriate": False}),
    (r"storage|no space|datastore", {
        "likely_cause": "Target storage pool is full, missing, or does not allow VM images.",
        "immediate_checks": ["Run: pvesm status", "Check content types of the storage pool include 'images'"],
        "safe_remediation_steps": ["Free space or select another pool in .env (TEST_STORAGE/PROD_STORAGE)"],
        "recreate_appropriate": False}),
]


def _local_troubleshoot(vm_name: str, blob: str) -> dict:
    text = blob.lower()
    for pattern, result in _RULES:
        if re.search(pattern, text):
            out = {**result}
            break
    else:
        out = {"likely_cause": "No known failure signature found in the provided logs.",
               "immediate_checks": ["Read the full job log for the first error line",
                                    "Check VM status and console in the Proxmox UI"],
               "safe_remediation_steps": ["Re-run validation", "Collect logs and escalate"],
               "recreate_appropriate": False}
    stateful = bool(re.search(r"prod|database|postgres|mysql|data", f"{vm_name} {text}"))
    out["recreate_reasoning"] = ("Recreating is safe only for disposable TEST VMs where all config comes from "
                                 "cloud-init." if out["recreate_appropriate"] else
                                 "Recreating would not fix a platform/configuration problem outside the VM.")
    out["stateful_risk"] = stateful
    out["stateful_notes"] = ("The VM may hold state. Back it up (vzdump/snapshot) and prefer restore over "
                             "recreate." if stateful else "No sign of persistent data; VM appears disposable.")
    return out


def troubleshoot(settings: Settings, vm_name: str, job_logs: str, validation_output: Any,
                 proxmox_status: Any) -> dict:
    if isinstance(validation_output, dict) and isinstance(validation_output.get("tests"), list):
        # only failing checks matter; ids and passing titles would just add noise
        validation_output = {**validation_output, "tests": [
            {k: t.get(k) for k in ("title", "where", "detail")} for t in validation_output["tests"]
            if isinstance(t, dict) and not t.get("ok")]}
    blob = "\n".join([job_logs[-20000:], json.dumps(validation_output, default=str)[:10000],
                      json.dumps(proxmox_status, default=str)[:5000]])

    def ai():
        out = _call_claude(settings, TROUBLE_SYSTEM, f"VM: {vm_name}\n\n{blob}", TROUBLE_SCHEMA)
        if "prod" in vm_name or (isinstance(validation_output, dict) and validation_output.get("environment") == "prod"):
            out["stateful_risk"] = True
        return out

    return _with_fallback(settings, ai, lambda: _local_troubleshoot(vm_name, blob))
