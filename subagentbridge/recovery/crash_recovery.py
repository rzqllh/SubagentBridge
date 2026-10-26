"""Crash recovery and worker state reconciliation.

Recovers team sessions, queues, and worker process states across orchestrator
restarts without assuming false execution completion.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from subagentbridge.domain.orca_contracts import (
    OrcaRole,
    OrcaSession,
    QueueTaskStatus,
    WorkerCheckpoint,
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
    """Resumes a worker session from its latest checkpoint, restoring cumulative tokens and worktree binding."""
    session = store.load_session(worker_id)
    if not session:
        raise KeyError(f"worker session {worker_id!r} not found")

    # Restore cumulative tokens from latest checkpoint
    latest_cp = store.load_latest_checkpoint(worker_id)
    if latest_cp:
        session.config = replace(session.config, tokens_consumed=latest_cp.tokens_consumed)

    # Recover worktree ownership provenance if assigned
    wt = store.load_worktree(worker_id)
    worktree_path: str | None = None
    if wt:
        wt_path = Path(wt.worktree_path)
        if wt_path.exists() and wt_path.is_dir():
            worktree_path = str(wt_path)
            session.config = replace(session.config, working_dir=worktree_path)

    if controller:
        record = controller.spawn_worker(session.config, worktree_path=worktree_path)
        session.config = replace(
            session.config,
            pid=record.pid,
            process_create_time=record.create_time,
        )
        session.status = WorkerStatus.IDLE
        session.updated_at = time.time()
        store.save_session(session)

    return session


def resume_task_from_checkpoint(
    dispatch_id: str,
    store: OrcaStore,
    controller: WorkerProcessController,
    approval_authority: Any | None = None,
) -> dict[str, Any]:
    """Resumes an interrupted queue task from its checkpoint, avoiding duplicate execution.

    Distinguishes worker restart (rehydrating the process + token budget) from task resume
    (continuing the logical work without repeating completed side effects).
    Recovers worktree binding, commit identity, skipped steps from checkpoint context,
    revalidates approvals, executes remaining steps, and updates durable state.
    """
    item = store.load_queue_item(dispatch_id)
    if not item:
        raise KeyError(f"queue item {dispatch_id!r} not found")

    worker_id = item.to_session_id
    if not controller.is_worker_alive(worker_id):
        session = resume_worker_from_checkpoint(worker_id, store=store, controller=controller)
    else:
        loaded = store.load_session(worker_id)
        if not loaded:
            raise KeyError(f"worker session {worker_id!r} not found")
        session = loaded

    # Verify worktree ownership and exact commit identity
    wt = store.load_worktree(worker_id)
    worktree_path = wt.worktree_path if wt and Path(wt.worktree_path).exists() else session.config.working_dir

    current_commit: str | None = None
    if worktree_path and Path(worktree_path).exists():
        rev_res = subprocess.run(
            ["git", "-C", str(worktree_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        if rev_res.returncode == 0:
            current_commit = rev_res.stdout.strip()

    # Strict Checkpoint Binding Audit:
    # A checkpoint must match the exact team, worker, dispatch, task, and commit.
    latest_cp = store.load_latest_checkpoint(worker_id)
    completed_steps: list[str] = []
    is_valid_checkpoint = False

    if latest_cp and latest_cp.context_snapshot:
        cp_snap = latest_cp.context_snapshot
        cp_disp = cp_snap.get("dispatch_id")
        cp_task = cp_snap.get("task_id")
        cp_commit = cp_snap.get("commit_hash")

        # Disallow checkpoints from other tasks or dispatches
        if cp_disp == item.dispatch_id and cp_task == item.task_id and latest_cp.team_id == session.team_id:
            # If commit was tracked, verify tree has not diverged
            if cp_commit is None or current_commit is None or cp_commit == current_commit:
                is_valid_checkpoint = True

    if is_valid_checkpoint and latest_cp and latest_cp.context_snapshot:
        completed_steps = list(latest_cp.context_snapshot.get("completed_steps", []))
    else:
        latest_cp = None
        completed_steps = []

    payload = dict(item.payload)
    steps = payload.get("steps")
    expected_artifacts = payload.get("expected_artifacts", [])

    if isinstance(steps, list):
        # Bounded multi-step workflow: skip already completed steps (idempotent continuation)
        remaining_steps = [s for s in steps if s.get("name") not in completed_steps]

        # Never mark COMPLETED merely because checkpoint claims steps finished without validating evidence
        if not remaining_steps:
            missing_evidence = False
            if expected_artifacts and worktree_path:
                for art in expected_artifacts:
                    if not (Path(worktree_path) / art).exists():
                        missing_evidence = True
                        break

            if missing_evidence:
                # Evidence missing: reset completed steps and re-execute safely (at-least-once recoverable)
                remaining_steps = list(steps)
                completed_steps = []
            else:
                item.status = QueueTaskStatus.COMPLETED
                item.updated_at = time.time()
                store.save_queue_item(item)
                return {
                    "status": "COMPLETED",
                    "summary": "All steps already completed in checkpoint and verified against evidence",
                    "completed_steps": completed_steps,
                    "skipped_steps": completed_steps,
                    "tokens_consumed": session.config.tokens_consumed,
                    "execution_classification": "IDEMPOTENT_RESUME",
                }

        item.status = QueueTaskStatus.RUNNING
        item.updated_at = time.time()
        store.save_queue_item(item)

        current_tokens = latest_cp.tokens_consumed if latest_cp else session.config.tokens_consumed
        step_idx = latest_cp.step_index if latest_cp else 0

        for step in remaining_steps:
            step_name = step.get("name", f"step_{step_idx + 1}")
            step_idx += 1
            step_payload = dict(step)
            if worktree_path:
                step_payload["workspace_path"] = worktree_path

            # Revalidate approval ticket if step is a command
            if "command" in step_payload and approval_authority:
                action = approval_authority.request_command_approval(
                    worker_id=worker_id,
                    task_id=f"{item.task_id}-{step_name}",
                    command=step_payload["command"] if isinstance(step_payload["command"], list) else [step_payload["command"]],
                    workspace_path=worktree_path or "",
                )
                step_payload["approval_action_id"] = action.action_id

            res = controller.dispatch_task_to_worker(worker_id, f"{item.task_id}-{step_name}", step_payload)
            if res.get("status") != "COMPLETED":
                item.status = QueueTaskStatus.FAILED
                item.updated_at = time.time()
                store.save_queue_item(item)
                return {
                    "status": "FAILED",
                    "error": res.get("error", "Step execution failed"),
                    "failed_step": step_name,
                    "completed_steps": completed_steps,
                }

            completed_steps.append(step_name)
            metered = int(res.get("metered_tokens", 0))
            current_tokens += metered

            # Persist checkpoint after each successfully completed step
            cp = WorkerCheckpoint(
                checkpoint_id=f"cp-{item.dispatch_id}-{step_idx}",
                worker_id=worker_id,
                team_id=session.team_id,
                step_index=step_idx,
                state_summary=f"Completed {step_name}",
                tokens_consumed=current_tokens,
                context_snapshot={
                    "dispatch_id": item.dispatch_id,
                    "task_id": item.task_id,
                    "completed_steps": completed_steps,
                    "worktree_path": worktree_path,
                    "commit_hash": current_commit,
                },
            )
            store.save_checkpoint(cp)

        item.status = QueueTaskStatus.COMPLETED
        item.updated_at = time.time()
        store.save_queue_item(item)
        return {
            "status": "COMPLETED",
            "dispatch_id": item.dispatch_id,
            "task_id": item.task_id,
            "completed_steps": completed_steps,
            "skipped_steps": [s.get("name") for s in steps if s.get("name") not in [r.get("name") for r in remaining_steps]],
            "tokens_consumed": current_tokens,
            "worktree_path": worktree_path,
        }

    # Single-instruction or atomic command payload
    if latest_cp and latest_cp.context_snapshot.get("completed"):
        # Check evidence if declared
        ev_missing = False
        if expected_artifacts and worktree_path:
            for art in expected_artifacts:
                if not (Path(worktree_path) / art).exists():
                    ev_missing = True
                    break
        if not ev_missing:
            item.status = QueueTaskStatus.COMPLETED
            item.updated_at = time.time()
            store.save_queue_item(item)
            return {"status": "COMPLETED", "summary": "Task was completed before crash and verified"}

    item.status = QueueTaskStatus.RUNNING
    item.updated_at = time.time()
    store.save_queue_item(item)

    if worktree_path:
        payload["workspace_path"] = worktree_path

    res = controller.dispatch_task_to_worker(worker_id, item.task_id, payload)
    if res.get("status") == "COMPLETED":
        item.status = QueueTaskStatus.COMPLETED
    else:
        item.status = QueueTaskStatus.FAILED
    item.updated_at = time.time()
    store.save_queue_item(item)
    return res
