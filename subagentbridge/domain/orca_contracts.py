"""Domain contracts and data types for Cindy/Orca orchestration-core parity.

Implements Lead/Worker distinct sessions, status lifecycles, worker configurations,
durable queue items, worktree assignments, and structured handoff evidence.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OrcaRole(str, Enum):
    LEAD = "lead"
    WORKER = "worker"


class WorkerStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    INTERRUPTED = "INTERRUPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class QueueTaskStatus(str, Enum):
    PENDING = "PENDING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    INTERRUPTED = "INTERRUPTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class WorkerConfig:
    worker_id: str
    team_id: str
    role: str = "worker"
    harness: str = "native"
    model: str | None = None
    provider: str | None = None
    system_prompt: str | None = None
    working_dir: str | None = None
    effort: str | None = None
    budget_tokens: int | None = None
    pid: int | None = None


@dataclass
class OrcaTeam:
    team_id: str
    lead_session_id: str
    title: str
    created_at: float = field(default_factory=time.time)


@dataclass
class OrcaSession:
    session_id: str
    orca_role: OrcaRole
    team_id: str
    status: WorkerStatus = WorkerStatus.IDLE
    config: WorkerConfig = field(default_factory=lambda: WorkerConfig(worker_id="", team_id=""))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class QueueItem:
    dispatch_id: str
    team_id: str
    from_session_id: str
    to_session_id: str
    task_id: str
    payload: dict[str, Any]
    status: QueueTaskStatus = QueueTaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class WorktreeAssignment:
    worker_id: str
    team_id: str
    worktree_path: str
    branch_name: str
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class HandoffEvidence:
    dispatch_id: str
    from_worker_id: str
    to_lead_id: str
    status: str
    summary: str
    artifacts: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    submitted_at: float = field(default_factory=time.time)
