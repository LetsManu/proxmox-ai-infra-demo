"""Plan generation, job polling and history, plus the shared plan/apply helpers
used by the deploy, promotion and recreate workflows."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from ..config import ENVIRONMENTS, Settings, get_settings
from ..database import session_scope
from ..models import HistoryEntry, Job, VirtualMachine
from ..schemas import HistoryOut, JobCreated, JobOut, PlanRequest, VmSpec
from ..services.proxmox_service import MockProxmox, ProxmoxError, find_free_vmid, get_proxmox
from ..services.template_service import ensure_template
from ..services.terraform_service import TerraformService, vm_entry
from ..workers.job_runner import JobContext, create_job, submit

router = APIRouter(prefix="/api", tags=["plans"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def current_vms(env: str) -> dict[str, dict]:
    """Desired-state map of all VMs already deployed in an environment (`var.vms`)."""
    with session_scope() as db:
        rows = db.query(VirtualMachine).filter_by(environment=env).all()
        return {r.name: vm_entry(r.spec, r.vmid, r.spec["_template_id"]) for r in rows}


def get_vm(name: str, env: str) -> VirtualMachine | None:
    with session_scope() as db:
        vm = db.query(VirtualMachine).filter_by(name=name, environment=env).one_or_none()
        if vm:
            db.expunge(vm)
        return vm


def allocate_vmid(settings: Settings, env: str, name: str) -> int:
    existing = get_vm(name, env)
    if existing:
        return existing.vmid
    policy = ENVIRONMENTS[env]
    with session_scope() as db:
        used = {v.vmid for v in db.query(VirtualMachine).all()}
    try:
        used |= get_proxmox(settings).used_vmids()
    except ProxmoxError:
        if settings.live_mode:
            raise
    return find_free_vmid(used, policy.vmid_min, policy.vmid_max)


def run_plan(ctx: JobContext, settings: Settings, spec: VmSpec | None, env: str, *,
             replace: list[str] | None = None) -> dict:
    """Plan the environment with `spec` added/updated. Stores and returns the plan."""
    current = current_vms(env)
    desired = dict(current)
    extra = {}
    if spec is not None:
        ctx.log(f"Checking template '{spec.template}' exists on node {settings.proxmox_node}")
        template_id = ensure_template(settings, spec.template)
        vmid = allocate_vmid(settings, env, spec.name)
        ctx.log(f"Using template VMID {template_id}; VM ID {vmid} "
                f"(range {ENVIRONMENTS[env].vmid_min}-{ENVIRONMENTS[env].vmid_max})")
        desired[spec.name] = vm_entry(spec.model_dump(), vmid, template_id)
        extra = {"vmid": vmid, "template_id": template_id}
    plan = TerraformService(settings).plan(env, desired, ctx.job_id, ctx.log, replace=replace, current=current)
    result = {"plan": plan.to_dict(), "summary": plan.summary_line, **extra}
    ctx.update_result(**result)
    return result


def apply_plan(ctx: JobContext, settings: Settings, env: str, plan: dict, spec: dict | None,
               *, vmid: int | None = None, template_id: int | None = None) -> None:
    """Apply a reviewed plan and record the resulting desired state."""
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
            if row is None:
                if spec is None or spec["name"] != name:
                    continue
                row = VirtualMachine(name=name, environment=env, vmid=vmid, node=settings.proxmox_node)
                db.add(row)
            if spec is not None and spec["name"] == name:
                row.spec = {**spec, "_template_id": template_id}
                row.vmid = vmid
            if ch["action"] in ("create", "replace"):
                row.deployed_at = now
                row.last_validation = None
                row.last_validation_at = None
                row.ip_address = None
                if isinstance(px, MockProxmox):
                    px.register_vm(row.vmid, name, env)
            row.status = "running"
    ctx.update_result(applied=True, applied_at=now.isoformat())


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
    spec = req.spec
    job_id = create_job(action="plan", environment=spec.environment, vm_name=spec.name, user=s.app_user,
                        params={"spec": spec.model_dump()})

    def work(ctx: JobContext):
        ctx.log(f"Generating {ENVIRONMENTS[spec.environment].label} plan for '{spec.name}' "
                f"({'live' if s.live_mode else 'mock'} mode, {s.iac_binary})")
        return run_plan(ctx, s, spec, spec.environment)["summary"]

    submit(job_id, work, env_lock=spec.environment)
    return JobCreated(job_id=job_id, status="queued")


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

