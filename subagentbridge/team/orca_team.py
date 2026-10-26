"""Orca team management, worker lifecycle, queue dispatch, and inter-agent coordination.

Implements Lead/Worker separation, per-worker model/harness config, durable task queue,
interrupt preemption, worktree isolation, structured handoffs, and default-deny security.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from subagentbridge.domain.orca_contracts import (
    OrcaRole,
    WorkerStatus,
    QueueTaskStatus,
    WorkerConfig,
    OrcaTeam,
    OrcaSession,
    QueueItem,
    WorktreeAssignment,
    HandoffEvidence,
    ChannelMessage,
)
from subagentbridge.storage.orca_store import OrcaStore


class OrcaTeamManager:
    """Coordinates Lead and Worker sessions with real identity, lifecycle, and queue."""

    def __init__(self, store: OrcaStore) -> None:
        self.store = store

    # ---- Team & Session Lifecycle ----------------------------------------

    def create_team(
        self,
        team_id: str | None = None,
        lead_session_id: str = "",
        title: str = "",
    ) -> OrcaTeam:
        tid = team_id or f"team-{uuid.uuid4().hex[:8]}"
        team = OrcaTeam(team_id=tid, lead_session_id=lead_session_id, title=title)
        self.store.save_team(team)

        # Automatically initialize Lead session
        lead_cfg = WorkerConfig(worker_id=lead_session_id, team_id=tid, role="lead")
        lead_session = OrcaSession(
            session_id=lead_session_id,
            orca_role=OrcaRole.LEAD,
            team_id=tid,
            status=WorkerStatus.IDLE,
            config=lead_cfg,
        )
        self.store.save_session(lead_session)
        return team

    def register_worker(self, config: WorkerConfig) -> OrcaSession:
        return self.create_worker(config.team_id, config)

    def load_team(self, team_id: str) -> OrcaTeam | None:
        return self.store.load_team(team_id)

    def create_worker(
        self,
        team_id: str,
        config: WorkerConfig,
        worktree_path: str | None = None,
        branch_name: str | None = None,
    ) -> OrcaSession:
        team = self.store.load_team(team_id)
        if not team:
            raise ValueError(f"team {team_id!r} not found")

        session = OrcaSession(
            session_id=config.worker_id,
            orca_role=OrcaRole.WORKER,
            team_id=team_id,
            status=WorkerStatus.IDLE,
            config=config,
        )
        self.store.save_session(session)

        if worktree_path:
            assignment = WorktreeAssignment(
                worker_id=config.worker_id,
                team_id=team_id,
                worktree_path=worktree_path,
                branch_name=branch_name or f"worker/{config.worker_id}",
            )
            self.store.save_worktree(assignment)

        return session

    def get_session(self, session_id: str) -> OrcaSession | None:
        return self.store.load_session(session_id)

    def set_worker_status(self, worker_id: str, status: WorkerStatus) -> OrcaSession:
        session = self.store.load_session(worker_id)
        if not session:
            raise KeyError(f"session {worker_id!r} not found")
        session.status = status
        session.updated_at = time.time()
        self.store.save_session(session)
        return session

    def archive_worker(self, worker_id: str) -> OrcaSession:
        return self.set_worker_status(worker_id, WorkerStatus.ARCHIVED)

    def list_workers(self, team_id: str) -> list[OrcaSession]:
        sessions = self.store.list_sessions_by_team(team_id)
        return [s for s in sessions if s.orca_role == OrcaRole.WORKER]

    # ---- Channel Messaging -----------------------------------------------

    def post_message(
        self,
        from_session_id: str,
        to_session_id: str,
        content: str,
    ) -> ChannelMessage:
        sender = self.store.load_session(from_session_id)
        if not sender:
            raise ValueError(f"sender session {from_session_id!r} not found")
        receiver = self.store.load_session(to_session_id)
        if not receiver:
            raise ValueError(f"receiver session {to_session_id!r} not found")
        if sender.team_id != receiver.team_id:
            raise ValueError("cross-team messaging not permitted")

        msg = ChannelMessage(
            message_id=f"msg-{uuid.uuid4().hex[:12]}",
            team_id=sender.team_id,
            from_session_id=from_session_id,
            to_session_id=to_session_id,
            content=content,
            role=sender.orca_role.value,
            created_at=time.time(),
        )
        self.store.save_channel_message(msg)
        return msg

    def read_lead_history(self, session_id: str, limit: int = 50) -> list[ChannelMessage]:
        session = self.store.load_session(session_id)
        if not session:
            raise ValueError(f"session {session_id!r} not found")
        return self.store.list_channel_messages_by_team(session.team_id, limit=limit)

    # ---- Dispatch Queue --------------------------------------------------

    def dispatch_task(
        self,
        from_session_id: str,
        to_session_id: str,
        task_id: str,
        payload: dict[str, Any],
        dedup_key: str | None = None,
        priority: int = 0,
    ) -> QueueItem:
        sender = self.store.load_session(from_session_id)
        receiver = self.store.load_session(to_session_id)
        if not sender:
            raise ValueError(f"sender session {from_session_id!r} not found")
        if not receiver:
            raise ValueError(f"receiver session {to_session_id!r} not found")
        if sender.team_id != receiver.team_id:
            raise ValueError("cross-team dispatch not permitted")

        if dedup_key:
            existing = self.store.find_queue_item_by_dedup(sender.team_id, dedup_key)
            if existing and existing.status not in (
                QueueTaskStatus.FAILED,
                QueueTaskStatus.CANCELLED,
            ):
                return existing

        dispatch_id = f"dsp-{uuid.uuid4().hex[:12]}"
        item = QueueItem(
            dispatch_id=dispatch_id,
            team_id=sender.team_id,
            from_session_id=from_session_id,
            to_session_id=to_session_id,
            task_id=task_id,
            payload=payload,
            status=QueueTaskStatus.PENDING,
            dedup_key=dedup_key,
            priority=priority,
            steering_instructions=[],
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.store.save_queue_item(item)
        return item

    def get_queue_item(self, dispatch_id: str) -> QueueItem | None:
        return self.store.load_queue_item(dispatch_id)

    def fetch_next_pending_task(self, team_id: str, worker_id: str) -> QueueItem | None:
        return self.store.fetch_next_pending_task(team_id, worker_id)

    def update_queue_status(self, dispatch_id: str, status: QueueTaskStatus) -> QueueItem:
        item = self.store.load_queue_item(dispatch_id)
        if not item:
            raise KeyError(f"queue item {dispatch_id!r} not found")
        item.status = status
        item.updated_at = time.time()
        self.store.save_queue_item(item)
        return item

    def steer_task(
        self,
        lead_session_id: str,
        dispatch_id: str,
        guidance: str | dict[str, Any],
    ) -> QueueItem:
        lead = self.store.load_session(lead_session_id)
        if not lead or lead.orca_role != OrcaRole.LEAD:
            raise PermissionError(f"Only lead session can steer tasks: {lead_session_id!r}")
        item = self.store.load_queue_item(dispatch_id)
        if not item:
            raise KeyError(f"queue item {dispatch_id!r} not found")
        if lead.team_id != item.team_id:
            raise PermissionError("cross-team task steering not permitted")
        if item.status not in (
            QueueTaskStatus.PENDING,
            QueueTaskStatus.DISPATCHED,
            QueueTaskStatus.RUNNING,
        ):
            raise ValueError(f"Cannot steer task in terminal status {item.status.value}")

        item.steering_instructions.append({
            "guidance": guidance,
            "steered_by": lead_session_id,
            "timestamp": time.time(),
        })
        item.updated_at = time.time()
        self.store.save_queue_item(item)
        return item

    def cancel_task(
        self,
        lead_session_id: str,
        dispatch_id: str,
        reason: str = "",
    ) -> QueueItem:
        lead = self.store.load_session(lead_session_id)
        if not lead or lead.orca_role != OrcaRole.LEAD:
            raise PermissionError(f"Only lead session can cancel tasks: {lead_session_id!r}")
        item = self.store.load_queue_item(dispatch_id)
        if not item:
            raise KeyError(f"queue item {dispatch_id!r} not found")
        if lead.team_id != item.team_id:
            raise PermissionError("cross-team task cancellation not permitted")

        item.status = QueueTaskStatus.CANCELLED
        if reason:
            item.steering_instructions.append({
                "cancellation_reason": reason,
                "cancelled_by": lead_session_id,
                "timestamp": time.time(),
            })
        item.updated_at = time.time()
        self.store.save_queue_item(item)
        return item

    def list_team_queue(self, team_id: str) -> list[QueueItem]:
        return self.store.list_queue_by_team(team_id)

    def interrupt_worker(self, worker_id: str, reason: str = "") -> bool:
        session = self.store.load_session(worker_id)
        if not session:
            return False

        # Transition worker status
        session.status = WorkerStatus.INTERRUPTED
        session.updated_at = time.time()
        self.store.save_session(session)

        # Preempt active queue items for this worker
        items = self.store.list_queue_by_team(session.team_id)
        for item in items:
            if item.to_session_id == worker_id and item.status in (
                QueueTaskStatus.PENDING,
                QueueTaskStatus.DISPATCHED,
                QueueTaskStatus.RUNNING,
            ):
                item.status = QueueTaskStatus.INTERRUPTED
                if reason:
                    item.steering_instructions.append({
                        "interruption_reason": reason,
                        "timestamp": time.time(),
                    })
                item.updated_at = time.time()
                self.store.save_queue_item(item)

        return True

    # ---- Worktree Management ---------------------------------------------

    def get_worktree_assignment(self, worker_id: str) -> WorktreeAssignment | None:
        return self.store.load_worktree(worker_id)

    # ---- Handoff & Inter-Agent Channels ----------------------------------

    def submit_worker_handoff(self, evidence: HandoffEvidence) -> dict[str, Any]:
        item = self.store.load_queue_item(evidence.dispatch_id)
        if not item:
            raise KeyError(f"dispatch {evidence.dispatch_id!r} not found")

        # Verified handoff binding checks
        if evidence.from_worker_id != item.to_session_id:
            raise PermissionError(
                f"Worker identity mismatch: dispatch {item.dispatch_id!r} assigned to {item.to_session_id!r}, not {evidence.from_worker_id!r}"
            )
        if item.status not in (
            QueueTaskStatus.PENDING,
            QueueTaskStatus.DISPATCHED,
            QueueTaskStatus.RUNNING,
        ):
            raise ValueError(
                f"Cannot accept handoff for item in status {item.status.value}"
            )

        worker = self.store.load_session(evidence.from_worker_id)
        if not worker or worker.status == WorkerStatus.INTERRUPTED:
            raise ValueError(
                f"Worker {evidence.from_worker_id!r} is interrupted or unavailable"
            )

        team = self.store.load_team(item.team_id)
        if not team or team.lead_session_id != evidence.to_lead_id:
            raise PermissionError(
                f"Lead identity mismatch: team lead is {team.lead_session_id if team else None!r}"
            )

        self.store.save_handoff(item.team_id, evidence)

        # Advance queue item to COMPLETED
        item.status = QueueTaskStatus.COMPLETED
        item.updated_at = time.time()
        self.store.save_queue_item(item)

        # Set worker back to IDLE
        worker.status = WorkerStatus.IDLE
        worker.updated_at = time.time()
        self.store.save_session(worker)

        return {"status": "RECEIVED", "dispatch_id": evidence.dispatch_id}

    def list_team_handoffs(self, team_id: str) -> list[HandoffEvidence]:
        return self.store.list_handoffs_by_team(team_id)

    # ---- Security Execution Boundary -------------------------------------

    def execute_worker_command(
        self,
        worker_id: str,
        command: list[str],
        approver: str | None = None,
        approved: bool = False,
    ) -> dict[str, Any]:
        """Enforces default-deny execution policy for worker sessions."""
        session = self.store.load_session(worker_id)
        if not session:
            return {"status": "DENIED", "reason": f"session {worker_id!r} not found"}

        if not approved or not approver:
            return {
                "status": "DENIED",
                "worker_id": worker_id,
                "command": command,
                "reason": "Default-deny: unapproved command execution blocked by policy",
            }

        return {
            "status": "APPROVED",
            "worker_id": worker_id,
            "command": command,
            "approver": approver,
            "approved_at": time.time(),
        }


# Upstream Cindy / Orca parity alias
OrcaTeamService = OrcaTeamManager
