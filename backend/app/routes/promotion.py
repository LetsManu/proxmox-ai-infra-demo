"""Production promotion with mandatory human approval.

Two stages, both server-enforced:
  1. request  -> validates preconditions, runs a PRODUCTION plan, and parks the
                 job in `awaiting_approval`. Nothing is changed.
  2. approve  -> requires the awaiting job ID, `acknowledge=true` and the exact
                 typed confirmation word. Only then is the reviewed plan applied.

The AI endpoints have no route into this flow.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from ..auth import actor, require_role, require_second_person
from ..config import get_settings
from ..database import session_scope
from ..models import Job, JobStatus
from ..schemas import ApprovalFields, JobCreated, PromotionRequest, VmSpec
from ..workers.job_runner import JobContext, JobOutcome, add_history, create_job, submit
from .plans import apply_plan, configure, get_vm, plan_job_or_404, run_plan

router = APIRouter(prefix="/api", tags=["promotion"])

APPROVAL_WINDOW = timedelta(minutes=60)


def prod_name(test_name: str) -> str:
    return re.sub(r"-test$", "", test_name)


def require_validated_test_vm(name: str):
    vm = get_vm(name, "test")
    if not vm:
        raise HTTPException(409, f"'{name}' has no TEST deployment. Deploy and validate in TEST first.")
    if vm.last_validation != "PASS":
        raise HTTPException(409, f"TEST validation for '{name}' has not passed "
                                 f"(last result: {vm.last_validation or 'never validated'}).")
    if vm.deployed_at and vm.last_validation_at and vm.last_validation_at < vm.deployed_at:
        raise HTTPException(409, "TEST VM was redeployed after its last validation. Validate again.")
    return vm


def check_approval(req: ApprovalFields, *, action: str, word: str) -> Job:
    """Verify an approve/reject request against an awaiting job. Raises HTTP errors.

    Only approvers decide on production changes; with AUTH_FOUR_EYES not the person who requested it.
    """
    require_role("approver")
    if not req.approval_job_id:
        raise HTTPException(400, "approval_job_id is required")
    job = plan_job_or_404(req.approval_job_id)
    require_second_person(job.user)
    if job.action != action or job.status != JobStatus.AWAITING_APPROVAL:
        raise HTTPException(409, f"Job {job.id} is not an {action} awaiting approval (status: {job.status}).")
    created = job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > APPROVAL_WINDOW:
        raise HTTPException(409, "This plan is older than 60 minutes. Request a fresh plan.")
    if req.stage == "approve":
        if not req.acknowledge:
            raise HTTPException(400, "You must acknowledge that this will change production.")
        if req.confirmation != word:
            raise HTTPException(400, f"Type {word} exactly to confirm.")
    return job


def finish_approval_job(job_id: str, status: str, note: str, user: str) -> None:
    with session_scope() as db:
        # Compare-and-set: of two concurrent approvals only one can move the job out of awaiting_approval.
        claimed = db.query(Job).filter(Job.id == job_id, Job.status == JobStatus.AWAITING_APPROVAL) \
            .update({Job.status: status}, synchronize_session=False)
        if claimed != 1:
            current = db.get(Job, job_id)
            raise HTTPException(409, f"Job {job_id} was already decided ({current.status if current else 'missing'}).")
        job = db.get(Job, job_id)
        db.refresh(job)
        job.result = {**(job.result or {}), "decision": note, "decided_by": user,
                      "decided_at": datetime.now(timezone.utc).isoformat()}
        if status == JobStatus.FAILED:
            job.error = note
        entry = dict(vm_name=job.vm_name, environment=job.environment, action=f"{job.action}-{note}",
                     status=status, user=user, plan_summary=(job.result or {}).get("summary", ""), job_id=job_id)
    add_history(**entry)  # after commit: SQLite allows one writer at a time


@router.post("/vms/promote/production", response_model=JobCreated, status_code=202)
def promote(req: PromotionRequest):
    s = get_settings()
    who = actor()  # captured now: jobs run in worker threads

    if req.stage == "request":
        test_vm = require_validated_test_vm(req.name)
        spec_data = {k: v for k, v in test_vm.spec.items() if not k.startswith("_")}
        try:
            spec = VmSpec(**{**spec_data, "name": prod_name(req.name), "environment": "prod", "network": "prod",
                             "tags": sorted(set(spec_data.get("tags", [])) | {"promoted"})})
        except ValueError as exc:
            raise HTTPException(422, f"TEST spec is not valid for production: {exc}") from exc
        job_id = create_job(action="promote", environment="prod", vm_name=spec.name, user=who,
                            params={"spec": spec.model_dump(), "source_vm": req.name})

        def work(ctx: JobContext):
            ctx.log(f"Promotion requested: TEST '{req.name}' (validated {test_vm.last_validation_at:%Y-%m-%d %H:%M} UTC) "
                    f"-> PRODUCTION '{spec.name}'")
            result = run_plan(ctx, s, spec, "prod")
            ctx.update_result(required_confirmation="PROMOTE", source_vm=req.name)
            ctx.log("Production plan ready. Waiting for explicit human approval. Nothing has been changed.")
            return JobOutcome(JobStatus.AWAITING_APPROVAL, result["summary"])

        submit(job_id, work, env_lock="prod")
        return JobCreated(job_id=job_id, status="queued")

    job = check_approval(req, action="promote", word="PROMOTE")
    if req.stage == "reject":
        finish_approval_job(job.id, JobStatus.FAILED, "rejected", who)
        return JobCreated(job_id=job.id, status=JobStatus.FAILED)

    # approve: re-check the precondition at the moment of approval
    require_validated_test_vm(job.params["source_vm"])
    finish_approval_job(job.id, JobStatus.SUCCESS, "approved", who)
    spec = job.params["spec"]
    apply_id = create_job(action="promote-apply", environment="prod", vm_name=spec["name"], user=who,
                          params={"approval_job_id": job.id, "approved_by": who})

    def apply_work(ctx: JobContext):
        ctx.log(f"Approved by {who} (typed PROMOTE, acknowledged production impact)")
        apply_plan(ctx, s, "prod", job.result["plan"], spec, vmid=job.result["vmid"],
                   template_id=job.result["template_id"])
        ctx.update_result(summary=job.result["plan"]["summary"])
        configure(ctx, s, "prod", spec["name"])
        ctx.log("Production deployment complete. Run Validate against PRODUCTION to confirm.")
        return job.result["plan"]["summary"]

    submit(apply_id, apply_work, env_lock="prod")
    return JobCreated(job_id=apply_id, status="queued")
