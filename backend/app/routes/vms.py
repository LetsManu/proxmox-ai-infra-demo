from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from ..config import ENVIRONMENTS, get_settings, placement, public_settings
from ..database import session_scope
from ..models import Job, JobStatus, VirtualMachine
from ..schemas import NETWORKS, ConfigureRequest, DeployTestRequest, JobCreated, PowerRequest, RecreateRequest, VmOut
from ..services import template_service
from ..services.proxmox_service import ProxmoxError, get_proxmox
from ..workers.job_runner import JobContext, JobOutcome, create_job, submit
from .plans import apply_plan, configure, get_vm, plan_job_or_404, run_plan
from .promotion import check_approval, finish_approval_job

router = APIRouter(prefix="/api", tags=["vms"])


@router.get("/health")
def health():
    s = get_settings()
    return {"status": "ok", "mode": "live" if s.live_mode else "mock", "settings": public_settings(s)}


@router.get("/proxmox/status")
def proxmox_status():
    s = get_settings()
    px = get_proxmox(s)
    try:
        return {
            "connected": True,
            "mode": "live" if s.live_mode else "mock",
            "version": px.version(),
            "nodes": px.list_nodes(),
            "storage": px.list_storage(),
            "bridges": px.list_bridges(),
            "templates": px.list_templates(),
        }
    except ProxmoxError as exc:
        return {"connected": False, "mode": "live" if s.live_mode else "mock", "error": str(exc)}


@router.get("/templates")
def templates():
    return template_service.list_templates(get_settings())


@router.get("/profiles")
def profiles():
    """Discovered software profiles (built-in and project role folders), re-read on every call."""
    from ..services.profile_service import load_profiles

    return load_profiles(get_settings())


@router.get("/environments")
def environments():
    s = get_settings()
    out = []
    for key, policy in ENVIRONMENTS.items():
        p = placement(s, key)
        out.append({**asdict(policy), "network": {"key": NETWORKS[key], "bridge": p["bridge"], "vlan": p["vlan"],
                                                  "label": f"{p['bridge']} / VLAN {p['vlan']}"},
                    "storage": p["storage"]})
    return out


@router.get("/vms", response_model=list[VmOut])
def list_vms():
    with session_scope() as db:
        rows = db.query(VirtualMachine).order_by(VirtualMachine.environment, VirtualMachine.name).all()
        for r in rows:
            db.expunge(r)
        return rows


@router.post("/vms/deploy/test", response_model=JobCreated, status_code=202)
def deploy_test(req: DeployTestRequest):
    s = get_settings()
    spec = req.spec
    if spec.environment != "test":
        raise HTTPException(400, "This endpoint only deploys to TEST. Production uses the promotion workflow.")
    plan_job = plan_job_or_404(req.plan_job_id)
    if plan_job.action != "plan" or plan_job.environment != "test" or plan_job.status != JobStatus.SUCCESS:
        raise HTTPException(409, "Plan job is not a successful TEST plan. Generate a plan first.")
    if plan_job.params.get("spec") != spec.model_dump():
        raise HTTPException(409, "The VM form changed after the plan was generated. Generate a new plan.")
    if plan_job.result.get("applied"):
        raise HTTPException(409, "This plan was already applied. Generate a new plan.")

    job_id = create_job(action="deploy", environment="test", vm_name=spec.name, user=s.app_user,
                        params={"spec": spec.model_dump(), "plan_job_id": plan_job.id})

    def work(ctx: JobContext):
        apply_plan(ctx, s, "test", plan_job.result["plan"], spec.model_dump(), vmid=plan_job.result["vmid"],
                   template_id=plan_job.result["template_id"])
        with session_scope() as db:
            db.get(Job, plan_job.id).result = {**plan_job.result, "applied": True}
        ctx.update_result(vmid=plan_job.result["vmid"], summary=plan_job.result["summary"])
        ctx.log(f"TEST VM '{spec.name}' deployed as VMID {plan_job.result['vmid']}.")
        configure(ctx, s, "test", spec.name)
        ctx.log("Next: Validate.")
        return plan_job.result["summary"]

    submit(job_id, work, env_lock="test")
    return JobCreated(job_id=job_id, status="queued")


@router.post("/vms/recreate", response_model=JobCreated, status_code=202)
def recreate(req: RecreateRequest):
    """Destroy and recreate a VM from its template (cloud-init re-runs from scratch).

    TEST: plan + apply in one job. PRODUCTION: plan, then human approval with the word RECREATE.
    """
    s = get_settings()
    env = req.environment

    if env == "prod" and req.stage != "request":
        job = check_approval(req, action="recreate", word="RECREATE")
        if req.stage == "reject":
            finish_approval_job(job.id, JobStatus.FAILED, "rejected", s.app_user)
            return JobCreated(job_id=job.id, status=JobStatus.FAILED)
        finish_approval_job(job.id, JobStatus.SUCCESS, "approved", s.app_user)
        apply_id = create_job(action="recreate-apply", environment="prod", vm_name=job.vm_name, user=s.app_user,
                              params={"approval_job_id": job.id})

        def apply_work(ctx: JobContext):
            ctx.log(f"Approved by {s.app_user} (typed RECREATE)")
            apply_plan(ctx, s, "prod", job.result["plan"], None)
            configure(ctx, s, "prod", job.vm_name)
            return job.result["plan"]["summary"]

        submit(apply_id, apply_work, env_lock="prod")
        return JobCreated(job_id=apply_id, status="queued")

    vm = get_vm(req.name, env)
    if not vm:
        raise HTTPException(404, f"VM '{req.name}' is not deployed in {env}.")
    job_id = create_job(action="recreate", environment=env, vm_name=req.name, user=s.app_user,
                        params={"name": req.name})

    def work(ctx: JobContext):
        ctx.log(f"Recreate requested for '{req.name}' (VMID {vm.vmid}) in {env.upper()}: destroy + clone from template")
        result = run_plan(ctx, s, None, env, replace=[req.name])
        if env == "prod":
            ctx.update_result(required_confirmation="RECREATE")
            ctx.log("Production recreate plan ready. DESTRUCTIVE. Waiting for explicit human approval.")
            return JobOutcome(JobStatus.AWAITING_APPROVAL, result["summary"])
        apply_plan(ctx, s, env, result["plan"], None)
        configure(ctx, s, env, req.name)
        ctx.log("TEST VM recreated and configured. Validation state was reset; run Validate again.")
        return result["summary"]

    submit(job_id, work, env_lock=env)
    return JobCreated(job_id=job_id, status="queued")


@router.post("/vms/power")
def power(req: PowerRequest):
    if req.environment != "test":
        raise HTTPException(403, "Power actions from the console are limited to TEST VMs.")
    vm = get_vm(req.name, req.environment)
    if not vm:
        raise HTTPException(404, f"VM '{req.name}' not found in {req.environment}")
    px = get_proxmox(get_settings())
    try:
        (px.start_vm if req.action == "start" else px.stop_vm)(vm.vmid)
        return {"name": req.name, "vmid": vm.vmid, **px.vm_status(vm.vmid)}
    except ProxmoxError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/vms/configure", response_model=JobCreated, status_code=202)
def configure_vm(req: ConfigureRequest):
    """Re-run Ansible (idempotent) for a deployed VM."""
    s = get_settings()
    vm = get_vm(req.name, req.environment)
    if not vm:
        raise HTTPException(404, f"VM '{req.name}' is not deployed in {req.environment}.")
    if req.environment == "prod":
        raise HTTPException(403, "Production is configured as part of an approved promotion or recreate.")
    job_id = create_job(action="configure", environment=req.environment, vm_name=req.name, user=s.app_user,
                        params={"profiles": vm.spec.get("profiles") or []})

    def work(ctx: JobContext):
        status = configure(ctx, s, req.environment, req.name)
        return f"Configuration {status}"

    submit(job_id, work, env_lock=req.environment)
    return JobCreated(job_id=job_id, status="queued")
