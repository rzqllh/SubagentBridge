"""Tests for Phase C04: Inter-Agent Control, Messaging, Queue, Steering, and Verified Handoffs.

Validates:
- Authenticated Lead<->Worker communication and history reading.
- Durable targeted queue with FIFO ordering.
- Dispatch deduplication via idempotency keys.
- In-flight task steering by Lead.
- Task cancellation and worker interruption preemption.
- Verified handoff binding (rejecting spoofed workers and late handoffs).
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from subagentbridge.domain.orca_contracts import (
    ChannelMessage,
    HandoffEvidence,
    OrcaRole,
    OrcaSession,
    QueueItem,
    QueueTaskStatus,
    WorkerConfig,
    WorkerStatus,
)
from subagentbridge.storage.orca_store import OrcaStore
from subagentbridge.team.orca_team import OrcaTeamService


@pytest.fixture
def store_and_service():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_c04.db"
        with OrcaStore(db_path) as store:
            service = OrcaTeamService(store=store)
            yield store, service


def _setup_lead_and_workers(service: OrcaTeamService):
    team = service.create_team(lead_session_id="lead-alpha", title="Alpha Team")
    worker1 = service.register_worker(
        WorkerConfig(worker_id="w-coder-1", team_id=team.team_id, role="coder", harness="native")
    )
    worker2 = service.register_worker(
        WorkerConfig(worker_id="w-tester-1", team_id=team.team_id, role="tester", harness="native")
    )
    return team, worker1, worker2


def test_c04_authenticated_lead_worker_messaging(store_and_service):
    """Lead and workers can exchange messages within the same team; history is preserved."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    # Lead posts an instruction to the team channel
    msg1 = service.post_message(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        content="Begin implementing parser module",
    )
    assert isinstance(msg1, ChannelMessage)
    assert msg1.team_id == team.team_id
    assert msg1.from_session_id == team.lead_session_id
    assert msg1.to_session_id == worker1.session_id

    # Worker posts progress update
    msg2 = service.post_message(
        from_session_id=worker1.session_id,
        to_session_id=team.lead_session_id,
        content="Parser AST parsing complete, running tests",
    )
    assert msg2.from_session_id == worker1.session_id

    # Worker reads lead history
    history = service.read_lead_history(worker1.session_id)
    assert len(history) == 2
    assert history[0].content == "Begin implementing parser module"
    assert history[1].content == "Parser AST parsing complete, running tests"

    # Cross-team or non-existent session messaging rejected
    with pytest.raises(ValueError, match="not found"):
        service.post_message("non-existent-lead", worker1.session_id, "hello")


def test_c04_targeted_queue_fifo_order(store_and_service):
    """Tasks dispatched to specific worker are fetched in FIFO order."""
    _, service = store_and_service
    team, worker1, worker2 = _setup_lead_and_workers(service)

    # Dispatch two tasks to worker1 and one to worker2
    item1 = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-1",
        payload={"instruction": "first task for worker 1"},
    )
    time.sleep(0.01)
    item2 = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker2.session_id,
        task_id="task-2",
        payload={"instruction": "task for worker 2"},
    )
    time.sleep(0.01)
    item3 = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-3",
        payload={"instruction": "second task for worker 1"},
    )

    # Fetch next task for worker1
    next_w1 = service.fetch_next_pending_task(team.team_id, worker1.session_id)
    assert next_w1 is not None
    assert next_w1.dispatch_id == item1.dispatch_id
    assert next_w1.task_id == "task-1"

    # Update item1 status to RUNNING
    service.update_queue_status(item1.dispatch_id, QueueTaskStatus.RUNNING)

    # Now next task for worker1 should be item3
    next_w1_second = service.fetch_next_pending_task(team.team_id, worker1.session_id)
    assert next_w1_second is not None
    assert next_w1_second.dispatch_id == item3.dispatch_id

    # Next task for worker2 should be item2
    next_w2 = service.fetch_next_pending_task(team.team_id, worker2.session_id)
    assert next_w2 is not None
    assert next_w2.dispatch_id == item2.dispatch_id


def test_c04_dispatch_deduplication(store_and_service):
    """Tasks dispatched with the same dedup_key return existing item without duplicate dispatch."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    item1 = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-dedup-1",
        payload={"instruction": "run build step"},
        dedup_key="build-step-unique-key-123",
    )

    # Dispatch duplicate with same dedup_key
    item2 = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-dedup-retry",
        payload={"instruction": "run build step"},
        dedup_key="build-step-unique-key-123",
    )

    assert item2.dispatch_id == item1.dispatch_id
    assert item2.task_id == item1.task_id

    # Queue should contain only one item for this team
    queue = service.list_team_queue(team.team_id)
    assert len(queue) == 1


def test_c04_lead_steering_active_task(store_and_service):
    """Lead can steer in-flight task with additional guidance; non-lead or finished task cannot be steered."""
    _, service = store_and_service
    team, worker1, worker2 = _setup_lead_and_workers(service)

    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-steer-1",
        payload={"instruction": "refactor authentication"},
    )
    service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

    # Lead steers running task
    steered = service.steer_task(
        lead_session_id=team.lead_session_id,
        dispatch_id=item.dispatch_id,
        guidance="Prioritize OAuth2 PKCE over client secrets",
    )
    assert len(steered.steering_instructions) == 1
    assert steered.steering_instructions[0]["guidance"] == "Prioritize OAuth2 PKCE over client secrets"

    # Worker cannot steer task (only Lead)
    with pytest.raises(PermissionError, match="Only lead"):
        service.steer_task(
            lead_session_id=worker2.session_id,
            dispatch_id=item.dispatch_id,
            guidance="Unauthorized guidance",
        )

    # Cannot steer completed or cancelled task
    service.update_queue_status(item.dispatch_id, QueueTaskStatus.COMPLETED)
    with pytest.raises(ValueError, match="Cannot steer"):
        service.steer_task(
            lead_session_id=team.lead_session_id,
            dispatch_id=item.dispatch_id,
            guidance="Too late guidance",
        )


def test_c04_worker_interruption_and_cancellation(store_and_service):
    """Lead can cancel specific task or interrupt entire worker atomically."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    item1 = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-cancel-1",
        payload={"instruction": "long running task 1"},
    )
    item2 = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-cancel-2",
        payload={"instruction": "long running task 2"},
    )

    # Cancel item1 directly
    cancelled_item = service.cancel_task(team.lead_session_id, item1.dispatch_id, reason="User requested abort")
    assert cancelled_item.status == QueueTaskStatus.CANCELLED

    # Interrupt worker1: item2 must transition to INTERRUPTED and worker status to INTERRUPTED
    ok = service.interrupt_worker(worker1.session_id, reason="Emergency stop")
    assert ok is True

    loaded_worker = service.store.load_session(worker1.session_id)
    assert loaded_worker.status == WorkerStatus.INTERRUPTED

    loaded_item2 = service.store.load_queue_item(item2.dispatch_id)
    assert loaded_item2.status == QueueTaskStatus.INTERRUPTED


def test_c04_verified_handoff_binding_success(store_and_service):
    """Worker submits handoff matching dispatch; status updates to COMPLETED and worker back to IDLE."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-handoff-1",
        payload={"instruction": "run verification tests"},
    )
    service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

    evidence = HandoffEvidence(
        dispatch_id=item.dispatch_id,
        from_worker_id=worker1.session_id,
        to_lead_id=team.lead_session_id,
        status="SUCCESS",
        summary="All 15 verification tests passed cleanly",
        artifacts=["reports/test_results.xml"],
        metrics={"duration_s": 4.2, "tests_run": 15},
    )

    res = service.submit_worker_handoff(evidence)
    assert res["status"] == "RECEIVED"
    assert res["dispatch_id"] == item.dispatch_id

    # Queue item should now be COMPLETED
    updated_item = service.store.load_queue_item(item.dispatch_id)
    assert updated_item.status == QueueTaskStatus.COMPLETED

    # Worker should be reset to IDLE
    loaded_worker = service.store.load_session(worker1.session_id)
    assert loaded_worker.status == WorkerStatus.IDLE


def test_c04_reject_spoofed_worker_handoff(store_and_service):
    """An unassigned worker cannot submit handoff for another worker's dispatch."""
    _, service = store_and_service
    team, worker1, worker2 = _setup_lead_and_workers(service)

    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-spoof-probe",
        payload={"instruction": "secure operation"},
    )
    service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

    # worker2 attempts to spoof handoff for worker1's task
    spoofed_evidence = HandoffEvidence(
        dispatch_id=item.dispatch_id,
        from_worker_id=worker2.session_id,  # Spoofed worker!
        to_lead_id=team.lead_session_id,
        status="SUCCESS",
        summary="Spoofed completion report",
    )

    with pytest.raises(PermissionError, match="Worker identity mismatch"):
        service.submit_worker_handoff(spoofed_evidence)


def test_c04_reject_late_handoff_after_interruption(store_and_service):
    """Once a task is CANCELLED or INTERRUPTED, late completion handoffs are strictly rejected."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-interrupted-probe",
        payload={"instruction": "interrupted operation"},
    )
    # Interrupt worker
    service.interrupt_worker(worker1.session_id)

    late_evidence = HandoffEvidence(
        dispatch_id=item.dispatch_id,
        from_worker_id=worker1.session_id,
        to_lead_id=team.lead_session_id,
        status="SUCCESS",
        summary="Late completed work",
    )

    with pytest.raises(ValueError, match="Cannot accept handoff for item in status"):
        service.submit_worker_handoff(late_evidence)
