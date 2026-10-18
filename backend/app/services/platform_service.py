"""Everything the console needs on the Proxmox side, and whether it exists.

Three owners:
  bootstrap  infra/bootstrap, run once by an admin (user, role, token, pool, storage, SDN vnets)
  platform   infra/platform, run by the console (cloud images + Linux templates)
  manual     provided once by a person (the Windows template: no redistributable image)
"""

from __future__ import annotations

import os
import re

from ..config import TEMPLATE_CATALOG, Settings
from .proxmox_service import ProxmoxError, get_proxmox
from .template_service import image_url_for
from .terraform_service import TerraformService


def _file_name(url: str, key: str) -> str:
    # content type "import" needs a disk-image extension; Ubuntu's .img is qcow2
    base = os.path.basename(url.split("?")[0]) or key
    base = re.sub(r"\.(img|qcow2|raw)$", "", base)
    return f"{base}.qcow2"


def desired_templates(settings: Settings) -> dict:
    """Templates declared in the platform stack: missing ones plus those it already manages."""
    px = get_proxmox(settings)
    managed = TerraformService(settings).platform_managed_keys()
    out = {}
    for t in TEMPLATE_CATALOG:
        if not t["buildable"]:
            continue
        vmid = int(getattr(settings, t["setting"]))
        url = image_url_for(settings, t["key"])
        if not url:
            continue
        if t["key"] in managed or not px.template_exists(vmid):
            out[t["key"]] = {"vm_id": vmid, "name": f"tmpl-{t['key']}", "image_url": url,
                             "file_name": _file_name(url, t["key"])}
    return out


def status(settings: Settings) -> dict:
    px = get_proxmox(settings)
    try:
        templates = {t["vmid"] for t in px.list_templates()}
        storages = {s["storage"] for s in px.list_storage()}
        bridges = {b["iface"] for b in px.list_bridges()} | set(px.list_vnets())
        pools = set(px.list_pools()) if settings.pool_id else set()
        reachable, error = True, None
    except ProxmoxError as exc:
        templates, storages, bridges, pools = set(), set(), set(), set()
        reachable, error = False, str(exc)

    def item(kind, name, present, owner, detail=""):
        state = "unknown" if not reachable else ("present" if present else "missing")
        return {"kind": kind, "name": name, "status": state, "owner": owner, "detail": detail}

    resources = []
    for env, bridge, vlan in (("Test", settings.test_bridge, settings.test_vlan),
                              ("Production", settings.prod_bridge, settings.prod_vlan)):
        resources.append(item("Network", bridge, bridge in bridges, "bootstrap",
                              f"{env}{f' · VLAN {vlan}' if vlan else ''}"))
    for name in sorted({settings.test_storage, settings.prod_storage, settings.template_storage}):
        resources.append(item("Storage", name, name in storages, "bootstrap", "VM disks"))
    resources.append(item("Storage", settings.image_storage, settings.image_storage in storages, "bootstrap",
                          "Cloud images (content: import)"))
    if settings.pool_id:
        resources.append(item("Pool", settings.pool_id, settings.pool_id in pools, "bootstrap", "Groups managed VMs"))
    for t in TEMPLATE_CATALOG:
        vmid = int(getattr(settings, t["setting"]))
        resources.append(item("Template", f"{vmid} ({t['label']})", vmid in templates,
                              "platform" if t["buildable"] else "manual",
                              ("Built from the official cloud image" if image_url_for(settings, t["key"])
                               else f"Set {t['image_setting'].upper()} to build it") if t["buildable"]
                              else "Provide once: docs/windows-template.md"))

    buildable_missing = [r for r in resources if r["owner"] == "platform" and r["status"] == "missing"]
    blocking = [r for r in resources if r["owner"] == "bootstrap" and r["status"] == "missing"]
    return {
        "reachable": reachable,
        "error": error,
        "resources": resources,
        "ready": reachable and not buildable_missing and not blocking,
        "needs_platform_apply": bool(buildable_missing),
        "needs_bootstrap": bool(blocking),
    }
