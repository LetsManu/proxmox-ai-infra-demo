"""Can a package actually be installed? Checked against the real repositories.

  Ubuntu  packages.ubuntu.com/<suite>/<name>   ("No such package" page when missing)
  Debian  packages.debian.org/<suite>/<name>
  Windows community.chocolatey.org OData API

Results are cached. Without internet (or in mock mode, or PACKAGE_CHECK=offline)
a bundled index of common packages is used: names in it count as available,
anything else is "unverified" rather than "missing".
"""

from __future__ import annotations

import json
import os
import threading
import time

import httpx

from ..config import Settings

SUITES = {"ubuntu-24-04": ("ubuntu", "noble"), "debian-12": ("debian", "bookworm")}
_CACHE: dict[tuple[str, str], tuple[float, str]] = {}
_LOCK = threading.Lock()
TTL = 6 * 3600
_OFFLINE: dict[str, set[str]] | None = None


def _offline_index() -> dict[str, set[str]]:
    global _OFFLINE
    if _OFFLINE is None:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "package_index.json")
        with open(path, encoding="utf-8") as fh:
            _OFFLINE = {k: set(v) for k, v in json.load(fh).items()}
    return _OFFLINE


def _live(template: str, name: str) -> str:
    """'available' | 'missing'; raises httpx.HTTPError when the repository is unreachable."""
    base = name.split("=")[0]
    if template in SUITES:
        distro, suite = SUITES[template]
        host = "packages.ubuntu.com" if distro == "ubuntu" else "packages.debian.org"
        last: Exception | None = None
        for _ in range(2):  # the package sites occasionally drop the first connection
            try:
                r = httpx.get(f"https://{host}/{suite}/{base}", timeout=6, follow_redirects=True)
                if r.status_code == 404 or "No such package" in r.text:
                    return "missing"
                r.raise_for_status()
                return "available"
            except httpx.HTTPError as exc:
                last = exc
        raise last  # type: ignore[misc]
    r = httpx.get("https://community.chocolatey.org/api/v2/FindPackagesById()", params={"id": f"'{base}'"},
                  timeout=6)
    r.raise_for_status()
    return "available" if "<entry" in r.text else "missing"


def check(settings: Settings, template: str, names: list[str]) -> dict[str, dict]:
    """{name: {"status": available|missing|unverified, "source": live|offline|cache}}."""
    family_key = template if template in SUITES else "windows"
    mode = (settings.package_check or "live").lower()
    if not settings.live_mode or mode == "offline":
        mode = "offline"
    out: dict[str, dict] = {}
    for name in names:
        key = (family_key, name.split("=")[0].lower())
        if mode == "off":
            out[name] = {"status": "unverified", "source": "disabled"}
            continue
        with _LOCK:
            hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < TTL:
            out[name] = {"status": hit[1], "source": "cache"}
            continue
        if mode == "live":
            try:
                status = _live(template, name)
                with _LOCK:
                    _CACHE[key] = (time.time(), status)
                out[name] = {"status": status, "source": "live"}
                continue
            except httpx.HTTPError:
                pass  # repository unreachable: fall back to the bundled index
        known = key[1] in _offline_index().get(family_key, set())
        out[name] = {"status": "available" if known else "unverified", "source": "offline"}
    return out
