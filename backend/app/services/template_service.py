"""Maps UI template keys (e.g. `ubuntu-24-04`) to configured Proxmox template IDs."""

from __future__ import annotations

from ..config import TEMPLATE_CATALOG, Settings
from .proxmox_service import ProxmoxError, get_proxmox


def template_id_for(settings: Settings, key: str) -> int:
    for t in TEMPLATE_CATALOG:
        if t["key"] == key:
            return int(getattr(settings, t["setting"]))
    raise ValueError(f"Unknown template '{key}'")


def image_url_for(settings: Settings, key: str) -> str:
    for t in TEMPLATE_CATALOG:
        if t["key"] == key:
            return getattr(settings, t["image_setting"])
    raise ValueError(f"Unknown template '{key}'")


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
            "template_id": vmid,
            "image_url_configured": bool(getattr(settings, t["image_setting"])),
            "available": None if available is None else vmid in available,
            "error": error,
        })
    return out


def ensure_template(settings: Settings, key: str) -> int:
    vmid = template_id_for(settings, key)
    if not get_proxmox(settings).template_exists(vmid):
        raise ProxmoxError(
            f"Template '{key}' (VMID {vmid}) not found on node {settings.proxmox_node}. "
            "Run infra/scripts/create-cloudinit-template.sh first."
        )
    return vmid
