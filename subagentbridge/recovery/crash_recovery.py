"""Crash recovery and worker state reconciliation.

Recovers team sessions, queues, and worker process states across orchestrator
restarts without assuming false execution completion.
"""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from subagentbridge.domain.orca_contracts import (
    OrcaRole,
    OrcaSession,
    QueueTaskStatus,
    WorkerStatus,
)
from subagentbridge.execution.worker_process import (
    WorkerProcessController,
    is_process_identically_alive,
)
from subagentbridge.storage.orca_store import OrcaStore


def reconcile_team_after_crash(team_id: str, store: OrcaStore) -> dict[str, Any]:
    """Reconciles worker session and queue states for a team following a crash.

    Audits all worker sessions against real OS process tables. Workers whose
    processes have terminated are transitioned to FAILED, and any in-flight
    queue items are transitioned to FAILED (never assumed COMPLETED).
    """
    sessions = store.list_sessions_by_team(team_id)
    dead_workers: list[str] = []

    for session in sessions:
        if session.orca_role != OrcaRole.WORKER:
            continue

        pid = session.config.pid
        create_time = session.config.process_create_time

        # If PID was recorded and process is dead, or if status was RUNNING but PID dead
        is_alive = False
        if pid is not None and pid > 0:
            is_alive = is_process_identically_alive(pid, create_time)

        if not is_alive:
            if session.status in (WorkerStatus.RUNNING, WorkerStatus.PAUSED, WorkerStatus.IDLE):
                session.status = WorkerStatus.FAILED
                session.updated_at = time.time()
                store.save_session(session)
                dead_workers.append(session.session_id)

                # Transition in-flight queue tasks assigned to this dead worker to FAILED
                items = store.list_queue_by_team(team_id)
                for item in items:
                    if item.to_session_id == session.session_id and item.status in (
                        QueueTaskStatus.PENDING,
                        QueueTaskStatus.DISPATCHED,
                        QueueTaskStatus.RUNNING,
                    ):
                        item.status = QueueTaskStatus.FAILED
                        item.updated_at = time.time()
                        store.save_queue_item(item)

    return {
        "team_id": team_id,
        "reconciled_workers": len(dead_workers),
        "dead_workers": dead_workers,
    }


def resume_worker_from_checkpoint(
    worker_id: str,
    store: OrcaStore,
    controller: WorkerProcessController | None = None,
) -> OrcaSession:
    """Resumes a worker session from its latest checkpoint, restoring cumulative tokens."""
    session = store.load_session(worker_id)
    if not session:
        raise KeyError(f"worker session {worker_id!r} not found")

    latest_cp = store.load_latest_checkpoint(worker_id)
    if latest_cp:
        session.config = replace(session.config, tokens_consumed=latest_cp.tokens_consumed)

    if controller:
        record = controller.spawn_worker(session.config)
        session.config = replace(
            session.config,
            pid=record.pid,
            process_create_time=record.create_time,
        )
        session.status = WorkerStatus.IDLE
        session.updated_at = time.time()
        store.save_session(session)

    return session
