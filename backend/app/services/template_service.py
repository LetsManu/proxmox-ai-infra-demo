"""Maps UI template keys (e.g. `ubuntu-24-04`) to configured Proxmox template IDs."""

from __future__ import annotations

from ..config import CT_CATALOG, TEMPLATE_CATALOG, Settings, ct_entry, ct_storage, ct_volume_id, template_entry
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
            "kind": "vm",
            "label": t["label"],
            "os_family": t["os_family"],
            "buildable": t["buildable"],
            "template_id": vmid,
            "image_url_configured": bool(image_url_for(settings, t["key"])),
            "available": None if available is None else vmid in available,
            "error": error,
        })
    try:
        have_ct = get_proxmox(settings).list_ct_templates(ct_storage(settings)) if available is not None else None
    except ProxmoxError:
        have_ct = None
    for c in CT_CATALOG:
        configured = bool(getattr(settings, c["url_setting"]))
        out.append({"key": c["key"], "kind": "lxc", "label": c["label"], "os_family": "linux", "buildable": True,
                    "template_id": None, "image_url_configured": configured,
                    "available": None if have_ct is None else configured and ct_volume_id(settings, c["key"]) in have_ct,
                    "error": error})
    return out


def ensure_ct_template(settings: Settings, key: str) -> str:
    c = ct_entry(key)
    if not c:
        raise ValueError(f"Unknown LXC template '{key}'")
    if not getattr(settings, c["url_setting"]):
        raise ProxmoxError(f"LXC template '{key}' is not configured. Set {c['url_setting'].upper()}, "
                           "then prepare the platform.")
    volid = ct_volume_id(settings, key)
    if volid not in get_proxmox(settings).list_ct_templates(ct_storage(settings)):
        raise ProxmoxError(f"LXC template '{key}' ({volid}) does not exist on node {settings.proxmox_node}. "
                           "Prepare the platform to download it.")
    return volid


def ensure_template(settings: Settings, key: str) -> int:
    vmid = template_id_for(settings, key)
    if not get_proxmox(settings).template_exists(vmid):
        t = template_entry(key)
        how = ("Prepare the platform to build it from the official cloud image."
               if t and t["buildable"] else "Provide it once, see docs/windows-template.md.")
        raise ProxmoxError(f"Template '{key}' (VMID {vmid}) does not exist on node {settings.proxmox_node}. {how}")
    return vmid
