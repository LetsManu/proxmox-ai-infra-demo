from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import (CT_CATALOG, ENVIRONMENTS, NAME_PATTERN, STACK_LIMITS, TEMPLATE_CATALOG, get_settings,
                     normalize_env, template_entry)

TEMPLATE_KEYS = {t["key"] for t in TEMPLATE_CATALOG}
CT_KEYS = {t["key"] for t in CT_CATALOG}
NETWORKS = {"test": "test", "prod": "prod"}


class CloudInit(BaseModel):
    packages: list[str] = Field(default_factory=list, max_length=25)
    commands: list[str] = Field(default_factory=list, max_length=25)

    @field_validator("packages")
    @classmethod
    def _pkg_names(cls, v: list[str]) -> list[str]:
        import re

        for p in v:
            if not re.fullmatch(r"[a-z0-9][a-z0-9.+\-]{0,63}", p):
                raise ValueError(f"Invalid package name '{p}'")
        return v

    @field_validator("commands")
    @classmethod
    def _commands(cls, v: list[str]) -> list[str]:
        for c in v:
            if len(c) > 300 or "\n" in c:
                raise ValueError("Cloud-init commands must be single lines under 300 characters")
        return v


SECRET_KEY_RE = r"(?i)(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE)"


class DockerService(BaseModel):
    """One container on a Docker host. Only images, ports, named volumes and plain settings:
    no privileged mode, host mounts, capabilities or host networking can be expressed."""

    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,29}[a-z0-9]$")
    image: str = Field(pattern=r"^[a-z0-9][a-z0-9._/-]{0,127}(:[A-Za-z0-9._-]{1,64})?(@sha256:[a-f0-9]{64})?$")
    ports: list[str] = Field(default_factory=list, max_length=10)   # "8080:80"
    env: dict[str, str] = Field(default_factory=dict)              # value or "secret:<name>"
    volumes: list[str] = Field(default_factory=list, max_length=10)  # "named-volume:/path"

    @field_validator("ports")
    @classmethod
    def _ports(cls, v: list[str]) -> list[str]:
        import re

        for p in v:
            m = re.fullmatch(r"(\d{1,5}):(\d{1,5})", p)
            if not m or not all(0 < int(x) < 65536 for x in m.groups()):
                raise ValueError(f"Port mapping '{p}' must look like HOST:CONTAINER, e.g. 8080:80")
        return v

    @field_validator("volumes")
    @classmethod
    def _volumes(cls, v: list[str]) -> list[str]:
        import re

        for vol in v:
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,40}:/[A-Za-z0-9._/-]{1,120}", vol) or ".." in vol:
                raise ValueError(f"Volume '{vol}' must be a named volume like data:/var/lib/data (no host paths)")
        return v

    @field_validator("env")
    @classmethod
    def _env(cls, v: dict[str, str]) -> dict[str, str]:
        import re

        if len(v) > 30:
            raise ValueError("At most 30 environment variables per service")
        for k, val in v.items():
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", k):
                raise ValueError(f"Invalid environment variable name '{k}'")
            if not isinstance(val, str) or len(val) > 300 or "\n" in val or "$" in val:
                raise ValueError(f"{k}: values must be single-line text without '$'")
            if val.startswith("secret:"):
                if not re.fullmatch(r"secret:[a-z][a-z0-9_]{1,40}", val):
                    raise ValueError(f"{k}: secret references look like secret:db_password")
            elif re.search(SECRET_KEY_RE, k) and val:
                raise ValueError(f"{k} looks like a secret. Use secret:<name>; the host generates and keeps it.")
        return v


class VmSpec(BaseModel):
    """A VM definition. Environment limits are enforced here, server-side,
    regardless of what the browser or the AI produced."""

    name: str = Field(pattern=NAME_PATTERN)
    environment: str = "test"
    template: str = "ubuntu-24-04"
    cores: int = Field(default=2, ge=1, le=64)
    memory_mb: int = Field(default=4096, ge=512, le=262144)
    disk_gb: int = Field(default=32, ge=8, le=4096)
    network: str | None = None
    description: str = Field(default="", max_length=500)
    ssh_public_key: str = Field(default="", max_length=4096)
    cloud_init: CloudInit = Field(default_factory=CloudInit)
    profiles: list[str] = Field(default_factory=list, max_length=20)
    packages: list[str] = Field(default_factory=list, max_length=40)  # apt (Linux) / Chocolatey (Windows)
    tags: list[str] = Field(default_factory=list, max_length=10)
    kind: Literal["vm", "lxc"] = "vm"
    services: list[DockerService] = Field(default_factory=list, max_length=12)  # needs the docker profile
    stack: str = Field(default="", max_length=64)

    @property
    def os_family(self) -> str:
        t = template_entry(self.template)
        return t["os_family"] if t else "linux"

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        return normalize_env(v)

    @field_validator("template")
    @classmethod
    def _template(cls, v: str) -> str:
        if v not in TEMPLATE_KEYS | CT_KEYS:
            raise ValueError(f"Unknown template '{v}'. Allowed: {sorted(TEMPLATE_KEYS | CT_KEYS)}")
        return v

    @field_validator("ssh_public_key")
    @classmethod
    def _ssh_key(cls, v: str) -> str:
        v = v.strip()
        if v and not v.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")):
            raise ValueError("SSH key must be an OpenSSH *public* key (ssh-ed25519 / ssh-rsa / ecdsa)")
        if "PRIVATE KEY" in v:
            raise ValueError("That looks like a private key. Never paste private keys.")
        return v

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        import re

        for t in v:
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,30}", t):
                raise ValueError(f"Invalid tag '{t}'")
        return v

    @model_validator(mode="after")
    def _limits(self) -> "VmSpec":
        policy = ENVIRONMENTS[self.environment]
        errors = []
        if self.cores > policy.max_cores:
            errors.append(f"{policy.label}: max {policy.max_cores} vCPU (requested {self.cores})")
        if self.memory_mb > policy.max_memory_mb:
            errors.append(f"{policy.label}: max {policy.max_memory_mb} MB RAM (requested {self.memory_mb})")
        if self.disk_gb > policy.max_disk_gb:
            errors.append(f"{policy.label}: max {policy.max_disk_gb} GB disk (requested {self.disk_gb})")
        if self.network is None:
            self.network = NETWORKS[self.environment]
        if self.network != NETWORKS[self.environment]:
            errors.append(
                f"Network '{self.network}' is not allowed in {policy.label}; "
                f"use '{NETWORKS[self.environment]}'"
            )
        from .services.profile_service import get_profiles, package_errors

        settings = get_settings()
        catalog = get_profiles(settings)
        os_family = self.os_family
        for p in self.profiles:
            prof = catalog.get(p)
            if not prof:
                errors.append(f"Unknown software profile '{p}'. Available: {sorted(catalog)}")
            elif prof["os_family"] != os_family:
                errors.append(f"Profile '{p}' is for {prof['os_family']}, but {self.template} is {os_family}")
        if len(set(self.profiles)) != len(self.profiles):
            errors.append("Profiles must not repeat")
        errors += package_errors(settings, os_family, self.packages)
        if os_family == "windows":
            if len(self.name) > 15:
                errors.append("Windows computer names are limited to 15 characters")
            # cloud-init packages and SSH keys do not apply to Windows; software comes from profiles
            self.cloud_init = CloudInit()
            self.ssh_public_key = ""
        if self.kind == "lxc" and self.template not in CT_KEYS:
            errors.append(f"Containers use an LXC template: {sorted(CT_KEYS)}")
        if self.kind == "vm" and self.template in CT_KEYS:
            errors.append(f"'{self.template}' is an LXC template; set kind to lxc or pick a VM template")
        if self.services:
            if "docker" not in self.profiles:
                errors.append("Docker services need the 'docker' profile on this machine")
            names = [x.name for x in self.services]
            if len(set(names)) != len(names):
                errors.append("Docker service names must be unique per host")
            host_ports = [p.split(":")[0] for x in self.services for p in x.ports]
            if len(set(host_ports)) != len(host_ports):
                errors.append("Two services publish the same host port")
        if errors:
            raise ValueError("; ".join(errors))
        return self


class StackComponent(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,10}[a-z0-9]$")
    kind: Literal["vm", "lxc"] = "vm"
    template: str = "ubuntu-24-04"
    cores: int = Field(default=2, ge=1, le=64)
    memory_mb: int = Field(default=2048, ge=256, le=262144)
    disk_gb: int = Field(default=16, ge=4, le=4096)
    description: str = Field(default="", max_length=300)
    profiles: list[str] = Field(default_factory=list, max_length=20)
    packages: list[str] = Field(default_factory=list, max_length=40)
    services: list[DockerService] = Field(default_factory=list, max_length=12)


class StackSpec(BaseModel):
    """Machines deployed, validated and promoted together. Each component becomes a VmSpec
    named <stack>-<component>[-test], so all single-VM rules apply to every member."""

    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,18}[a-z0-9]$")
    environment: str = "test"
    description: str = Field(default="", max_length=500)
    components: list[StackComponent] = Field(min_length=1, max_length=8)

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        return normalize_env(v)

    def member_name(self, component: str) -> str:
        return f"{self.name}-{component}" + ("-test" if self.environment == "test" else "")

    def member_specs(self) -> list[VmSpec]:
        out = []
        for c in self.components:
            out.append(VmSpec(name=self.member_name(c.name), environment=self.environment, template=c.template,
                              cores=c.cores, memory_mb=c.memory_mb, disk_gb=c.disk_gb,
                              description=c.description or f"{self.name}: {c.name}", profiles=c.profiles,
                              packages=c.packages, kind=c.kind, services=c.services, stack=self.name,
                              tags=["stack-" + self.name[:24]]))
        return out

    @model_validator(mode="after")
    def _members(self) -> "StackSpec":
        from pydantic import ValidationError

        errors = []
        names = [c.name for c in self.components]
        if len(set(names)) != len(names):
            errors.append("Component names must be unique")
        limits = STACK_LIMITS[self.environment]
        for key, unit in (("cores", "vCPU"), ("memory_mb", "MB RAM"), ("disk_gb", "GB disk")):
            total = sum(getattr(c, key) for c in self.components)
            if total > limits[key]:
                errors.append(f"Stack total {total} {unit} exceeds the {ENVIRONMENTS[self.environment].label} "
                              f"stack limit of {limits[key]}")
        for c in self.components:
            try:
                VmSpec(name=self.member_name(c.name), environment=self.environment, template=c.template,
                       cores=c.cores, memory_mb=c.memory_mb, disk_gb=c.disk_gb, profiles=c.profiles,
                       packages=c.packages, kind=c.kind, services=c.services)
            except ValidationError as exc:
                errors += [f"{c.name}: {str(e['msg']).removeprefix('Value error, ')}" for e in exc.errors()]
        if errors:
            raise ValueError("; ".join(errors))
        return self


class StackPlanRequest(BaseModel):
    stack: StackSpec
    recreate: bool = False


class StackDeployRequest(BaseModel):
    plan_job_id: str


class StackValidateRequest(BaseModel):
    name: str
    environment: str = Field("test", pattern="^(test|prod)$")
    simulate_failure: bool = False


class StackPromotionRequest(BaseModel):
    name: str
    stage: Literal["request", "approve", "reject"] = "request"
    approval_job_id: str | None = None
    acknowledge: bool = False
    confirmation: str = ""


class GenerateStackRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)


class PlanRequest(BaseModel):
    spec: VmSpec


class DeployTestRequest(BaseModel):
    spec: VmSpec
    plan_job_id: str


class ValidateRequest(BaseModel):
    name: str = Field(pattern=NAME_PATTERN)
    environment: str = "test"
    health_check_port: int | None = Field(default=None, ge=1, le=65535)
    health_check_path: str | None = Field(default=None, max_length=200)
    simulate_failure: bool = False

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        return normalize_env(v)


class ApprovalFields(BaseModel):
    stage: Literal["request", "approve", "reject"] = "request"
    approval_job_id: str | None = None
    acknowledge: bool = False
    confirmation: str = ""


class PromotionRequest(ApprovalFields):
    name: str = Field(pattern=NAME_PATTERN)


class RecreateRequest(ApprovalFields):
    name: str = Field(pattern=NAME_PATTERN)
    environment: str = "test"

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        return normalize_env(v)


class ConfigureRequest(BaseModel):
    name: str = Field(pattern=NAME_PATTERN)
    environment: str = "test"

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        return normalize_env(v)


class DraftTestsRequest(BaseModel):
    name: str = Field(min_length=3, max_length=63)
    environment: str = Field("test", pattern="^(test|prod)$")


class PlatformApplyRequest(BaseModel):
    plan_job_id: str
    confirm_destroy: bool = False


class PowerRequest(BaseModel):
    name: str = Field(pattern=NAME_PATTERN)
    environment: str = "test"
    action: Literal["start", "stop"]

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        return normalize_env(v)


class SummarizePlanRequest(BaseModel):
    plan_text: str = Field(max_length=200_000)
    environment: str = "test"

    @field_validator("environment")
    @classmethod
    def _env(cls, v: str) -> str:
        return normalize_env(v)


class GenerateSpecRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)


class TroubleshootRequest(BaseModel):
    vm_name: str = Field(max_length=64)
    job_logs: str = Field(default="", max_length=200_000)
    validation_output: Any = None
    proxmox_status: Any = None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    action: str
    environment: str
    vm_name: str
    user: str
    params: dict
    logs: str
    result: dict
    error: str | None
    created_at: datetime
    updated_at: datetime


class JobCreated(BaseModel):
    job_id: str
    status: str


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    vm_name: str
    environment: str
    action: str
    status: str
    user: str
    plan_summary: str
    job_id: str | None


class VmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    environment: str
    vmid: int
    node: str
    spec: dict
    status: str
    ip_address: str | None
    last_validation: str | None
    last_validation_at: datetime | None
    config_status: str | None
    configured_at: datetime | None
    deployed_at: datetime | None
