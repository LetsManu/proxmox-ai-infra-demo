"""Proxmox VE API access (token auth) plus an in-memory mock with the same interface.

Only the backend talks to Proxmox. The token is sent as
`Authorization: PVEAPIToken=USER@REALM!TOKENID=SECRET` and is never returned to
callers or written to logs.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any

import httpx

from ..config import Settings, get_settings


class ProxmoxError(RuntimeError):
    pass


class ProxmoxClient:
    """Thin wrapper around the Proxmox VE REST API."""

    def __init__(self, settings: Settings):
        self.s = settings
        self.node = settings.proxmox_node
        self._client = httpx.Client(
            base_url=settings.proxmox_base_url,
            headers={"Authorization": settings.proxmox_token_header},
            verify=settings.proxmox_verify_ssl,
            timeout=settings.proxmox_timeout_seconds,
        )

    # -- low level ----------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ProxmoxError(f"Cannot reach Proxmox API at {self.s.proxmox_host}:{self.s.proxmox_port}: {exc}") from exc
        if resp.status_code == 401:
            raise ProxmoxError("Proxmox rejected the API token (401). Check PROXMOX_USER/TOKEN_ID/TOKEN_SECRET.")
        if resp.status_code == 403:
            raise ProxmoxError(f"Permission denied (403) for {method} {path}. Check the token's role/ACL.")
        if resp.status_code >= 400:
            raise ProxmoxError(f"Proxmox API {method} {path} failed: {resp.status_code} {resp.text[:300]}")
        return resp.json().get("data")

    def get(self, path: str, **params) -> Any:
        return self._request("GET", path, params=params or None)

    def post(self, path: str, data: dict | None = None) -> Any:
        return self._request("POST", path, data=data or {})

    def put(self, path: str, data: dict | None = None) -> Any:
        return self._request("PUT", path, data=data or {})

    def delete(self, path: str, **params) -> Any:
        return self._request("DELETE", path, params=params or None)

    def wait_task(self, upid: str, timeout: int = 600) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = self.get(f"/nodes/{self.node}/tasks/{upid}/status")
            if st and st.get("status") == "stopped":
                if st.get("exitstatus") != "OK":
                    raise ProxmoxError(f"Task {upid} failed: {st.get('exitstatus')}")
                return
            time.sleep(2)
        raise ProxmoxError(f"Task {upid} timed out")

    # -- inventory ----------------------------------------------------------
    def version(self) -> dict:
        return self.get("/version")

    def list_nodes(self) -> list[dict]:
        return [{"node": n["node"], "status": n.get("status"), "cpu": n.get("cpu"), "maxmem": n.get("maxmem")}
                for n in self.get("/nodes")]

    def list_storage(self) -> list[dict]:
        return [{"storage": s["storage"], "type": s.get("type"), "content": s.get("content"),
                 "avail": s.get("avail"), "total": s.get("total")}
                for s in self.get(f"/nodes/{self.node}/storage")]

    def list_bridges(self) -> list[dict]:
        return [{"iface": n["iface"], "type": n.get("type"), "comments": n.get("comments", "")}
                for n in self.get(f"/nodes/{self.node}/network", type="any_bridge")]

    def list_vms(self) -> list[dict]:
        return self.get("/cluster/resources", type="vm") or []

    def list_templates(self) -> list[dict]:
        return [{"vmid": v["vmid"], "name": v.get("name"), "node": v.get("node")}
                for v in self.list_vms() if v.get("template") == 1 and v.get("type") == "qemu"]

    def template_exists(self, vmid: int) -> bool:
        return any(t["vmid"] == vmid for t in self.list_templates())

    def used_vmids(self) -> set[int]:
        return {int(v["vmid"]) for v in self.list_vms()}

    # -- lifecycle ----------------------------------------------------------
    def clone_vm(self, template_id: int, new_id: int, name: str, full: bool, storage: str | None = None) -> None:
        data: dict[str, Any] = {"newid": new_id, "name": name, "full": int(full)}
        if full and storage:
            data["storage"] = storage
        self.wait_task(self.post(f"/nodes/{self.node}/qemu/{template_id}/clone", data))

    def start_vm(self, vmid: int) -> None:
        self.wait_task(self.post(f"/nodes/{self.node}/qemu/{vmid}/status/start"))

    def stop_vm(self, vmid: int) -> None:
        self.wait_task(self.post(f"/nodes/{self.node}/qemu/{vmid}/status/stop"))

    def delete_vm(self, vmid: int) -> None:
        self.wait_task(self.delete(f"/nodes/{self.node}/qemu/{vmid}", purge=1))

    def vm_status(self, vmid: int) -> dict:
        st = self.get(f"/nodes/{self.node}/qemu/{vmid}/status/current")
        return {"status": st.get("status"), "uptime": st.get("uptime"), "agent": st.get("agent"),
                "name": st.get("name"), "qmpstatus": st.get("qmpstatus")}

    def guest_ips(self, vmid: int) -> list[str]:
        """IPv4 addresses reported by the QEMU guest agent (excluding loopback)."""
        data = self.get(f"/nodes/{self.node}/qemu/{vmid}/agent/network-get-interfaces")
        ips = []
        for iface in (data or {}).get("result", []):
            if iface.get("name") == "lo":
                continue
            for addr in iface.get("ip-addresses", []):
                if addr.get("ip-address-type") == "ipv4" and not addr["ip-address"].startswith("127."):
                    ips.append(addr["ip-address"])
        return ips

    def cloud_init_done(self, vmid: int) -> bool:
        """cloud-init writes /var/lib/cloud/instance/boot-finished when all stages complete."""
        try:
            self.get(f"/nodes/{self.node}/qemu/{vmid}/agent/file-read",
                     file="/var/lib/cloud/instance/boot-finished")
            return True
        except ProxmoxError:
            return False

    def guest_os(self, vmid: int) -> str | None:
        """Guest OS name reported by the agent (used for Windows readiness)."""
        try:
            info = self.get(f"/nodes/{self.node}/qemu/{vmid}/agent/get-osinfo") or {}
            return (info.get("result") or {}).get("pretty-name") or "unknown"
        except ProxmoxError:
            return None

    def list_pools(self) -> list[str]:
        return [p["poolid"] for p in self.get("/pools") or []]

    def list_vnets(self) -> list[str]:
        try:
            return [v["vnet"] for v in self.get("/cluster/sdn/vnets") or []]
        except ProxmoxError:
            return []  # SDN not configured or no SDN.Audit


class MockProxmox:
    """Simulated Proxmox for demo mode. Behaviour mirrors ProxmoxClient."""

    _lock = threading.Lock()

    def __init__(self, settings: Settings):
        self.s = settings
        self.node = settings.proxmox_node
        self.vms: dict[int, dict] = {}
        # The Windows template is "provided once" by an admin, so it exists from the start.
        # Linux templates are built by the platform stack unless MOCK_PLATFORM_READY=true.
        self.templates = {settings.template_windows_2022_id: "tmpl-windows-2022"}
        self.templates.update(self._load_built())
        if settings.mock_platform_ready:
            self.templates.update({
                settings.template_ubuntu_2404_id: "tmpl-ubuntu-24-04",
                settings.template_debian_12_id: "tmpl-debian-12",
            })

    def version(self) -> dict:
        return {"version": "8.4.1", "release": "8.4", "repoid": "mock"}

    def list_nodes(self) -> list[dict]:
        return [{"node": self.node, "status": "online", "cpu": 0.07, "maxmem": 68_719_476_736}]

    def list_storage(self) -> list[dict]:
        return [
            {"storage": "local", "type": "dir", "content": "iso,vztmpl,import,snippets,backup",
             "avail": 80 * 2**30, "total": 100 * 2**30},
            {"storage": "local-lvm", "type": "lvmthin", "content": "images,rootdir",
             "avail": 700 * 2**30, "total": 900 * 2**30},
        ] + ([{"storage": self.s.image_storage, "type": "dir", "content": "import,iso,snippets",
               "avail": 90 * 2**30, "total": 100 * 2**30}] if self.s.image_storage not in ("local", "local-lvm") else [])

    def list_bridges(self) -> list[dict]:
        return [{"iface": "vmbr0", "type": "bridge", "comments": "VLAN-aware: 10=prod, 30=test"}]

    def list_pools(self) -> list[str]:
        return [self.s.pool_id] if self.s.pool_id else []

    def list_vnets(self) -> list[str]:
        return [b for b in (self.s.test_bridge, self.s.prod_bridge) if b.startswith("v") and b != "vmbr0"]

    # Templates "built" by the mock platform stack survive restarts (like real ones would).
    def _built_file(self) -> str:
        import os

        return os.path.join(self.s.workspace_dir, "state", "platform", "mock-templates.json")

    def _load_built(self) -> dict[int, str]:
        import json

        try:
            with open(self._built_file()) as fh:
                return {int(k): v for k, v in json.load(fh).items()}
        except (OSError, ValueError):
            return {}

    def add_template(self, vmid: int, name: str) -> None:
        import json
        import os

        self.templates[vmid] = name
        built = self._load_built()
        built[vmid] = name
        os.makedirs(os.path.dirname(self._built_file()), exist_ok=True)
        with open(self._built_file(), "w") as fh:
            json.dump(built, fh)

    def list_vms(self) -> list[dict]:
        rows = [{"vmid": k, "name": v, "template": 1, "type": "qemu", "node": self.node}
                for k, v in self.templates.items()]
        rows += [{"vmid": k, "name": v["name"], "template": 0, "type": "qemu", "node": self.node,
                  "status": v["status"]} for k, v in self.vms.items()]
        return rows

    def list_templates(self) -> list[dict]:
        return [{"vmid": k, "name": v, "node": self.node} for k, v in self.templates.items()]

    def template_exists(self, vmid: int) -> bool:
        return vmid in self.templates

    def used_vmids(self) -> set[int]:
        return set(self.templates) | set(self.vms)

    def register_vm(self, vmid: int, name: str, env: str, fail: bool = False, windows: bool = False) -> None:
        net = "192.0.2" if env == "test" else "198.51.100"  # RFC 5737 documentation ranges
        with self._lock:
            self.vms[vmid] = {"name": name, "status": "running", "started": time.time(),
                              "ip": f"{net}.{random.randint(20, 220)}", "fail": fail, "windows": windows}

    def clone_vm(self, template_id: int, new_id: int, name: str, full: bool, storage: str | None = None) -> None:
        self.register_vm(new_id, name, "test")

    def start_vm(self, vmid: int) -> None:
        self.vms.setdefault(vmid, {"name": f"vm-{vmid}", "ip": "192.0.2.50", "fail": False})
        self.vms[vmid].update(status="running", started=time.time())

    def stop_vm(self, vmid: int) -> None:
        if vmid in self.vms:
            self.vms[vmid]["status"] = "stopped"

    def delete_vm(self, vmid: int) -> None:
        self.vms.pop(vmid, None)

    def vm_status(self, vmid: int) -> dict:
        vm = self.vms.get(vmid)
        if not vm:
            raise ProxmoxError(f"VM {vmid} does not exist on node {self.node}")
        uptime = int(time.time() - vm.get("started", time.time())) if vm["status"] == "running" else 0
        return {"status": vm["status"], "uptime": uptime, "agent": 1, "name": vm["name"],
                "qmpstatus": vm["status"]}

    def guest_ips(self, vmid: int) -> list[str]:
        vm = self.vms.get(vmid)
        if not vm or vm["status"] != "running":
            raise ProxmoxError("QEMU guest agent is not running")
        return [vm["ip"]]

    def cloud_init_done(self, vmid: int) -> bool:
        vm = self.vms.get(vmid)
        return bool(vm and vm["status"] == "running" and not vm.get("fail"))

    def guest_os(self, vmid: int) -> str | None:
        vm = self.vms.get(vmid)
        if not vm or vm["status"] != "running":
            return None
        return "Microsoft Windows Server 2022 Standard" if vm.get("windows") else "Ubuntu 24.04 LTS"

    def set_failure(self, vmid: int, fail: bool) -> None:
        if vmid in self.vms:
            self.vms[vmid]["fail"] = fail


_mock_singleton: MockProxmox | None = None


def get_proxmox(settings: Settings | None = None):
    """Return the live client or the shared mock depending on LIVE_MODE."""
    global _mock_singleton
    settings = settings or get_settings()
    if settings.live_mode:
        return ProxmoxClient(settings)
    if _mock_singleton is None:
        _mock_singleton = MockProxmox(settings)
    return _mock_singleton


def find_free_vmid(used: set[int], vmid_min: int, vmid_max: int) -> int:
    for vmid in range(vmid_min, vmid_max + 1):
        if vmid not in used:
            return vmid
    raise ProxmoxError(f"No free VM ID in range {vmid_min}-{vmid_max}")
