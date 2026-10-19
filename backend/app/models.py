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


class Proposal(Base):
    """Something the AI drafted that a person must review before it is used:
    an Ansible role (new software profile), a test suite, or a stack architecture."""

    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    kind: Mapped[str] = mapped_column(String(16), index=True)  # role | tests | stack
    name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|rejected
    target: Mapped[str] = mapped_column(String(128), default="")  # e.g. "test/demo-web-test" for tests
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    review: Mapped[dict] = mapped_column(JSON, default=dict)  # automated safety checks
    source: Mapped[str] = mapped_column(String(64), default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Stack(Base):
    """A set of VMs / LXC containers (and Docker services on them) deployed and promoted together."""

    __tablename__ = "stacks"
    __table_args__ = (UniqueConstraint("name", "environment", name="uq_stack_name_env"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(64), index=True)
    environment: Mapped[str] = mapped_column(String(16), index=True)
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    members: Mapped[list] = mapped_column(JSON, default=list)  # full machine names
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_validation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    """A signed-in browser. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(256), default="")
    roles: Mapped[list] = mapped_column(JSON, default=list)
    csrf: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
