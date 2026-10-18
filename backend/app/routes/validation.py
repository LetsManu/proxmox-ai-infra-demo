from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..database import session_scope
from ..models import JobStatus, VirtualMachine
from ..schemas import JobCreated, ValidateRequest
from ..services.template_service import os_family_for
from ..services.validation_service import finish, validate_vm
from ..workers.job_runner import JobContext, JobOutcome, create_job, submit
from .plans import get_vm

router = APIRouter(prefix="/api", tags=["validation"])


@router.post("/vms/validate", response_model=JobCreated, status_code=202)
def validate(req: ValidateRequest):
    s = get_settings()
    vm = get_vm(req.name, req.environment)
    if not vm:
        raise HTTPException(404, f"VM '{req.name}' is not deployed in {req.environment}. Deploy it first.")
    job_id = create_job(action="validate", environment=req.environment, vm_name=req.name, user=s.app_user,
                        params=req.model_dump())

    def work(ctx: JobContext):
        ctx.log(f"Validating {req.name} (VMID {vm.vmid}) in {req.environment.upper()}")
        os_family = os_family_for(vm.spec.get("template", ""))
        result = validate_vm(s, vmid=vm.vmid, env=req.environment, health_check_port=req.health_check_port,
                             health_check_path=req.health_check_path, simulate_failure=req.simulate_failure,
                             log=ctx.log, os_family=os_family)
        current = get_vm(req.name, req.environment)
        result = finish(result, config_status=current.config_status,
                        profiles=(vm.spec.get("profiles") or []) + (vm.spec.get("packages") or []), log=ctx.log)
        ctx.update_result(validation=result, summary=f"Validation {result['overall']}")
        with session_scope() as db:
            row = db.query(VirtualMachine).filter_by(name=req.name, environment=req.environment).one()
            row.last_validation = result["overall"]
            row.last_validation_at = datetime.now(timezone.utc)
            row.ip_address = result["ip_address"]
        if result["overall"] != "PASS":
            failed = ", ".join(c["name"] for c in result["checks"] if not c["ok"])
            ctx.log(f"Failed checks: {failed}. Use Diagnose in the Validation panel for guidance.")
            return JobOutcome(JobStatus.FAILED, f"Validation FAIL: {failed}")
        return f"Validation PASS ({result['ip_address']})"

    submit(job_id, work)
    return JobCreated(job_id=job_id, status="queued")
