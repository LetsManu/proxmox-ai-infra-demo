"""Background job execution.

Long-running work (plan, apply, validation, template builds) runs in a small
thread pool. Each job's status, logs and result are persisted to the database
so the browser can poll `GET /api/jobs/{id}`. Plan/apply jobs for the same
environment are serialised with a per-environment lock (one writer per
Terraform state).
"""

from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from ..database import session_scope
from ..models import HistoryEntry, Job, JobStatus

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="job")
_env_locks = {"test": threading.Lock(), "prod": threading.Lock()}


class JobContext:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self._buffer: list[str] = []
        self._lock = threading.Lock()

    def log(self, line: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        with self._lock:
            with session_scope() as db:
                job = db.get(Job, self.job_id)
                job.logs = (job.logs or "") + f"[{stamp}] {line}\n"

    def update_result(self, **values) -> None:
        with session_scope() as db:
            job = db.get(Job, self.job_id)
            job.result = {**(job.result or {}), **values}


class JobOutcome:
    """Returned by a job function to finish in a status other than success."""

    def __init__(self, status: str, summary: str = ""):
        self.status = status
        self.summary = summary


def create_job(*, action: str, environment: str, vm_name: str, user: str, params: dict,
               status: str = JobStatus.QUEUED) -> str:
    with session_scope() as db:
        job = Job(action=action, environment=environment, vm_name=vm_name, user=user,
                  params=params, status=status, result={}, logs="")
        db.add(job)
        db.flush()
        return job.id


def add_history(*, vm_name: str, environment: str, action: str, status: str, user: str,
                plan_summary: str = "", job_id: str | None = None) -> None:
    with session_scope() as db:
        db.add(HistoryEntry(vm_name=vm_name, environment=environment, action=action, status=status,
                            user=user, plan_summary=plan_summary, job_id=job_id))


def _set_status(job_id: str, status: str, error: str | None = None) -> Job:
    with session_scope() as db:
        job = db.get(Job, job_id)
        job.status = status
        if error is not None:
            job.error = error
        db.flush()
        db.expunge(job)
        return job


def submit(job_id: str, fn: Callable[[JobContext], JobOutcome | str | None], *, env_lock: str | None = None) -> None:
    def run():
        ctx = JobContext(job_id)
        lock = _env_locks.get(env_lock) if env_lock else None
        try:
            if lock and not lock.acquire(blocking=False):
                ctx.log(f"Waiting for another {env_lock.upper()} operation to finish (state lock)...")
                lock.acquire()
            _set_status(job_id, JobStatus.RUNNING)
            outcome = fn(ctx)
            if isinstance(outcome, JobOutcome):
                status, summary = outcome.status, outcome.summary
            else:
                status, summary = JobStatus.SUCCESS, outcome or ""
            job = _set_status(job_id, status)
            add_history(vm_name=job.vm_name, environment=job.environment, action=job.action, status=status,
                        user=job.user, plan_summary=summary or (job.result or {}).get("summary", ""), job_id=job_id)
        except Exception as exc:  # noqa: BLE001 - every failure must surface in the job log
            ctx.log(f"ERROR: {exc}")
            ctx.log(traceback.format_exc(limit=3).strip().splitlines()[-1])
            job = _set_status(job_id, JobStatus.FAILED, error=str(exc))
            add_history(vm_name=job.vm_name, environment=job.environment, action=job.action,
                        status=JobStatus.FAILED, user=job.user, plan_summary=str(exc)[:300], job_id=job_id)
        finally:
            if lock and lock.locked():
                lock.release()

    _executor.submit(run)


def recover_interrupted_jobs() -> None:
    """Jobs that were running when the backend stopped can never finish; mark them failed."""
    with session_scope() as db:
        for job in db.query(Job).filter(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])):
            job.status = JobStatus.FAILED
            job.error = "Backend restarted while the job was running"
