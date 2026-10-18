"""Stacks: several VMs / LXC containers (plus Docker services on them) handled as one unit.

Every member is an ordinary machine named <stack>-<component>[-test]: the same
limits, plans, configuration, validation and promotion rules apply. The stack
adds "all together": one plan for all members, one deploy, one validation
verdict, one production approval.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..config import ENVIRONMENTS, get_settings
from ..database import session_scope
from ..models import JobStatus, Stack
from ..schemas import JobCreated, StackDeployRequest, StackPlanRequest, StackPromotionRequest, StackSpec, \
    StackValidateRequest
from ..services.terraform_service import TerraformService
from ..workers.job_runner import JobContext, JobOutcome, create_job, submit
from .plans import add_member, apply_plan, configure, current_vms, get_vm, plan_job_or_404
from .promotion import check_approval, finish_approval_job
from .validation import validate_member

router = APIRouter(prefix="/api/stacks", tags=["stacks"])


def get_stack(name: str, env: str) -> Stack | None:
    with session_scope() as db:
        st = db.query(Stack).filter_by(name=name, environment=env).one_or_none()
        if st:
            db.expunge(st)
        return st


def _out(st: Stack) -> dict:
    members = []
    for n in st.members:
        vm = get_vm(n, st.environment)
        if vm:
            members.append({"name": n, "kind": vm.spec.get("kind", "vm"), "vmid": vm.vmid,
                            "template": vm.spec.get("template"), "ip_address": vm.ip_address,
                            "status": vm.status, "config_status": vm.config_status,
                            "last_validation": vm.last_validation,
                            "services": [x["name"] for x in vm.spec.get("services") or []]})
    return {"name": st.name, "environment": st.environment, "spec": st.spec, "members": members,
            "deployed_at": st.deployed_at.isoformat() if st.deployed_at else None,
            "last_validation": st.last_validation,
            "last_validation_at": st.last_validation_at.isoformat() if st.last_validation_at else None}


@router.get("")
def list_stacks():
    with session_scope() as db:
        rows = db.query(Stack).order_by(Stack.environment, Stack.name).all()
        for r in rows:
            db.expunge(r)
    return [_out(r) for r in rows]


def run_stack_plan(ctx: JobContext, s, stack: StackSpec, *, recreate: bool = False) -> dict:
    env = stack.environment
    current = current_vms(env)
    desired = dict(current)
    previous = get_stack(stack.name, env)
    specs = stack.member_specs()
    wanted = {m.name for m in specs}
    removed = [n for n in (previous.members if previous else []) if n not in wanted]
    for n in removed:
        desired.pop(n, None)
        ctx.log(f"{n}: no longer part of the stack, will be destroyed")
    members, reserved = {}, set()
    for spec in specs:
        vmid, template_id = add_member(ctx, s, env, spec, desired, reserved)
        members[spec.name] = {"spec": spec.model_dump(), "vmid": vmid, "template_id": template_id}
    replace = [m.name for m in specs if m.name in current] if recreate else []
    if replace:
        ctx.log(f"Recreate requested: {', '.join(replace)} will be destroyed and created again")
    plan = TerraformService(s).plan(env, desired, ctx.job_id, ctx.log, replace=replace, current=current)
    result = {"plan": plan.to_dict(), "summary": plan.summary_line, "members": members,
              "stack": stack.model_dump(), "removed": removed}
    ctx.update_result(**result)
    return result


@router.post("/plan", response_model=JobCreated, status_code=202)
def plan_stack(req: StackPlanRequest):
    s = get_settings()
    stack = req.stack
    if stack.environment != "test":
        raise HTTPException(400, "Stacks are planned in TEST. Production uses the stack promotion workflow.")
    if req.recreate and not get_stack(stack.name, "test"):
        raise HTTPException(409, f"Stack '{stack.name}' is not deployed in TEST; nothing to recreate.")
    job_id = create_job(action="stack-plan", environment="test", vm_name=stack.name, user=s.app_user,
                        params={"stack": stack.model_dump(), "recreate": req.recreate})

    def work(ctx: JobContext):
        kinds = ", ".join(f"{c.name} ({c.kind}{', ' + str(len(c.services)) + ' services' if c.services else ''})"
                          for c in stack.components)
        ctx.log(f"Planning stack '{stack.name}' in TEST: {kinds}")
        return run_stack_plan(ctx, s, stack, recreate=req.recreate)["summary"]

    submit(job_id, work, env_lock="test")
    return JobCreated(job_id=job_id, status="queued")


def apply_stack(ctx: JobContext, s, env: str, plan_result: dict) -> None:
    stack = plan_result["stack"]
    apply_plan(ctx, s, env, plan_result["plan"], None, members=plan_result["members"])
    names = list(plan_result["members"])
    with session_scope() as db:
        st = db.query(Stack).filter_by(name=stack["name"], environment=env).one_or_none()
        if st is None:
            st = Stack(name=stack["name"], environment=env)
            db.add(st)
        st.spec = stack
        st.members = names
        st.deployed_at = datetime.now(timezone.utc)
        st.last_validation = None
        st.last_validation_at = None
    failed = []
    for n in names:  # configure every member; one failure must not hide the others
        ctx.log(f"--- Configuring {n} ---")
        try:
            configure(ctx, s, env, n)
        except Exception as exc:  # noqa: BLE001 - reported below
            failed.append(n)
            ctx.log(f"{n}: {exc}")
    if failed:
        raise RuntimeError(f"Configuration failed on: {', '.join(failed)}")


@router.post("/deploy", response_model=JobCreated, status_code=202)
def deploy_stack(req: StackDeployRequest):
    s = get_settings()
    plan_job = plan_job_or_404(req.plan_job_id)
    if plan_job.action != "stack-plan" or plan_job.status != JobStatus.SUCCESS:
        raise HTTPException(409, "Not a successful stack plan. Plan the stack first.")
    if plan_job.result.get("applied"):
        raise HTTPException(409, "This plan was already applied. Plan the stack again.")
    name = plan_job.result["stack"]["name"]
    job_id = create_job(action="stack-deploy", environment="test", vm_name=name, user=s.app_user,
                        params={"plan_job_id": plan_job.id})

    def work(ctx: JobContext):
        from ..models import Job

        with session_scope() as db:
            db.get(Job, plan_job.id).result = {**plan_job.result, "applied": True}
        apply_stack(ctx, s, "test", plan_job.result)
        ctx.log(f"Stack '{name}' deployed to TEST. Validate it before promotion.")
        return plan_job.result["summary"]

    submit(job_id, work, env_lock="test")
    return JobCreated(job_id=job_id, status="queued")


@router.post("/validate", response_model=JobCreated, status_code=202)
def validate_stack(req: StackValidateRequest):
    s = get_settings()
    st = get_stack(req.name, req.environment)
    if not st:
        raise HTTPException(404, f"Stack '{req.name}' is not deployed in {req.environment}.")
    job_id = create_job(action="stack-validate", environment=req.environment, vm_name=req.name, user=s.app_user,
                        params=req.model_dump())

    def work(ctx: JobContext):
        results = {}
        for n in st.members:
            vm = get_vm(n, req.environment)
            if not vm:
                results[n] = {"overall": "FAIL", "checks": [{"name": "exists", "ok": False, "detail": "missing"}]}
                continue
            ctx.log(f"--- {n} ---")
            results[n] = validate_member(ctx, s, vm, req.environment, simulate_failure=req.simulate_failure)
        overall = "PASS" if all(r["overall"] == "PASS" for r in results.values()) else "FAIL"
        with session_scope() as db:
            row = db.query(Stack).filter_by(name=req.name, environment=req.environment).one()
            row.last_validation = overall
            row.last_validation_at = datetime.now(timezone.utc)
        ctx.update_result(members=results, overall=overall, summary=f"Stack validation {overall}")
        failed = [n for n, r in results.items() if r["overall"] != "PASS"]
        ctx.log(f"Stack validation result: {overall}" + (f" (failed: {', '.join(failed)})" if failed else ""))
        if failed:
            return JobOutcome(JobStatus.FAILED, f"Stack validation FAIL: {', '.join(failed)}")
        return "Stack validation PASS"

    submit(job_id, work)
    return JobCreated(job_id=job_id, status="queued")


def require_validated_stack(name: str) -> Stack:
    st = get_stack(name, "test")
    if not st:
        raise HTTPException(409, f"Stack '{name}' has no TEST deployment. Deploy and validate it in TEST first.")
    if st.last_validation != "PASS":
        raise HTTPException(409, f"TEST validation of stack '{name}' has not passed "
                                 f"(last result: {st.last_validation or 'never validated'}).")
    if st.deployed_at and st.last_validation_at and st.last_validation_at < st.deployed_at:
        raise HTTPException(409, "The TEST stack was redeployed after its last validation. Validate again.")
    return st


@router.post("/promote", response_model=JobCreated, status_code=202)
def promote_stack(req: StackPromotionRequest):
    """Whole-stack promotion: one PRODUCTION plan, one human approval (typed PROMOTE)."""
    s = get_settings()
    if req.stage == "request":
        test = require_validated_stack(req.name)
        try:
            stack = StackSpec(**{**test.spec, "environment": "prod"})
        except ValueError as exc:
            raise HTTPException(422, f"TEST stack is not valid for production: {exc}") from exc
        job_id = create_job(action="stack-promote", environment="prod", vm_name=stack.name, user=s.app_user,
                            params={"stack": stack.model_dump(), "source": req.name})

        def work(ctx: JobContext):
            ctx.log(f"Promotion requested: TEST stack '{req.name}' (validated "
                    f"{test.last_validation_at:%Y-%m-%d %H:%M} UTC) -> PRODUCTION, "
                    f"{len(stack.components)} member(s), full clones, {ENVIRONMENTS['prod'].label} network")
            result = run_stack_plan(ctx, s, stack)
            ctx.update_result(required_confirmation="PROMOTE", source_stack=req.name)
            ctx.log("Production plan ready. Waiting for explicit human approval. Nothing has been changed.")
            return JobOutcome(JobStatus.AWAITING_APPROVAL, result["summary"])

        submit(job_id, work, env_lock="prod")
        return JobCreated(job_id=job_id, status="queued")

    job = check_approval(req, action="stack-promote", word="PROMOTE")
    if req.stage == "reject":
        finish_approval_job(job.id, JobStatus.FAILED, "rejected", s.app_user)
        return JobCreated(job_id=job.id, status=JobStatus.FAILED)

    require_validated_stack(job.params["source"])  # re-checked at the moment of approval
    finish_approval_job(job.id, JobStatus.SUCCESS, "approved", s.app_user)
    apply_id = create_job(action="stack-promote-apply", environment="prod", vm_name=job.vm_name, user=s.app_user,
                          params={"approval_job_id": job.id, "approved_by": s.app_user})

    def apply_work(ctx: JobContext):
        ctx.log(f"Approved by {s.app_user} (typed PROMOTE, acknowledged production impact)")
        apply_stack(ctx, s, "prod", job.result)
        ctx.log("Production stack deployed. Run Validate against PRODUCTION to confirm.")
        return job.result["summary"]

    submit(apply_id, apply_work, env_lock="prod")
    return JobCreated(job_id=apply_id, status="queued")


@router.get("/{name}")
def get_stack_detail(name: str, environment: str = "test"):
    st = get_stack(name, environment)
    if not st:
        raise HTTPException(404, f"Stack '{name}' is not deployed in {environment}.")
    return _out(st)

