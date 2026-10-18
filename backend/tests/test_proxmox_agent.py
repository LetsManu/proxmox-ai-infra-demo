"""Parsing of QEMU guest agent answers as Proxmox passes them through ({"result": ...})."""

from app.services.proxmox_service import ProxmoxClient


def _client(answer):
    px = ProxmoxClient.__new__(ProxmoxClient)
    px.node = "pve"
    px.get = lambda path, **params: answer
    return px


def _iface(name, *addrs):
    return {"name": name, "hardware-address": "00:00:00:00:00:00",
            "ip-addresses": [{"ip-address-type": t, "ip-address": a, "prefix": 16 if t == "ipv4" else 64}
                             for t, a in addrs]}


def test_windows_apipa_before_dhcp_is_not_an_address():
    # Windows reports a link-local address until DHCP answers; validation must keep waiting
    answer = {"result": [_iface("Ethernet", ("ipv6", "fe80::1"), ("ipv4", "169.254.12.34")),
                         _iface("Loopback Pseudo-Interface 1", ("ipv6", "::1"), ("ipv4", "127.0.0.1"))]}
    assert _client(answer).guest_ips(950) == []


def test_windows_dhcp_address_is_used():
    answer = {"result": [_iface("Ethernet", ("ipv6", "fe80::1"), ("ipv4", "192.0.2.15")),
                         _iface("Loopback Pseudo-Interface 1", ("ipv4", "127.0.0.1"))]}
    assert _client(answer).guest_ips(950) == ["192.0.2.15"]


def test_lxc_interfaces_skip_loopback_and_link_local():
    answer = [{"name": "lo", "inet": "127.0.0.1/8"}, {"name": "eth0", "inet": "169.254.1.1/16"},
              {"name": "eth1", "inet": "192.0.2.20/24"}]
    assert _client(answer).guest_ips(950, "lxc") == ["192.0.2.20"]


class _FakeWindowsPx:
    """Running Windows VM whose guest agent already answers (cloudbase-init may still be running)."""

    def vm_status(self, vmid, kind="vm"):
        return {"status": "running", "uptime": 60}

    def guest_ips(self, vmid, kind="vm"):
        return ["192.0.2.15"]

    def guest_os(self, vmid):
        return "Windows Server 2022 Standard Evaluation"


def _validate_windows(monkeypatch, winrm_open: bool):
    from app.config import get_settings
    from app.services import validation_service as vs

    monkeypatch.setattr(vs, "get_proxmox", lambda settings: _FakeWindowsPx())
    monkeypatch.setattr(vs, "_service_check", lambda ip, port, path: (winrm_open, f"tcp://{ip}:{port}"))
    monkeypatch.setattr(vs.time, "sleep", lambda s: None)
    settings = get_settings().model_copy(update={"validation_timeout_seconds": 0})
    result = vs.validate_vm(settings, vmid=950, env="test", health_check_port=None, health_check_path=None,
                            simulate_failure=False, log=lambda line: None, os_family="windows")
    return {c["name"]: c for c in result["checks"]}


def test_windows_is_not_ready_while_winrm_is_closed(monkeypatch):
    check = _validate_windows(monkeypatch, winrm_open=False)["cloud_init_completed"]
    assert not check["ok"] and "5986" in check["detail"]


def test_windows_is_ready_once_winrm_answers(monkeypatch):
    check = _validate_windows(monkeypatch, winrm_open=True)["cloud_init_completed"]
    assert check["ok"]
