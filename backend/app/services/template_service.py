"""Maps UI template keys (e.g. `ubuntu-24-04`) to configured Proxmox template IDs."""

from __future__ import annotations

from ..config import TEMPLATE_CATALOG, Settings, template_entry
from .proxmox_service import ProxmoxError, get_proxmox


def template_id_for(settings: Settings, key: str) -> int:
    t = template_entry(key)
    if not t:
        raise ValueError(f"Unknown template '{key}'")
    return int(getattr(settings, t["setting"]))


def image_url_for(settings: Settings, key: str) -> str:
    t = template_entry(key)
    if not t:
        raise ValueError(f"Unknown template '{key}'")
    return getattr(settings, t["image_setting"]) if t["image_setting"] else ""


def os_family_for(key: str) -> str:
    t = template_entry(key)
    return t["os_family"] if t else "linux"


def list_templates(settings: Settings) -> list[dict]:
    """Configured templates, annotated with whether they exist on the Proxmox node."""
    available: set[int] | None
    error = None
    try:
        available = {t["vmid"] for t in get_proxmox(settings).list_templates()}
    except ProxmoxError as exc:
        available, error = None, str(exc)
    out = []
    for t in TEMPLATE_CATALOG:
        vmid = int(getattr(settings, t["setting"]))
        out.append({
            "key": t["key"],
            "label": t["label"],
            "os_family": t["os_family"],
            "buildable": t["buildable"],
            "template_id": vmid,
            "image_url_configured": bool(image_url_for(settings, t["key"])),
            "available": None if available is None else vmid in available,
            "error": error,
        })
    return out


def ensure_template(settings: Settings, key: str) -> int:
    vmid = template_id_for(settings, key)
    if not get_proxmox(settings).template_exists(vmid):
        t = template_entry(key)
        how = ("Prepare the platform to build it from the official cloud image."
               if t and t["buildable"] else "Provide it once, see docs/windows-template.md.")
        raise ProxmoxError(f"Template '{key}' (VMID {vmid}) does not exist on node {settings.proxmox_node}. {how}")
    return vmid
