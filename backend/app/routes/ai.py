"""AI assistance endpoints. Advisory only: none of these can deploy, approve or promote."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..schemas import GenerateSpecRequest, SummarizePlanRequest, TroubleshootRequest
from ..services import ai_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/summarize-plan")
def summarize_plan(req: SummarizePlanRequest):
    return ai_service.summarize_plan(get_settings(), req.plan_text, req.environment)


@router.post("/generate-vm-spec")
def generate_vm_spec(req: GenerateSpecRequest):
    try:
        return ai_service.generate_vm_spec(get_settings(), req.prompt)
    except ai_service.SpecRejected as exc:
        raise HTTPException(422, {"message": "Generated spec rejected by safety validation",
                                  "errors": exc.errors, "draft": exc.spec}) from exc


@router.post("/troubleshoot")
def troubleshoot(req: TroubleshootRequest):
    return ai_service.troubleshoot(get_settings(), req.vm_name, req.job_logs, req.validation_output,
                                   req.proxmox_status)
