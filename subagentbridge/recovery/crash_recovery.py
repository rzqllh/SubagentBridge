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

from subagentbridge.domain.team_contracts import (
    AgentRole,
    AgentSession,
    QueueTaskStatus,
    WorkerCheckpoint,
    WorkerStatus,
)
from subagentbridge.execution.worker_process import (
    WorkerProcessController,
    is_process_identically_alive,
)
from subagentbridge.storage.team_store import TeamStore


def reconcile_team_after_crash(team_id: str, store: TeamStore) -> dict[str, Any]:
    """Reconciles worker session and queue states for a team following a crash.

    Audits all worker sessions against real OS process tables. Workers whose
    processes have terminated are transitioned to FAILED, and any in-flight
    queue items are transitioned to FAILED (never assumed COMPLETED).
    """
    sessions = store.list_sessions_by_team(team_id)
    dead_workers: list[str] = []

    for session in sessions:
        if session.role != AgentRole.WORKER:
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
    store: TeamStore,
    controller: WorkerProcessController | None = None,
) -> AgentSession:
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
    store: TeamStore,
    controller: WorkerProcessController,
    approval_authority: Any | None = None,
) -> dict[str, Any]:
    """Resumes an interrupted queue task from its checkpoint, avoiding duplicate execution.

    Distinguishes worker restart (rehydrating the process + token budget) from task resume
    (continuing the logical work without repeating completed side effects).
    Recovers worktree binding, commit identity, skipped steps from checkpoint context,
    revalidates approvals, executes remaining steps, and updates durable state.
    """
    # A process visible in the OS is not necessarily attached to this controller.
    # Never launch a replacement or dispatch to an orphan whose pipes we do not own.
    pre_item = store.load_queue_item(dispatch_id)
    if pre_item and controller.is_worker_alive(pre_item.to_session_id) and not controller.is_worker_dispatchable(pre_item.to_session_id):
        return {
            "status": "RECOVERY_BLOCKED",
            "dispatch_id": dispatch_id,
            "reason": "Worker PID is alive but this controller has no attached IPC; operator reconciliation required",
        }

    # Enforce atomic resume transition to prevent concurrent or duplicate resume
    item = store.mark_task_resuming(dispatch_id)

    worker_id = item.to_session_id
    if not controller.is_worker_dispatchable(worker_id):
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
    # A checkpoint must match the exact team, worker, dispatch, task, and verified non-empty matching commit.
    latest_cp = store.load_latest_checkpoint(worker_id)
    completed_steps: list[str] = []
    is_valid_checkpoint = False

    if latest_cp and latest_cp.context_snapshot:
        cp_snap = latest_cp.context_snapshot
        cp_disp = cp_snap.get("dispatch_id")
        cp_task = cp_snap.get("task_id")
        cp_commit = cp_snap.get("commit_hash")

        # Explicit verified commit/worktree binding required for skipping execution
        if (
            cp_disp == item.dispatch_id
            and cp_task == item.task_id
            and latest_cp.team_id == session.team_id
            and bool(cp_commit)
            and bool(current_commit)
            and cp_commit == current_commit
        ):
            is_valid_checkpoint = True

    payload = dict(item.payload)
    steps = payload.get("steps")
    expected_artifacts = payload.get("expected_artifacts", [])

    # Approval must be resolved by the exact authority attached to this IPC controller.
    # All command approvals are obtained BEFORE running any multi-step side effects.
    def preflight_command_approvals(
        command_steps: list[tuple[str, dict[str, Any]]],
    ) -> dict[str, Any] | None:
        if not command_steps:
            return None
        if approval_authority is None or approval_authority is not controller.approval_authority:
            item.status = QueueTaskStatus.DISPATCHED
            store.save_queue_item(item)
            return {"status": "RECOVERY_BLOCKED", "reason": "Trusted attached human approval authority required",
                    "dispatch_id": item.dispatch_id}
        pending: list[dict[str, str]] = []
        for command_task_id, owner in command_steps:
            cmd = owner["command"]
            command_list = [str(x) for x in cmd] if isinstance(cmd, list) else [str(cmd)]
            action_id = owner.get("approval_action_id")
            action = approval_authority.broker.get_action(action_id) if action_id else None
            if action is None or (
                action.state.value == "APPROVED" and approval_authority.is_action_consumed(action.action_id)
            ):
                action = approval_authority.request_command_approval(
                    worker_id=worker_id,
                    task_id=command_task_id,
                    command=command_list,
                    workspace_path=worktree_path or "",
                )
                owner["approval_action_id"] = action.action_id
            if action.state.value == "BLOCKED":
                pending.append({"task_id": command_task_id, "action_id": action.action_id})
            elif action.state.value != "APPROVED":
                item.status = QueueTaskStatus.DISPATCHED
                item.updated_at = time.time()
                store.save_queue_item(item)
                return {"status": "RECOVERY_BLOCKED", "reason": f"Human approval {action.state.value}",
                        "action_id": action.action_id, "dispatch_id": item.dispatch_id}
        item.status = QueueTaskStatus.DISPATCHED if pending else QueueTaskStatus.RUNNING
        item.updated_at = time.time()
        store.save_queue_item(item)
        if pending:
            return {"status": "AWAITING_APPROVAL", "dispatch_id": item.dispatch_id,
                    "action_id": pending[0]["action_id"], "pending_actions": pending,
                    "completed_steps": completed_steps}
        return None

    if is_valid_checkpoint and latest_cp and latest_cp.context_snapshot:
        candidate_completed = list(latest_cp.context_snapshot.get("completed_steps", []))
        # Validate task-specific evidence for every completed/skipped step
        verified_completed: list[str] = []
        if worktree_path and Path(worktree_path).exists():
            for s_name in candidate_completed:
                m_step = next((s for s in (steps or []) if s.get("name") == s_name), None)
                if m_step and (m_step.get("artifact") or m_step.get("expected_artifact")):
                    art_name = m_step.get("artifact") or m_step.get("expected_artifact")
                    art_file = Path(worktree_path) / art_name
                    if art_file.exists() and art_file.stat().st_size > 0:
                        verified_completed.append(s_name)
                else:
                    verified_completed.append(s_name)
        completed_steps = verified_completed
    else:
        latest_cp = None
        completed_steps = []

    if isinstance(steps, list):
        # Bounded multi-step workflow: skip only verified completed steps
        remaining_steps = [s for s in steps if s.get("name") not in completed_steps]

        # Detect potential crash between side effect and checkpoint persistence
        uncheckpointed_side_effects = []
        if worktree_path and Path(worktree_path).exists():
            for rem_s in remaining_steps:
                s_art = rem_s.get("artifact") or rem_s.get("expected_artifact")
                if s_art and (Path(worktree_path) / s_art).exists():
                    uncheckpointed_side_effects.append(rem_s.get("name"))

        classification = (
            "RECOVERABLE_AMBIGUITY_AT_LEAST_ONCE"
            if uncheckpointed_side_effects
            else "AT_LEAST_ONCE_RECOVERABLE"
        )

        # Never mark COMPLETED merely because checkpoint claims steps finished without validating evidence
        if not remaining_steps:
            missing_evidence = False
            if expected_artifacts and worktree_path:
                for art in expected_artifacts:
                    art_file = Path(worktree_path) / art
                    if not art_file.exists() or art_file.stat().st_size == 0:
                        missing_evidence = True
                        break
            elif not expected_artifacts and steps:
                # If no expected_artifacts declared, check that steps actually created evidence
                any_evidence = False
                if worktree_path:
                    for s in steps:
                        s_art = s.get("artifact") or s.get("expected_artifact")
                        if s_art and (Path(worktree_path) / s_art).exists():
                            any_evidence = True
                            break
                if not any_evidence:
                    missing_evidence = True

            if missing_evidence:
                # Evidence missing: reset completed steps and re-execute safely under at-least-once recovery
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
                    "execution_classification": classification,
                }

        # Invalid or missing checkpoint identity must never silently replay an
        # already observed successful side effect from an earlier failed resume.
        if item.payload.get("_unverified_completed_steps") and not is_valid_checkpoint:
            item.status = QueueTaskStatus.DISPATCHED
            store.save_queue_item(item)
            return {"status": "RECOVERY_BLOCKED", "reason": "Ambiguous side effects require operator reconciliation",
                    "completed_steps": item.payload["_unverified_completed_steps"]}

        if not isinstance(remaining_steps, list) or any(not isinstance(step, dict) for step in remaining_steps):
            raise ValueError("Malformed multi-step payload")
        seen_step_names: set[str] = set()
        command_steps: list[tuple[str, dict[str, Any]]] = []
        for step_index, step in enumerate(remaining_steps):
            step_name = str(step.get("name", f"step_{step_index + 1}"))
            if step_name in seen_step_names:
                raise ValueError("Duplicate step name cannot safely bind approvals")
            seen_step_names.add(step_name)
            if "command" in step:
                command_steps.append((f"{item.task_id}-{step_name}", step))
        preflight = preflight_command_approvals(command_steps)
        if preflight is not None:
            return preflight

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

            # Ticket is bound to this step and comes from the preflight-approved
            # action. Do not request or self-approve a new action mid-execution.
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
            # If checkpoint evidence cannot be bound to a Git commit, a later
            # retry must not automatically replay an observed side effect.
            item.payload["_unverified_completed_steps"] = list(completed_steps)
            store.save_queue_item(item)
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
    if is_valid_checkpoint and latest_cp and latest_cp.context_snapshot.get("completed"):
        # Check evidence: bare completion claim without verified evidence is rejected
        ev_missing = False
        if expected_artifacts and worktree_path:
            for art in expected_artifacts:
                art_file = Path(worktree_path) / art
                if not art_file.exists() or art_file.stat().st_size == 0:
                    ev_missing = True
                    break
        elif not expected_artifacts:
            # Require at least one verified artifact or execution receipt
            receipt_id = latest_cp.context_snapshot.get("receipt_id")
            if not receipt_id:
                ev_missing = True

        if not ev_missing:
            item.status = QueueTaskStatus.COMPLETED
            item.updated_at = time.time()
            store.save_queue_item(item)
            return {"status": "COMPLETED", "summary": "Task was completed before crash and verified against evidence"}

    if "command" in item.payload:
        preflight = preflight_command_approvals([(item.task_id, item.payload)])
        if preflight is not None:
            return preflight
        payload = dict(item.payload)

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
