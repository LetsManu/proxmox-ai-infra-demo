"""Application configuration.

Every value comes from environment variables (normally loaded from `.env` by
Docker Compose). Nothing secret has a default, and the Proxmox token secret is
never serialised into any API response.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Mode -------------------------------------------------------------
    live_mode: bool = False
    app_user: str = "demo-operator"
    cors_origins: str = "http://localhost:8080,http://localhost:5173"

    # --- Persistence ------------------------------------------------------
    database_url: str = "sqlite:////data/app.db"
    workspace_dir: str = "/workspace"
    infra_dir: str = "/app/infra"
    iac_binary: str = "tofu"  # "tofu" or "terraform"

    # --- Proxmox API (token auth only) ------------------------------------
    proxmox_host: str = "pve.example.internal"
    proxmox_port: int = 8006
    proxmox_user: str = "automation@pve"
    proxmox_token_id: str = "infra-demo"
    proxmox_token_secret: SecretStr = SecretStr("")
    proxmox_verify_ssl: bool = True
    proxmox_node: str = "pve"
    proxmox_timeout_seconds: float = 15.0

    # --- Placement per environment ---------------------------------------
    test_storage: str = "local-lvm"
    test_bridge: str = "vmbr0"
    test_vlan: int = 30
    prod_storage: str = "local-lvm"
    prod_bridge: str = "vmbr0"
    prod_vlan: int = 10
    snippets_datastore: str = ""  # optional; enables cloud-init vendor data (guest agent, packages)
    pool_id: str = ""  # resource pool created by infra/bootstrap

    # --- Templates ---------------------------------------------------------
    template_ubuntu_2404_id: int = 9000
    template_debian_12_id: int = 9001
    template_windows_2022_id: int = 9002
    template_storage: str = "local-lvm"
    image_storage: str = "local"
    ubuntu_2404_image_url: str = ""
    debian_12_image_url: str = ""
    # LXC templates (vztmpl) for containers; downloaded by the platform stack
    ct_storage: str = ""  # storage with content 'vztmpl' ('' = IMAGE_STORAGE)
    debian_12_ct_url: str = ""
    ubuntu_2404_ct_url: str = ""

    # --- Cloud-init defaults ---------------------------------------------
    ci_user: str = "ops"
    default_ssh_public_key: str = ""

    # --- Configuration management (Ansible) -------------------------------
    ansible_dir: str = "/app/infra/ansible"
    extra_profile_dirs: str = ""  # project role folders with profile.yml, ":"-separated (e.g. /profiles)
    package_denylist: str = ""  # comma-separated package names users and the AI may not install
    package_check: str = "live"  # live | offline | off  (availability check against the repositories)
    approved_profiles_dir: str = ""  # where approved AI-drafted roles are stored (default: WORKSPACE_DIR/profiles)
    ansible_ssh_key_file: str = ""  # private key matching DEFAULT_SSH_PUBLIC_KEY (Docker secret)
    windows_admin_password: SecretStr = SecretStr("")
    # Optional SSH access to the node for the provider (cloud-init snippet upload)
    proxmox_ssh_username: str = ""
    proxmox_ssh_private_key_file: str = ""

    # --- Validation --------------------------------------------------------
    validation_timeout_seconds: int = 300
    mock_fail_validation: bool = False
    mock_speed: float = 1.0  # >1 makes mock jobs faster (used by tests)
    mock_platform_ready: bool = False  # mock: start with templates already built

    # --- AI ----------------------------------------------------------------
    ai_provider: str = "none"  # "anthropic" or "none"
    anthropic_api_key: SecretStr = SecretStr("")
    ai_model: str = "claude-opus-5-5"
    ai_max_tokens: int = 4000

    @property
    def proxmox_base_url(self) -> str:
        return f"https://{self.proxmox_host}:{self.proxmox_port}/api2/json"

    @property
    def proxmox_token_header(self) -> str:
        # PVEAPIToken=USER@REALM!TOKENID=SECRET
        return (
            f"PVEAPIToken={self.proxmox_user}!{self.proxmox_token_id}"
            f"={self.proxmox_token_secret.get_secret_value()}"
        )

    @property
    def ai_enabled(self) -> bool:
        return self.ai_provider.lower() == "anthropic" and bool(
            self.anthropic_api_key.get_secret_value()
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@dataclass(frozen=True)
class EnvironmentPolicy:
    key: str
    label: str
    vmid_min: int
    vmid_max: int
    default_cores: int
    default_memory_mb: int
    default_disk_gb: int
    max_cores: int
    max_memory_mb: int
    max_disk_gb: int
    full_clone: bool
    requires_approval: bool
    description: str


ENVIRONMENTS: dict[str, EnvironmentPolicy] = {
    "test": EnvironmentPolicy(
        key="test",
        label="Test",
        vmid_min=900,
        vmid_max=999,
        default_cores=2,
        default_memory_mb=4096,
        default_disk_gb=32,
        max_cores=4,
        max_memory_mb=8192,
        max_disk_gb=64,
        full_clone=False,
        requires_approval=False,
        description="Disposable VMs on an isolated test network. Linked clones. "
        "Deploys automatically after plan review.",
    ),
    "prod": EnvironmentPolicy(
        key="prod",
        label="Production",
        vmid_min=100,
        vmid_max=299,
        default_cores=2,
        default_memory_mb=4096,
        default_disk_gb=32,
        max_cores=8,
        max_memory_mb=16384,
        max_disk_gb=128,
        full_clone=True,
        requires_approval=True,
        description="Stable VMs on the production network. Full clones. "
        "Requires a passing TEST validation and explicit human approval.",
    ),
}


# Totals for one stack (all components together), on top of the per-machine limits.
STACK_LIMITS = {"test": {"cores": 16, "memory_mb": 32768, "disk_gb": 384, "components": 8},
                "prod": {"cores": 48, "memory_mb": 98304, "disk_gb": 2048, "components": 8}}


def normalize_env(value: str) -> str:
    v = (value or "").strip().lower()
    if v in ("production", "prod"):
        return "prod"
    if v == "test":
        return "test"
    raise ValueError(f"Unknown environment '{value}'. Use 'test' or 'prod'.")


def placement(settings: Settings, env: str) -> dict:
    if env == "prod":
        return {"storage": settings.prod_storage, "bridge": settings.prod_bridge, "vlan": settings.prod_vlan}
    return {"storage": settings.test_storage, "bridge": settings.test_bridge, "vlan": settings.test_vlan}


# Secrets that may be supplied as Docker secrets: VAR_FILE=/run/secrets/<name> wins over VAR.
SECRET_FILE_VARS = ("PROXMOX_TOKEN_SECRET", "ANTHROPIC_API_KEY", "WINDOWS_ADMIN_PASSWORD")


def _secret_file_overrides() -> dict:
    overrides = {}
    for var in SECRET_FILE_VARS:
        path = os.environ.get(f"{var}_FILE")
        if path:
            with open(path, encoding="utf-8") as fh:
                overrides[var.lower()] = fh.read().strip()
    return overrides


@lru_cache
def get_settings() -> Settings:
    return Settings(**_secret_file_overrides())


def public_settings(settings: Settings) -> dict:
    """Settings that are safe to show in the browser. Never includes secrets."""
    return {
        "live_mode": settings.live_mode,
        "proxmox_host": settings.proxmox_host if settings.live_mode else "mock",
        "proxmox_node": settings.proxmox_node,
        "proxmox_token_configured": bool(settings.proxmox_token_secret.get_secret_value()),
        "iac_binary": settings.iac_binary,
        "ai_provider": settings.ai_provider if settings.ai_enabled else "local-fallback",
        "ai_model": settings.ai_model if settings.ai_enabled else None,
        "user": settings.app_user,
    }


# Templates the console can deploy. Linux templates are built automatically by
# infra/platform from the official cloud images; Windows has no redistributable
# cloud image, so its template is provided once (docs/windows-template.md).
TEMPLATE_CATALOG = [
    {"key": "ubuntu-24-04", "label": "Ubuntu 24.04 LTS", "setting": "template_ubuntu_2404_id",
     "image_setting": "ubuntu_2404_image_url", "os_family": "linux", "buildable": True},
    {"key": "debian-12", "label": "Debian 12", "setting": "template_debian_12_id",
     "image_setting": "debian_12_image_url", "os_family": "linux", "buildable": True},
    {"key": "windows-2022", "label": "Windows Server 2022", "setting": "template_windows_2022_id",
     "image_setting": None, "os_family": "windows", "buildable": False},
]


def template_entry(key: str) -> dict | None:
    return next((t for t in TEMPLATE_CATALOG if t["key"] == key), None)


# LXC templates: official Proxmox system templates, downloaded by infra/platform.
CT_CATALOG = [
    {"key": "debian-12-lxc", "label": "Debian 12 (LXC)", "url_setting": "debian_12_ct_url", "os_type": "debian"},
    {"key": "ubuntu-24-04-lxc", "label": "Ubuntu 24.04 (LXC)", "url_setting": "ubuntu_2404_ct_url",
     "os_type": "ubuntu"},
]


def ct_entry(key: str) -> dict | None:
    return next((t for t in CT_CATALOG if t["key"] == key), None)


def ct_storage(settings: "Settings") -> str:
    return settings.ct_storage or settings.image_storage


def ct_file_name(settings: "Settings", key: str) -> str:
    url = getattr(settings, ct_entry(key)["url_setting"]) or ""
    return os.path.basename(url.split("?")[0])


def ct_volume_id(settings: "Settings", key: str) -> str:
    return f"{ct_storage(settings)}:vztmpl/{ct_file_name(settings, key)}"


# Software profiles are discovered at runtime from Ansible roles: services/profile_service.py

NAME_PATTERN = r"^[a-z][a-z0-9-]{1,40}[a-z0-9]$"
