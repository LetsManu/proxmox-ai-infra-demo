from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..database import session_scope
from ..models import JobStatus, VirtualMachine
from ..schemas import DraftTestsRequest, JobCreated, ValidateRequest
from ..services import ai_service, test_service
from ..services.template_service import os_family_for
from ..services.validation_service import finish, validate_vm
from ..workers.job_runner import JobContext, JobOutcome, create_job, submit
from .plans import get_vm

router = APIRouter(prefix="/api", tags=["validation"])


def validate_member(ctx: JobContext, s, vm: VirtualMachine, env: str, *, simulate_failure: bool = False,
                    port: int | None = None, path: str | None = None) -> dict:
    """Platform checks + security baseline + application tests for one machine; records the verdict."""
    kind = vm.spec.get("kind", "vm")
    ctx.log(f"Validating {vm.name} ({'CT' if kind == 'lxc' else 'VMID'} {vm.vmid}) in {env.upper()}")
    os_family = os_family_for(vm.spec.get("template", ""))
    result = validate_vm(s, vmid=vm.vmid, env=env, health_check_port=port, health_check_path=path,
                         simulate_failure=simulate_failure, log=ctx.log, os_family=os_family, kind=kind)
    tests = test_service.run_suite(s, vm_name=vm.name, env=env, spec=vm.spec, os_family=os_family,
                                   ip=result["ip_address"], job_id=ctx.job_id, log=ctx.log,
                                   mock=not s.live_mode, fail=simulate_failure or s.mock_fail_validation)
    for group, label in (("security_baseline", "Security baseline"), ("app_tests", "Application tests")):
        result["checks"].append({"name": group, "ok": tests["summary"][group]["ok"],
                                 "detail": f"{label}: {tests['summary'][group]['detail']}"})
    result["tests"] = tests["results"]
    result["tests_reviewed"] = tests["approved"]
    current = get_vm(vm.name, env)
    result = finish(result, config_status=current.config_status,
                    profiles=(vm.spec.get("profiles") or []) + (vm.spec.get("packages") or []), log=ctx.log)
    with session_scope() as db:
        row = db.query(VirtualMachine).filter_by(name=vm.name, environment=env).one()
        row.last_validation = result["overall"]
        row.last_validation_at = datetime.now(timezone.utc)
        row.ip_address = result["ip_address"]
    return result


@router.post("/vms/validate", response_model=JobCreated, status_code=202)
def validate(req: ValidateRequest):
    s = get_settings()
    vm = get_vm(req.name, req.environment)
    if not vm:
        raise HTTPException(404, f"VM '{req.name}' is not deployed in {req.environment}. Deploy it first.")
    job_id = create_job(action="validate", environment=req.environment, vm_name=req.name, user=s.app_user,
                        params=req.model_dump())

    def work(ctx: JobContext):
        result = validate_member(ctx, s, vm, req.environment, simulate_failure=req.simulate_failure,
                                 port=req.health_check_port, path=req.health_check_path)
        ctx.update_result(validation=result, summary=f"Validation {result['overall']}")
        if result["overall"] != "PASS":
            failed = ", ".join(c["name"] for c in result["checks"] if not c["ok"])
            ctx.log(f"Failed checks: {failed}. Use Diagnose in the Validation panel for guidance.")
            return JobOutcome(JobStatus.FAILED, f"Validation FAIL: {failed}")
        return f"Validation PASS ({result['ip_address']})"

    submit(job_id, work)
    return JobCreated(job_id=job_id, status="queued")


@router.get("/vms/tests")
def get_suite(name: str, environment: str = "test"):
    """The checks Validate will run for this VM, and whether they were reviewed."""
    s = get_settings()
    vm = get_vm(name, environment)
    if not vm:
        raise HTTPException(404, f"VM '{name}' is not deployed in {environment}.")
    suite = test_service.build_suite(s, name, vm.spec, os_family_for(vm.spec.get("template", "")))
    return {**suite, "suite": test_service.suite_key(name)}


@router.post("/vms/tests/draft")
def draft_tests(req: DraftTestsRequest):
    """Draft application tests (AI or rules). They are used only after a person approves them."""
    s = get_settings()
    vm = get_vm(req.name, req.environment)
    if not vm:
        raise HTTPException(404, f"VM '{req.name}' is not deployed in {req.environment}.")
    ai_call = ai_service.ai_caller(s, f"Write acceptance tests for VM {req.name}.") if s.ai_enabled else None
    return test_service.draft_suite(s, vm_name=req.name, spec=vm.spec, ai_call=ai_call, user=s.app_user)
