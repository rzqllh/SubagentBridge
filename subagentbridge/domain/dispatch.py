"""subagentbridge/domain/dispatch.py — Dispatch idempotency and lifecycle model (INV-09).

Prevents stale dispatches from completing or overwriting newer task attempts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DispatchStatus(str, Enum):
    INITIALIZED = "INITIALIZED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True, slots=True)
class DispatchAttempt:
    dispatch_id: str
    task_id: str
    run_id: str
    attempt_number: int
    tree_sha: str
    policy_revision: str
    status: DispatchStatus = DispatchStatus.INITIALIZED


class DispatchIdempotencyTracker:
    """Tracks active dispatches per task and enforces that only the latest active dispatch can complete."""

    def __init__(self) -> None:
        self._active_attempts: dict[str, DispatchAttempt] = {}
        self._history: list[DispatchAttempt] = []

    def start_dispatch(
        self,
        *,
        dispatch_id: str,
        task_id: str,
        run_id: str,
        tree_sha: str,
        policy_revision: str,
    ) -> DispatchAttempt:
        prior = self._active_attempts.get(task_id)
        attempt_num = (prior.attempt_number + 1) if prior else 1
        if prior and prior.status == DispatchStatus.ACTIVE:
            # Supersede previous attempt
            superseded = DispatchAttempt(
                dispatch_id=prior.dispatch_id,
                task_id=prior.task_id,
                run_id=prior.run_id,
                attempt_number=prior.attempt_number,
                tree_sha=prior.tree_sha,
                policy_revision=prior.policy_revision,
                status=DispatchStatus.SUPERSEDED,
            )
            self._history.append(superseded)

        attempt = DispatchAttempt(
            dispatch_id=dispatch_id,
            task_id=task_id,
            run_id=run_id,
            attempt_number=attempt_num,
            tree_sha=tree_sha,
            policy_revision=policy_revision,
            status=DispatchStatus.ACTIVE,
        )
        self._active_attempts[task_id] = attempt
        return attempt

    def validate_active_dispatch(self, *, task_id: str, dispatch_id: str) -> DispatchAttempt:
        active = self._active_attempts.get(task_id)
        if active is None:
            raise KeyError(f"no active dispatch for task {task_id!r}")
        if active.dispatch_id != dispatch_id:
            raise PermissionError(
                f"stale dispatch {dispatch_id!r} cannot complete task {task_id!r} "
                f"(current active attempt: {active.dispatch_id!r})"
            )
        if active.status != DispatchStatus.ACTIVE:
            raise PermissionError(f"dispatch {dispatch_id!r} is already {active.status.value}")
        return active

    def complete_dispatch(self, *, task_id: str, dispatch_id: str, success: bool) -> DispatchAttempt:
        active = self.validate_active_dispatch(task_id=task_id, dispatch_id=dispatch_id)
        new_status = DispatchStatus.COMPLETED if success else DispatchStatus.FAILED
        completed = DispatchAttempt(
            dispatch_id=active.dispatch_id,
            task_id=active.task_id,
            run_id=active.run_id,
            attempt_number=active.attempt_number,
            tree_sha=active.tree_sha,
            policy_revision=active.policy_revision,
            status=new_status,
        )
        self._active_attempts[task_id] = completed
        self._history.append(completed)
        return completed
