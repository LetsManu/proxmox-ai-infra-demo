"""Platform resources: status of everything the console needs, and the
platform stack (cloud images + templates) with plan -> review -> apply."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..models import JobStatus
from ..schemas import JobCreated, PlatformApplyRequest
from ..services import platform_service
from ..services.terraform_service import TerraformService
from ..workers.job_runner import JobContext, create_job, submit
from .plans import plan_job_or_404

router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("")
def platform_status():
    s = get_settings()
    out = platform_service.status(s)
    out["declared_templates"] = sorted(platform_service.desired_templates(s)) if out["reachable"] else []
    return out


@router.post("/plan", response_model=JobCreated, status_code=202)
def platform_plan():
    s = get_settings()
    job_id = create_job(action="platform-plan", environment="infra", vm_name="platform", user=s.app_user, params={})

    def work(ctx: JobContext):
        templates = platform_service.desired_templates(s)
        names = ", ".join(sorted(templates)) or "none"
        ctx.log(f"Platform stack (infra/platform): templates declared: {names}")
        plan = TerraformService(s).plan_platform(templates, ctx.job_id, ctx.log)
        ctx.update_result(plan=plan.to_dict(), summary=plan.summary_line, templates=sorted(templates))
        return plan.summary_line

    submit(job_id, work, env_lock="infra")
    return JobCreated(job_id=job_id, status="queued")


@router.post("/apply", response_model=JobCreated, status_code=202)
def platform_apply(req: PlatformApplyRequest):
    s = get_settings()
    plan_job = plan_job_or_404(req.plan_job_id)
    if plan_job.action != "platform-plan" or plan_job.status != JobStatus.SUCCESS:
        raise HTTPException(409, "Not a successful platform plan. Plan the platform first.")
    if plan_job.result.get("applied"):
        raise HTTPException(409, "This platform plan was already applied.")
    plan = plan_job.result["plan"]
    if plan["has_destroy"] and not req.confirm_destroy:
        raise HTTPException(400, "This platform plan destroys resources; confirm it explicitly.")
    job_id = create_job(action="platform-apply", environment="infra", vm_name="platform", user=s.app_user,
                        params={"plan_job_id": plan_job.id})

    def work(ctx: JobContext):
        ctx.log(f"Applying reviewed platform plan: {plan['summary']}")
        TerraformService(s).apply_platform(plan, ctx.log)
        from ..database import session_scope
        from ..models import Job

        with session_scope() as db:
            db.get(Job, plan_job.id).result = {**plan_job.result, "applied": True}
        ctx.update_result(summary=plan["summary"])
        return plan["summary"]

    submit(job_id, work, env_lock="infra")
    return JobCreated(job_id=job_id, status="queued")
