"""Domain contracts and data types for Simpul native agent coordination.

Implements Lead/Worker distinct sessions, status lifecycles, worker configurations,
durable queue items, worktree assignments, and structured handoff evidence.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    LEAD = "lead"
    WORKER = "worker"


# Backward-compatibility alias
OrcaRole = AgentRole


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
    AMBIGUOUS = "AMBIGUOUS"


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
    process_create_time: float | None = None
    tokens_consumed: int = 0
    fallback_to_native: bool = False


@dataclass
class AgentTeam:
    team_id: str
    lead_session_id: str
    title: str
    created_at: float = field(default_factory=time.time)


# Backward-compatibility alias
OrcaTeam = AgentTeam


@dataclass
class AgentSession:
    session_id: str
    role: AgentRole
    team_id: str
    status: WorkerStatus = WorkerStatus.IDLE
    config: WorkerConfig = field(default_factory=lambda: WorkerConfig(worker_id="", team_id=""))
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __init__(
        self,
        session_id: str,
        role: AgentRole | None = None,
        team_id: str = "",
        status: WorkerStatus = WorkerStatus.IDLE,
        config: WorkerConfig | None = None,
        created_at: float | None = None,
        updated_at: float | None = None,
        *,
        orca_role: AgentRole | None = None,
    ) -> None:
        self.session_id = session_id
        assigned_role = role if role is not None else (orca_role if orca_role is not None else AgentRole.WORKER)
        self.role = assigned_role
        self.team_id = team_id
        self.status = status
        self.config = config if config is not None else WorkerConfig(worker_id="", team_id="")
        now = time.time()
        self.created_at = created_at if created_at is not None else now
        self.updated_at = updated_at if updated_at is not None else now

    @property
    def orca_role(self) -> AgentRole:
        return self.role

    @orca_role.setter
    def orca_role(self, val: AgentRole) -> None:
        self.role = val


# Backward-compatibility alias
OrcaSession = AgentSession


@dataclass
class QueueItem:
    dispatch_id: str
    team_id: str
    from_session_id: str
    to_session_id: str
    task_id: str
    payload: dict[str, Any]
    status: QueueTaskStatus = QueueTaskStatus.PENDING
    dedup_key: str | None = None
    priority: int = 0
    steering_instructions: list[dict[str, Any]] = field(default_factory=list)
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


@dataclass
class ChannelMessage:
    message_id: str
    team_id: str
    from_session_id: str
    to_session_id: str
    content: str
    role: str
    created_at: float = field(default_factory=time.time)


@dataclass
class WorkerCheckpoint:
    checkpoint_id: str
    worker_id: str
    team_id: str
    step_index: int
    state_summary: str
    tokens_consumed: int
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
