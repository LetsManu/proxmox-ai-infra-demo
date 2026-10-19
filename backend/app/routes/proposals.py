"""Review queue: AI-drafted roles and test suites wait here for a person."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..auth import actor, require_role
from ..config import get_settings
from ..services import proposal_service

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


@router.get("")
def list_proposals(kind: str | None = None, target: str | None = None,
                   status: str | None = Query(None, pattern="^(pending|approved|rejected|superseded)$")):
    return proposal_service.list_(kind=kind, target=target, status=status)


@router.get("/{pid}")
def get_proposal(pid: str):
    p = proposal_service.get(pid)
    if not p:
        raise HTTPException(404, "Proposal not found")
    return p


def _decide(pid: str, approve: bool):
    require_role("approver")  # AI-drafted roles and tests are used only after an approver accepts them
    s = get_settings()
    who = actor()  # captured now: jobs run in worker threads
    try:
        return proposal_service.decide(s, pid, approve, who)
    except KeyError as exc:
        raise HTTPException(404, "Proposal not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{pid}/approve")
def approve(pid: str):
    return _decide(pid, True)


@router.post("/{pid}/reject")
def reject(pid: str):
    return _decide(pid, False)
