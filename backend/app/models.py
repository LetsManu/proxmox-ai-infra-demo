from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    environment: Mapped[str] = mapped_column(String(16), index=True)
    vm_name: Mapped[str] = mapped_column(String(64), index=True)
    user: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    logs: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class VirtualMachine(Base):
    """Desired state of every VM managed through this console.

    The Terraform/OpenTofu configuration for an environment is generated from
    these rows, so the table is the single source of truth for `var.vms`.
    """

    __tablename__ = "virtual_machines"
    __table_args__ = (UniqueConstraint("name", "environment", name="uq_vm_name_env"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16))
    vmid: Mapped[int] = mapped_column(Integer)
    node: Mapped[str] = mapped_column(String(64))
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_validation: Mapped[str | None] = mapped_column(String(8), nullable=True)  # PASS / FAIL
    last_validation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # success / failed / skipped
    configured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class HistoryEntry(Base):
    __tablename__ = "history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    vm_name: Mapped[str] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    user: Mapped[str] = mapped_column(String(64))
    plan_summary: Mapped[str] = mapped_column(Text, default="")
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
