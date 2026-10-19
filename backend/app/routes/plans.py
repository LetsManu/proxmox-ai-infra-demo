"""Plan generation, job polling and history, plus the shared plan/apply helpers
used by the deploy, promotion and recreate workflows."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from ..auth import actor
from ..config import ENVIRONMENTS, Settings, get_settings
from ..database import session_scope
from ..models import HistoryEntry, Job, VirtualMachine
from ..schemas import HistoryOut, JobCreated, JobOut, PlanRequest, VmSpec
from ..services import config_service
from ..services.proxmox_service import MockProxmox, ProxmoxError, find_free_vmid, get_proxmox
from ..services.template_service import ensure_ct_template, ensure_template, os_family_for
from ..services.terraform_service import TerraformService, entry_for
from ..workers.job_runner import JobContext, create_job, submit

router = APIRouter(prefix="/api", tags=["plans"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def current_vms(env: str) -> dict[str, dict]:
    """Desired-state map of all machines already deployed in an environment (`var.vms` + `var.containers`)."""
    settings = get_settings()
    with session_scope() as db:
        rows = db.query(VirtualMachine).filter_by(environment=env).all()
        return {r.name: entry_for(settings, r.spec, r.vmid, r.spec.get("_template_id")) for r in rows}


def get_vm(name: str, env: str) -> VirtualMachine | None:
    with session_scope() as db:
        vm = db.query(VirtualMachine).filter_by(name=name, environment=env).one_or_none()
        if vm:
            db.expunge(vm)
        return vm


def allocate_vmid(settings: Settings, env: str, name: str, reserved: set[int] | None = None) -> int:
    existing = get_vm(name, env)
    if existing:
        return existing.vmid
    policy = ENVIRONMENTS[env]
    with session_scope() as db:
        used = {v.vmid for v in db.query(VirtualMachine).all()} | (reserved or set())
    try:
        used |= get_proxmox(settings).used_vmids()
    except ProxmoxError:
        if settings.live_mode:
            raise
    return find_free_vmid(used, policy.vmid_min, policy.vmid_max)


def add_member(ctx: JobContext, settings: Settings, env: str, spec: VmSpec, desired: dict,
               reserved: set[int]) -> tuple[int, int | None]:
    """Resolve template + ID for one machine and put it into the desired map."""
    ctx.log(f"Checking template '{spec.template}' exists on node {settings.proxmox_node}")
    template_id = None
    if spec.kind == "lxc":
        volid = ensure_ct_template(settings, spec.template)
        ctx.log(f"Using LXC template {volid}")
    else:
        template_id = ensure_template(settings, spec.template)
    vmid = allocate_vmid(settings, env, spec.name, reserved)
    reserved.add(vmid)
    ctx.log(f"{spec.name}: {'container' if spec.kind == 'lxc' else 'VM'} ID {vmid}"
            + (f" from template {template_id}" if template_id else "")
            + f" (range {ENVIRONMENTS[env].vmid_min}-{ENVIRONMENTS[env].vmid_max})")
    desired[spec.name] = entry_for(settings, spec.model_dump(), vmid, template_id)
    return vmid, template_id


def run_plan(ctx: JobContext, settings: Settings, spec: VmSpec | None, env: str, *,
             replace: list[str] | None = None) -> dict:
    """Plan the environment with `spec` added/updated. Stores and returns the plan."""
    current = current_vms(env)
    desired = dict(current)
    extra = {}
    if spec is not None:
        vmid, template_id = add_member(ctx, settings, env, spec, desired, set())
        extra = {"vmid": vmid, "template_id": template_id}
    plan = TerraformService(settings).plan(env, desired, ctx.job_id, ctx.log, replace=replace, current=current)
    result = {"plan": plan.to_dict(), "summary": plan.summary_line, **extra}
    ctx.update_result(**result)
    return result


def apply_plan(ctx: JobContext, settings: Settings, env: str, plan: dict, spec: dict | None,
               *, vmid: int | None = None, template_id: int | None = None,
               members: dict[str, dict] | None = None) -> None:
    """Apply a reviewed plan and record the resulting desired state.

    `members` maps machine name -> {"spec", "vmid", "template_id"} (stacks); a single
    `spec` is the one-machine case."""
    members = dict(members or {})
    if spec is not None:
        members[spec["name"]] = {"spec": spec, "vmid": vmid, "template_id": template_id}
    ctx.log(f"Applying reviewed {ENVIRONMENTS[env].label} plan: {plan['summary']}")
    TerraformService(settings).apply(env, plan, ctx.log)
    now = datetime.now(timezone.utc)
    px = get_proxmox(settings)
    with session_scope() as db:
        for ch in plan["changes"]:
            name = ch["name"]
            row = db.query(VirtualMachine).filter_by(name=name, environment=env).one_or_none()
            if ch["action"] == "destroy":
                if row:
                    if isinstance(px, MockProxmox):
                        px.delete_vm(row.vmid)
                    db.delete(row)
                continue
            m = members.get(name)
            if row is None:
                if m is None:
                    continue
                row = VirtualMachine(name=name, environment=env, vmid=m["vmid"], node=settings.proxmox_node)
                db.add(row)
            if m is not None:
                row.spec = {**m["spec"], "_template_id": m["template_id"]}
                row.vmid = m["vmid"]
            if ch["action"] in ("create", "replace"):
                row.deployed_at = now
                row.last_validation = None
                row.last_validation_at = None
                row.ip_address = None
                config_service.forget_host(settings, env, name)
                row.config_status = None
                row.configured_at = None
                if isinstance(px, MockProxmox):
                    px.register_vm(row.vmid, name, env, windows=os_family_for(row.spec.get("template", "")) == "windows",
                                   kind=row.spec.get("kind", "vm"))
            row.status = "running"
        # Members without an infrastructure change can still have new software (profiles, packages,
        # services): store the reviewed spec and treat it as a new deployment, so the old validation
        # can't be used to promote software that was never tested.
        changed = {ch["name"] for ch in plan["changes"]}
        for name, m in members.items():
            if name in changed:
                continue
            row = db.query(VirtualMachine).filter_by(name=name, environment=env).one_or_none()
            new_spec = {**m["spec"], "_template_id": m["template_id"]}
            if row is not None and row.spec != new_spec:
                ctx.log(f"{name}: no infrastructure change; software settings updated")
                row.spec = new_spec
                row.deployed_at = now
                row.last_validation = None
                row.last_validation_at = None
    ctx.update_result(applied=True, applied_at=now.isoformat())


def configure(ctx: JobContext, settings: Settings, env: str, name: str) -> str:
    """Install the base role and the VM's software profiles with Ansible. Returns the config status."""
    vm = get_vm(name, env)
    if not vm:
        return "skipped"
    profiles = vm.spec.get("profiles") or []
    os_family = os_family_for(vm.spec.get("template", ""))
    status, error, ip = "success", None, None
    try:
        kind = vm.spec.get("kind", "vm")
        ip = config_service.wait_for_ip(settings, vm.vmid, ctx.log, kind=kind)
        config_service.configure_vm(settings, name=name, env=env, ip=ip, os_family=os_family,
                                    profiles=profiles, packages=vm.spec.get("packages") or [],
                                    job_id=ctx.job_id, log=ctx.log, kind=kind,
                                    services=vm.spec.get("services") or [], stack=vm.spec.get("stack") or "")
        ctx.log(f"Configuration of {name} complete.")
    except config_service.ConfigSkipped as exc:
        status = "skipped"
        ctx.log(f"Configuration skipped: {exc}")
    except Exception as exc:  # noqa: BLE001 - recorded on the VM, then re-raised
        status, error = "failed", exc
    with session_scope() as db:
        row = db.query(VirtualMachine).filter_by(name=name, environment=env).one()
        row.config_status = status
        row.configured_at = datetime.now(timezone.utc)
        if ip:
            row.ip_address = ip
    ctx.update_result(config_status=status)
    if error:
        raise RuntimeError(f"Configuration failed: {error}") from error
    return status


def plan_job_or_404(job_id: str) -> Job:
    with session_scope() as db:
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, f"Job {job_id} not found")
        db.expunge(job)
        return job


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/vms/plan", response_model=JobCreated, status_code=202)
def create_plan(req: PlanRequest):
    s = get_settings()
    who = actor()  # captured now: jobs run in worker threads
    spec = req.spec
    job_id = create_job(action="plan", environment=spec.environment, vm_name=spec.name, user=who,
                        params={"spec": spec.model_dump()})

    def work(ctx: JobContext):
        ctx.log(f"Generating {ENVIRONMENTS[spec.environment].label} plan for '{spec.name}' "
                f"({'live' if s.live_mode else 'mock'} mode, {s.iac_binary})")
        return run_plan(ctx, s, spec, spec.environment)["summary"]

    submit(job_id, work, env_lock=spec.environment)
    return JobCreated(job_id=job_id, status="queued")


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(status: str | None = Query(None, pattern="^(queued|running|success|failed|awaiting_approval)$"),
              limit: int = Query(20, ge=1, le=200), vm_name: str | None = None, environment: str | None = None,
              action: str | None = None):
    """Recent jobs (dashboard: in progress, awaiting approval; detail pages: last validation). Logs are omitted."""
    with session_scope() as db:
        q = db.query(Job)
        for col, val in (("status", status), ("vm_name", vm_name), ("environment", environment), ("action", action)):
            if val:
                q = q.filter_by(**{col: val})
        rows = q.order_by(Job.created_at.desc()).limit(limit).all()
        for r in rows:
            db.expunge(r)
    for r in rows:
        r.logs = ""
    return rows


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str):
    return plan_job_or_404(job_id)


@router.get("/history", response_model=list[HistoryOut])
def history(limit: int = Query(50, ge=1, le=500)):
    with session_scope() as db:
        rows = db.query(HistoryEntry).order_by(HistoryEntry.timestamp.desc()).limit(limit).all()
        for r in rows:
            db.expunge(r)
        return rows

