"""Simpul native team management, worker lifecycle, queue dispatch, and inter-agent coordination.

Implements Lead/Worker separation, per-worker model/harness config, durable task queue,
interrupt preemption, worktree isolation, structured handoffs, and default-deny security.
"""
from __future__ import annotations

import hashlib
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from subagentbridge.domain.team_contracts import (
    AgentRole,
    AgentSession,
    AgentTeam,
    ChannelMessage,
    HandoffEvidence,
    QueueItem,
    QueueTaskStatus,
    WorkerConfig,
    WorkerStatus,
    WorktreeAssignment,
)
from subagentbridge.storage.team_store import TeamStore


class TeamManager:
    """Coordinates Lead and Worker sessions with real identity, lifecycle, and queue."""

    def __init__(self, store: TeamStore) -> None:
        self.store = store
        self._lock = threading.Lock()

    # ---- Team & Session Lifecycle ----------------------------------------

    def create_team(
        self,
        team_id: str | None = None,
        lead_session_id: str = "",
        title: str = "",
    ) -> AgentTeam:
        tid = team_id or f"team-{uuid.uuid4().hex[:8]}"
        team = AgentTeam(team_id=tid, lead_session_id=lead_session_id, title=title)
        self.store.save_team(team)

        # Automatically initialize Lead session
        lead_cfg = WorkerConfig(worker_id=lead_session_id, team_id=tid, role="lead")
        lead_session = AgentSession(
            session_id=lead_session_id,
            role=AgentRole.LEAD,
            team_id=tid,
            status=WorkerStatus.IDLE,
            config=lead_cfg,
        )
        self.store.save_session(lead_session)
        return team

    def register_worker(self, config: WorkerConfig) -> AgentSession:
        return self.create_worker(config.team_id, config)

    def load_team(self, team_id: str) -> AgentTeam | None:
        return self.store.load_team(team_id)

    def create_worker(
        self,
        team_id: str,
        config: WorkerConfig,
        worktree_path: str | None = None,
        branch_name: str | None = None,
    ) -> AgentSession:
        team = self.store.load_team(team_id)
        if not team:
            raise ValueError(f"team {team_id!r} not found")

        session = AgentSession(
            session_id=config.worker_id,
            role=AgentRole.WORKER,
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

    def get_session(self, session_id: str) -> AgentSession | None:
        return self.store.load_session(session_id)

    def set_worker_status(self, worker_id: str, status: WorkerStatus) -> AgentSession:
        session = self.store.load_session(worker_id)
        if not session:
            raise KeyError(f"session {worker_id!r} not found")
        session.status = status
        session.updated_at = time.time()
        self.store.save_session(session)
        return session

    def archive_worker(self, worker_id: str) -> AgentSession:
        return self.set_worker_status(worker_id, WorkerStatus.ARCHIVED)

    def list_workers(self, team_id: str) -> list[AgentSession]:
        sessions = self.store.list_sessions_by_team(team_id)
        return [s for s in sessions if s.role == AgentRole.WORKER]

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
            role=sender.role.value if isinstance(sender.role, AgentRole) else str(sender.role),
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

        # The store performs lookup and insertion in one BEGIN IMMEDIATE transaction.
        # An in-memory preflight lookup here would race across orchestrator processes.
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
        return self.store.dispatch_or_get_existing(item)

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
        if not lead or lead.role != AgentRole.LEAD:
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
        if not lead or lead.role != AgentRole.LEAD:
            raise PermissionError(f"Only lead session can cancel tasks: {lead_session_id!r}")
        item = self.store.load_queue_item(dispatch_id)
        if not item:
            raise KeyError(f"queue item {dispatch_id!r} not found")
        if lead.team_id != item.team_id:
            raise PermissionError("cross-team task cancellation not permitted")

        return self.store.cancel_queue_if_active(dispatch_id, lead.team_id, lead_session_id, reason)

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

    def submit_worker_handoff(
        self,
        evidence: HandoffEvidence,
        verify_artifacts: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            item = self.store.load_queue_item(evidence.dispatch_id)
            if not item:
                raise KeyError(f"dispatch {evidence.dispatch_id!r} not found")

            # Verified handoff binding checks
            if evidence.from_worker_id != item.to_session_id:
                raise PermissionError(
                    f"Worker identity mismatch: dispatch {item.dispatch_id!r} assigned to {item.to_session_id!r}, not {evidence.from_worker_id!r}"
                )
            if item.status == QueueTaskStatus.PENDING:
                raise ValueError("Cannot accept handoff for pending task: execution has not started")
            if item.status not in (
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

            # Replay protection: cannot submit duplicate handoff for already finalized dispatch
            existing_handoffs = self.store.list_handoffs_by_team(item.team_id)
            if any(h.dispatch_id == evidence.dispatch_id for h in existing_handoffs):
                raise ValueError(f"Handoff already finalized for dispatch {evidence.dispatch_id!r}")

            # Disallow bypass of artifact verification for successful handoffs
            if evidence.status in ("SUCCESS", "PASSED") and not verify_artifacts:
                raise PermissionError(
                    "Bypassing artifact verification (verify_artifacts=False) is forbidden for successful handoffs"
                )

            # Reject empty/fabricated success evidence
            if evidence.status in ("SUCCESS", "PASSED"):
                if not evidence.summary or not evidence.summary.strip():
                    raise ValueError("Handoff rejected: summary must be non-empty for successful handoffs")
                if not evidence.metrics:
                    raise ValueError("Handoff rejected: metrics must be non-empty for successful handoffs")

            # Artifact existence, symlink check, containment, and SHA256 verification
            if evidence.artifacts:
                wt = self.store.load_worktree(evidence.from_worker_id)
                base_dir = Path(wt.worktree_path) if wt and Path(wt.worktree_path).exists() else (
                    Path(worker.config.working_dir) if worker.config.working_dir and Path(worker.config.working_dir).exists() else None
                )
                if not base_dir:
                    raise ValueError(f"Worker {evidence.from_worker_id!r} has no verified workspace or worktree for artifact verification")

                if base_dir.is_symlink():
                    raise PermissionError(f"Workspace directory {base_dir} is a symlink, refusing verification")

                base_dir_resolved = base_dir.resolve()
                for art in evidence.artifacts:
                    raw_art_path = base_dir / art

                    # Raw symlink check BEFORE resolve (reject links pointing inside or outside workspace)
                    if raw_art_path.is_symlink():
                        raise PermissionError(f"Handoff artifact {art!r} is a symlink, refusing verification")

                    # Check each intermediate path component between base_dir and raw_art_path
                    cur = raw_art_path
                    while cur != base_dir and cur != cur.parent:
                        if cur.is_symlink():
                            raise PermissionError(f"Handoff artifact path component {cur!r} is a symlink, refusing verification")
                        cur = cur.parent

                    art_path = raw_art_path.resolve()
                    try:
                        art_path.relative_to(base_dir_resolved)
                    except ValueError:
                        raise PermissionError(f"Handoff artifact path escape detected: {art!r} resolves outside workspace")

                declared_hashes = evidence.metrics.get("artifact_hashes")
                if not isinstance(declared_hashes, dict):
                    raise ValueError("Handoff rejected: 'artifact_hashes' mapping is required when artifacts are declared")

                for art in evidence.artifacts:
                    if art not in declared_hashes or not declared_hashes[art]:
                        raise ValueError(f"Handoff rejected: missing required SHA256 hash for declared artifact {art!r}")
                    expected_hash = declared_hashes[art]
                    if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected_hash):
                        raise ValueError(f"Handoff rejected: invalid SHA256 hash format for artifact {art!r}")

                    art_path = (base_dir / art).resolve()
                    if not art_path.exists() or not art_path.is_file():
                        raise FileNotFoundError(f"Handoff rejected: declared artifact {art!r} does not exist on disk")

                    h = hashlib.sha256(art_path.read_bytes()).hexdigest()
                    if h.lower() != declared_hashes[art].lower():
                        raise ValueError(f"Handoff rejected: hash mismatch for artifact {art!r}")

            # Execution receipt check: require genuine trusted execution receipts and QA verdict
            if evidence.status in ("SUCCESS", "PASSED"):
                receipt_id = evidence.metrics.get("receipt_id")
                exec_receipt = evidence.metrics.get("execution_receipt")
                if isinstance(exec_receipt, dict):
                    receipt_id = receipt_id or exec_receipt.get("receipt_id")
                    if "exit_code" in exec_receipt and evidence.metrics.get("exit_code") is None:
                        evidence.metrics["exit_code"] = exec_receipt["exit_code"]

                if not receipt_id or not isinstance(receipt_id, str) or not receipt_id.strip():
                    raise ValueError("Handoff rejected: missing genuine trusted execution receipt ('receipt_id' or 'execution_receipt')")

                exit_code = evidence.metrics.get("exit_code")
                if exit_code is None and isinstance(exec_receipt, dict):
                    exit_code = exec_receipt.get("exit_code")

                if exit_code is None:
                    raise ValueError("Handoff rejected: missing required execution receipt ('exit_code') in metrics")
                if exit_code != 0:
                    raise ValueError(f"Handoff rejected: execution receipt indicates non-zero exit code ({exit_code})")

                qa_verdict = evidence.metrics.get("qa_verdict")
                if qa_verdict is None or qa_verdict not in ("PASS", "VERIFIED"):
                    raise ValueError(f"Handoff rejected: QA verdict must be 'PASS' or 'VERIFIED', got {qa_verdict!r}")

            # Keep contract-only tests separate from verified completed execution
            if evidence.status in ("CONTRACT_FIXTURE", "CONTRACT_ONLY"):
                new_status = None  # Do not advance queue item to COMPLETED
                ret_status = "CONTRACT_VERIFIED"
            else:
                new_status = QueueTaskStatus.COMPLETED
                ret_status = "RECEIVED"

            # Durable transaction-level finalization and replay protection
            self.store.finalize_handoff_transaction(
                item.team_id,
                evidence,
                new_queue_status=new_status,
            )

            return {"status": ret_status, "dispatch_id": evidence.dispatch_id}

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


# Compatibility aliases
OrcaTeamManager = TeamManager
OrcaTeamService = TeamManager
