"""Terraform / OpenTofu execution.

Each environment has its own state file, data dir and plan directory under
WORKSPACE_DIR, so TEST and PRODUCTION never share state:

    /workspace/test/{src,.terraform,plans}   /workspace/state/test/terraform.tfstate
    /workspace/prod/{src,.terraform,plans}   /workspace/state/prod/terraform.tfstate

The desired VMs for an environment are rendered into `var.vms` from the
database. Proxmox credentials are passed to the provider via environment
variables only (PROXMOX_VE_ENDPOINT / PROXMOX_VE_API_TOKEN) and never written
to disk.

In mock mode the same interface returns realistic, deterministic plan/apply
output without executing anything.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable

from ..config import ENVIRONMENTS, Settings, placement

Log = Callable[[str], None]

RESOURCE = "proxmox_virtual_environment_vm"


def address(name: str) -> str:
    return f'module.vm["{name}"].{RESOURCE}.this'


@dataclass
class PlanResult:
    text: str
    changes: list[dict] = field(default_factory=list)  # [{address, name, action}]
    plan_file: str | None = None

    @property
    def counts(self) -> dict:
        c = {"create": 0, "update": 0, "destroy": 0}
        for ch in self.changes:
            if ch["action"] in ("create", "replace"):
                c["create"] += 1
            if ch["action"] in ("destroy", "replace"):
                c["destroy"] += 1
            if ch["action"] == "update":
                c["update"] += 1
        return c

    @property
    def has_destroy(self) -> bool:
        return any(ch["action"] in ("destroy", "replace") for ch in self.changes)

    @property
    def summary_line(self) -> str:
        c = self.counts
        return f"Plan: {c['create']} to add, {c['update']} to change, {c['destroy']} to destroy."

    def to_dict(self) -> dict:
        return {"text": self.text, "changes": self.changes, "counts": self.counts,
                "has_destroy": self.has_destroy, "summary": self.summary_line, "plan_file": self.plan_file}


def vm_entry(spec: dict, vmid: int, template_id: int) -> dict:
    """Shape of one element of `var.vms` (see infra/variables.tf)."""
    ci = spec.get("cloud_init") or {}
    return {
        "vm_id": vmid,
        "template_id": template_id,
        "cores": spec["cores"],
        "memory_mb": spec["memory_mb"],
        "disk_gb": spec["disk_gb"],
        "description": spec.get("description") or "",
        "ssh_public_key": spec.get("ssh_public_key") or "",
        "tags": spec.get("tags") or [],
        "packages": ci.get("packages") or [],
        "commands": ci.get("commands") or [],
    }


class TerraformService:
    def __init__(self, settings: Settings):
        self.s = settings

    # -- paths ----------------------------------------------------------------
    def env_dir(self, env: str) -> str:
        return os.path.join(self.s.workspace_dir, env)

    def state_path(self, env: str) -> str:
        return os.path.join(self.s.workspace_dir, "state", env, "terraform.tfstate")

    def _prepare(self, env: str) -> str:
        src = os.path.join(self.env_dir(env), "src")
        os.makedirs(os.path.dirname(self.state_path(env)), exist_ok=True)
        os.makedirs(os.path.join(self.env_dir(env), "plans"), exist_ok=True)
        shutil.copytree(self.s.infra_dir, src, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".terraform", "*.tfstate*", "*.tfplan"))
        return src

    def _env(self, env: str) -> dict:
        e = dict(os.environ)
        e.update({
            "TF_IN_AUTOMATION": "1",
            "TF_INPUT": "0",
            "TF_DATA_DIR": os.path.join(self.env_dir(env), ".terraform"),
            "PROXMOX_VE_ENDPOINT": f"https://{self.s.proxmox_host}:{self.s.proxmox_port}/",
            "PROXMOX_VE_API_TOKEN": (f"{self.s.proxmox_user}!{self.s.proxmox_token_id}="
                                     f"{self.s.proxmox_token_secret.get_secret_value()}"),
            "PROXMOX_VE_INSECURE": "false" if self.s.proxmox_verify_ssl else "true",
        })
        if os.path.isdir("/opt/tofu-plugin-cache"):
            e.setdefault("TF_PLUGIN_CACHE_DIR", "/opt/tofu-plugin-cache")
        return e

    def _scrub(self, line: str) -> str:
        secret = self.s.proxmox_token_secret.get_secret_value()
        return line.replace(secret, "***") if secret else line

    def _run(self, args: list[str], env: str, cwd: str, log: Log, capture: bool = False) -> str:
        cmd = [self.s.iac_binary, *args]
        log(f"$ {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, cwd=cwd, env=self._env(env), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        out = []
        assert proc.stdout is not None
        for line in proc.stdout:
            line = self._scrub(line.rstrip("\n"))
            out.append(line)
            if not capture:
                log(line)
        rc = proc.wait()
        if rc != 0:
            if capture:
                for line in out[-40:]:
                    log(line)
            raise RuntimeError(f"{self.s.iac_binary} {args[0]} failed with exit code {rc}")
        return "\n".join(out)

    def _var_args(self, env: str, vms: dict) -> list[str]:
        p = placement(self.s, env)
        generated = {
            "node_name": self.s.proxmox_node,
            "datastore_id": p["storage"],
            "bridge": p["bridge"],
            "vlan_id": p["vlan"],
            "ci_user": self.s.ci_user,
            "default_ssh_public_key": self.s.default_ssh_public_key,
            "snippets_datastore_id": self.s.snippets_datastore,
            "vms": vms,
        }
        path = os.path.join(self.env_dir(env), "generated.tfvars.json")
        with open(path, "w") as fh:
            json.dump(generated, fh, indent=2)
        return [f"-var-file=environments/{env}.tfvars", f"-var-file={path}"]

    # -- public API -----------------------------------------------------------
    def plan(self, env: str, vms: dict, job_id: str, log: Log, replace: list[str] | None = None,
             current: dict | None = None) -> PlanResult:
        if not self.s.live_mode:
            return mock_plan(env, vms, current or {}, replace or [], self.s, log)
        src = self._prepare(env)
        self._run(["init", "-input=false", "-no-color", "-reconfigure",
                   f"-backend-config=path={self.state_path(env)}"], env, src, log)
        plan_file = os.path.join(self.env_dir(env), "plans", f"{job_id}.tfplan")
        args = ["plan", "-input=false", "-no-color", *self._var_args(env, vms), f"-out={plan_file}"]
        args += [f"-replace={address(n)}" for n in (replace or [])]
        text = self._run(args, env, src, log)
        shown = json.loads(self._run(["show", "-json", plan_file], env, src, log, capture=True))
        changes = []
        for rc in shown.get("resource_changes", []):
            actions = rc["change"]["actions"]
            if actions == ["no-op"] or actions == ["read"]:
                continue
            action = ("replace" if set(actions) == {"delete", "create"} else
                      {"create": "create", "update": "update", "delete": "destroy"}.get(actions[0], actions[0]))
            addr = rc["address"]
            name = addr.split('"')[1] if '"' in addr else addr
            changes.append({"address": addr, "name": name, "action": action})
        return PlanResult(text=text, changes=changes, plan_file=plan_file)

    def apply(self, env: str, plan: dict, log: Log) -> dict:
        if not self.s.live_mode:
            return mock_apply(env, plan, self.s, log)
        src = self._prepare(env)
        if not plan.get("plan_file") or not os.path.exists(plan["plan_file"]):
            raise RuntimeError("Reviewed plan file is missing; generate a new plan.")
        self._run(["apply", "-input=false", "-no-color", plan["plan_file"]], env, src, log)
        outputs = json.loads(self._run(["output", "-json"], env, src, log, capture=True) or "{}")
        return {k: v.get("value") for k, v in outputs.items()}


# ----------------------------------------------------------------------------
# Mock implementation
# ----------------------------------------------------------------------------

def _hcl_list(values: list[str]) -> str:
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


def _render_create(name: str, e: dict, env: str, s: Settings, sign: str = "+") -> list[str]:
    p = placement(s, env)
    full = ENVIRONMENTS[env].full_clone
    tags = sorted({"managed-by-iac", env, *e["tags"]})
    lines = [
        f'  {sign} resource "{RESOURCE}" "this" {{',
        f'      + id          = (known after apply)',
        f'      + name        = "{name}"',
        f'      + node_name   = "{s.proxmox_node}"',
        f'      + vm_id       = {e["vm_id"]}',
        f'      + description = "{e["description"]}"',
        f'      + tags        = {_hcl_list(tags)}',
        f'      + on_boot     = {"true" if env == "prod" else "false"}',
        f'      + started     = true',
        f'      + ipv4_addresses = (known after apply)',
        '',
        '      + agent {',
        '          + enabled = true',
        '        }',
        '      + clone {',
        f'          + vm_id = {e["template_id"]}',
        f'          + full  = {"true" if full else "false"}',
        '        }',
        '      + cpu {',
        f'          + cores = {e["cores"]}',
        '          + type  = "x86-64-v2-AES"',
        '        }',
        '      + memory {',
        f'          + dedicated = {e["memory_mb"]}',
        '        }',
        '      + disk {',
        f'          + datastore_id = "{p["storage"]}"',
        '          + interface    = "scsi0"',
        f'          + size         = {e["disk_gb"]}',
        '        }',
        '      + network_device {',
        f'          + bridge  = "{p["bridge"]}"',
        f'          + vlan_id = {p["vlan"]}',
        '        }',
        '      + initialization {',
        '          + ip_config {',
        '              + ipv4 {',
        '                  + address = "dhcp"',
        '                }',
        '            }',
        '          + user_account {',
        f'              + username = "{s.ci_user}"',
        '              + keys     = (sensitive value)',
        '            }',
        '        }',
        '    }',
    ]
    return lines


def _diff_fields(old: dict, new: dict) -> list[tuple[str, object, object]]:
    keys = [("cores", "cpu.cores"), ("memory_mb", "memory.dedicated"), ("disk_gb", "disk.size"),
            ("description", "description"), ("tags", "tags")]
    return [(label, old.get(k), new.get(k)) for k, label in keys if old.get(k) != new.get(k)]


def mock_plan(env: str, desired: dict, current: dict, replace: list[str], s: Settings, log: Log) -> PlanResult:
    tool = "OpenTofu" if s.iac_binary == "tofu" else "Terraform"
    log(f"[mock] {s.iac_binary} init -backend-config=path=/workspace/state/{env}/terraform.tfstate")
    log(f"[mock] {s.iac_binary} plan -var-file=environments/{env}.tfvars -out={env}.tfplan")
    time.sleep(0.6 / max(s.mock_speed, 0.01))
    changes, body = [], []
    symbols: set[str] = set()
    for name in sorted(set(desired) | set(current)):
        new, old = desired.get(name), current.get(name)
        addr = address(name)
        vmid = (new or old)["vm_id"]
        if new and not old:
            changes.append({"address": addr, "name": name, "action": "create", "vm_id": vmid})
            symbols.add("+")
            body += [f"  # {addr} will be created", *_render_create(name, new, env, s), ""]
        elif old and not new:
            changes.append({"address": addr, "name": name, "action": "destroy", "vm_id": vmid})
            symbols.add("-")
            body += [f"  # {addr} will be destroyed",
                     f'  - resource "{RESOURCE}" "this" {{',
                     f'      - name  = "{name}" -> null',
                     f'      - vm_id = {old["vm_id"]} -> null',
                     "    }", ""]
        elif new and old:
            forced = (name in replace or new["template_id"] != old["template_id"]
                      or new["vm_id"] != old["vm_id"] or new["disk_gb"] < old["disk_gb"])
            if forced:
                changes.append({"address": addr, "name": name, "action": "replace", "vm_id": vmid})
                symbols.add("-/+")
                reason = "as requested" if name in replace else "because a forcing attribute changed"
                body += [f"  # {addr} will be replaced, {reason}",
                         *_render_create(name, new, env, s, sign="-/+"), ""]
            elif diffs := _diff_fields(old, new):
                changes.append({"address": addr, "name": name, "action": "update", "vm_id": vmid})
                symbols.add("~")
                body += [f"  # {addr} will be updated in-place",
                         f'  ~ resource "{RESOURCE}" "this" {{',
                         f'        id   = "{old["vm_id"]}"',
                         f'        name = "{name}"']
                body += [f"      ~ {label} = {json.dumps(a)} -> {json.dumps(b)}" for label, a, b in diffs]
                body += ["    }", ""]
    header = [f"{tool} used the selected providers to generate the following execution",
              "plan. Resource actions are indicated with the following symbols:"]
    legend = {"+": "  + create", "~": "  ~ update in-place", "-": "  - destroy",
              "-/+": "-/+ destroy and then create replacement"}
    header += [legend[k] for k in ("+", "~", "-", "-/+") if k in symbols]
    if not changes:
        text = f"No changes. Your infrastructure matches the configuration.\n\n{tool} has compared your real infrastructure against your configuration and found no differences, so no changes are needed."
    else:
        text = "\n".join([*header, "", f"{tool} will perform the following actions:", "", *body])
        pr = PlanResult(text="", changes=changes)
        text += pr.summary_line
    for line in text.splitlines():
        log(line)
    return PlanResult(text=text, changes=changes, plan_file=f"mock://{env}")


def mock_apply(env: str, plan: dict, s: Settings, log: Log) -> dict:
    delay = 0.35 / max(s.mock_speed, 0.01)
    added = changed = destroyed = 0
    for ch in plan.get("changes", []):
        addr, action = ch["address"], ch["action"]
        if action in ("destroy", "replace"):
            log(f"{addr}: Destroying... [id={ch.get('vm_id', '?')}]")
            time.sleep(delay)
            log(f"{addr}: Destruction complete after 6s")
            destroyed += 1
        if action in ("create", "replace"):
            log(f"{addr}: Creating...")
            for sec in (10, 20, 30):
                time.sleep(delay)
                log(f"{addr}: Still creating... [{sec}s elapsed]")
            log(f"{addr}: Creation complete after 38s [id={ch.get('vm_id', '?')}]")
            added += 1
        if action == "update":
            log(f"{addr}: Modifying... [id={ch.get('vm_id', '?')}]")
            time.sleep(delay)
            log(f"{addr}: Modifications complete after 4s")
            changed += 1
    log("")
    log(f"Apply complete! Resources: {added} added, {changed} changed, {destroyed} destroyed.")
    return {}
