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

from dataclasses import replace
import hashlib
import tempfile
import time
from pathlib import Path

import pytest

from subagentbridge.domain.team_contracts import (
    ChannelMessage,
    HandoffEvidence,
    QueueTaskStatus,
    WorkerConfig,
    WorkerStatus,
)
from subagentbridge.storage.team_store import TeamStore, OrcaStore
from subagentbridge.team.team_manager import TeamManager, OrcaTeamService


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

    with tempfile.TemporaryDirectory() as worker_workspace:
        worker1 = replace(worker1, config=replace(worker1.config, working_dir=worker_workspace))
        service.store.save_session(worker1)

        # Create genuine report artifact on disk and compute exact SHA256
        reports_dir = Path(worker_workspace) / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = reports_dir / "test_results.xml"
        report_file.write_text("<testsuite tests='15' failures='0'/>", encoding="utf-8")
        report_sha = hashlib.sha256(report_file.read_bytes()).hexdigest()

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
            metrics={
                "receipt_id": f"rcpt-{item.dispatch_id}",
                "duration_s": 4.2,
                "tests_run": 15,
                "exit_code": 0,
                "qa_verdict": "PASS",
                "artifact_hashes": {"reports/test_results.xml": report_sha},
            },
        )

        res = service.submit_worker_handoff(evidence)
        assert res["status"] == "RECEIVED"
        assert res["dispatch_id"] == item.dispatch_id

        # Queue item should now be COMPLETED
        updated_item = service.store.load_queue_item(item.dispatch_id)
        assert updated_item is not None
        assert updated_item.status == QueueTaskStatus.COMPLETED

        # Worker should be reset to IDLE
        loaded_worker = service.store.load_session(worker1.session_id)
        assert loaded_worker is not None
        assert loaded_worker.status == WorkerStatus.IDLE


def test_c04_reject_handoff_for_pending_task(store_and_service):
    """Handoff cannot be accepted for a task in PENDING status before execution begins."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-pending-handoff",
        payload={"instruction": "unstarted task"},
    )
    # Item is in PENDING status
    assert item.status == QueueTaskStatus.PENDING

    evidence = HandoffEvidence(
        dispatch_id=item.dispatch_id,
        from_worker_id=worker1.session_id,
        to_lead_id=team.lead_session_id,
        status="SUCCESS",
        summary="Premature completion claim",
        metrics={"exit_code": 0, "qa_verdict": "PASS"},
    )
    with pytest.raises(ValueError, match="Cannot accept handoff for pending task"):
        service.submit_worker_handoff(evidence)


def test_c04_reject_artifact_path_traversal_escape(store_and_service):
    """Artifact path containing traversal characters escaping workspace must be rejected."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    with tempfile.TemporaryDirectory() as worker_workspace:
        worker1 = replace(worker1, config=replace(worker1.config, working_dir=worker_workspace))
        service.store.save_session(worker1)

        item = service.dispatch_task(
            from_session_id=team.lead_session_id,
            to_session_id=worker1.session_id,
            task_id="task-traversal-escape",
            payload={"instruction": "malicious handoff"},
        )
        service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

        evidence = HandoffEvidence(
            dispatch_id=item.dispatch_id,
            from_worker_id=worker1.session_id,
            to_lead_id=team.lead_session_id,
            status="SUCCESS",
            summary="Traversal attempt",
            artifacts=["../../escaped_secret.txt"],
            metrics={"exit_code": 0, "qa_verdict": "PASS"},
        )
        with pytest.raises(PermissionError, match="Handoff artifact path escape detected"):
            service.submit_worker_handoff(evidence)


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


def test_c04_reject_verify_artifacts_false_bypass(store_and_service):
    """Bypassing artifact verification (verify_artifacts=False) is forbidden for successful handoffs."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-bypass-test",
        payload={"instruction": "test"},
    )
    service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

    evidence = HandoffEvidence(
        dispatch_id=item.dispatch_id,
        from_worker_id=worker1.session_id,
        to_lead_id=team.lead_session_id,
        status="SUCCESS",
        summary="Claimed success with verification bypassed",
        artifacts=["unverified.txt"],
        metrics={"exit_code": 0, "receipt_id": "rcpt-1", "qa_verdict": "PASS"},
    )
    with pytest.raises(PermissionError, match="Bypassing artifact verification"):
        service.submit_worker_handoff(evidence, verify_artifacts=False)


def test_c04_reject_missing_artifact_sha256(store_and_service):
    """Declared artifacts must have expected SHA256 hashes in metrics."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    with tempfile.TemporaryDirectory() as worker_workspace:
        worker1 = replace(worker1, config=replace(worker1.config, working_dir=worker_workspace))
        service.store.save_session(worker1)

        real_file = Path(worker_workspace) / "report.txt"
        real_file.write_text("VALID_DATA")

        item = service.dispatch_task(
            from_session_id=team.lead_session_id,
            to_session_id=worker1.session_id,
            task_id="task-no-hash",
            payload={"instruction": "test"},
        )
        service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

        evidence = HandoffEvidence(
            dispatch_id=item.dispatch_id,
            from_worker_id=worker1.session_id,
            to_lead_id=team.lead_session_id,
            status="SUCCESS",
            summary="Missing artifact SHA256",
            artifacts=["report.txt"],
            metrics={"exit_code": 0, "receipt_id": "rcpt-1", "qa_verdict": "PASS"},
        )
        with pytest.raises(ValueError, match="artifact_hashes"):
            service.submit_worker_handoff(evidence)


def test_c04_reject_handoff_without_genuine_receipt(store_and_service):
    """Handoff requires a genuine execution receipt and QA verdict, not only client-supplied exit_code."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-no-receipt",
        payload={"instruction": "test"},
    )
    service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

    # Client supplies only exit_code without receipt_id
    evidence = HandoffEvidence(
        dispatch_id=item.dispatch_id,
        from_worker_id=worker1.session_id,
        to_lead_id=team.lead_session_id,
        status="SUCCESS",
        summary="Bare exit code claim",
        metrics={"exit_code": 0, "qa_verdict": "PASS"},
    )
    with pytest.raises(ValueError, match="missing genuine trusted execution receipt"):
        service.submit_worker_handoff(evidence)


def test_c04_reject_empty_or_fabricated_evidence(store_and_service):
    """Empty summary or empty metrics is rejected for successful handoffs."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-empty-ev",
        payload={"instruction": "test"},
    )
    service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

    # Empty summary
    evidence = HandoffEvidence(
        dispatch_id=item.dispatch_id,
        from_worker_id=worker1.session_id,
        to_lead_id=team.lead_session_id,
        status="SUCCESS",
        summary="",
        metrics={"exit_code": 0, "receipt_id": "rcpt-1", "qa_verdict": "PASS"},
    )
    with pytest.raises(ValueError, match="summary must be non-empty"):
        service.submit_worker_handoff(evidence)


def test_c04_reject_symlink_artifact_inside_workspace(store_and_service):
    """Artifacts that are symlinks inside the workspace are rejected before resolution."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    with tempfile.TemporaryDirectory() as worker_workspace:
        worker1 = replace(worker1, config=replace(worker1.config, working_dir=worker_workspace))
        service.store.save_session(worker1)

        real_target = Path(worker_workspace) / "target.txt"
        real_target.write_text("TARGET")
        sym_link = Path(worker_workspace) / "link_artifact.txt"
        try:
            sym_link.symlink_to(real_target)
        except OSError:
            pytest.skip("Symlink creation not supported on this host environment")

        target_sha = hashlib.sha256(real_target.read_bytes()).hexdigest()

        item = service.dispatch_task(
            from_session_id=team.lead_session_id,
            to_session_id=worker1.session_id,
            task_id="task-symlink-artifact",
            payload={"instruction": "test"},
        )
        service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

        evidence = HandoffEvidence(
            dispatch_id=item.dispatch_id,
            from_worker_id=worker1.session_id,
            to_lead_id=team.lead_session_id,
            status="SUCCESS",
            summary="Symlink artifact handoff",
            artifacts=["link_artifact.txt"],
            metrics={
                "exit_code": 0,
                "receipt_id": "rcpt-sym",
                "qa_verdict": "PASS",
                "artifact_hashes": {"link_artifact.txt": target_sha},
            },
        )
        with pytest.raises(PermissionError, match="is a symlink"):
            service.submit_worker_handoff(evidence)


def test_c04_reject_duplicate_handoff_transactional_replay(store_and_service):
    """Submitting duplicate handoffs for the same dispatch is rejected transactionally."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    with tempfile.TemporaryDirectory() as worker_workspace:
        worker1 = replace(worker1, config=replace(worker1.config, working_dir=worker_workspace))
        service.store.save_session(worker1)

        res_file = Path(worker_workspace) / "res.txt"
        res_file.write_text("RES")
        res_sha = hashlib.sha256(res_file.read_bytes()).hexdigest()

        item = service.dispatch_task(
            from_session_id=team.lead_session_id,
            to_session_id=worker1.session_id,
            task_id="task-dup-handoff",
            payload={"instruction": "test"},
        )
        service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

        evidence = HandoffEvidence(
            dispatch_id=item.dispatch_id,
            from_worker_id=worker1.session_id,
            to_lead_id=team.lead_session_id,
            status="SUCCESS",
            summary="First successful submission",
            artifacts=["res.txt"],
            metrics={
                "exit_code": 0,
                "receipt_id": "rcpt-dup-1",
                "qa_verdict": "PASS",
                "artifact_hashes": {"res.txt": res_sha},
            },
        )
        ack = service.submit_worker_handoff(evidence)
        assert ack["status"] == "RECEIVED"

        # Duplicate replay attempt via service
        with pytest.raises(ValueError, match="Cannot accept handoff for item in status|Handoff already finalized"):
            service.submit_worker_handoff(evidence)

        # Direct transactional database replay rejection in store
        with pytest.raises(ValueError, match="Handoff already finalized"):
            service.store.finalize_handoff_transaction(team.team_id, evidence)


def test_c04_contract_only_handoff_keeps_separate_status(store_and_service):
    """Contract-only handoffs transition to CONTRACT_VERIFIED, never falsely claiming COMPLETED."""
    _, service = store_and_service
    team, worker1, _ = _setup_lead_and_workers(service)

    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker1.session_id,
        task_id="task-contract-only",
        payload={"instruction": "contract test"},
    )
    service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

    evidence = HandoffEvidence(
        dispatch_id=item.dispatch_id,
        from_worker_id=worker1.session_id,
        to_lead_id=team.lead_session_id,
        status="CONTRACT_FIXTURE",
        summary="Contract binding only without execution",
    )
    ack = service.submit_worker_handoff(evidence)
    assert ack["status"] == "CONTRACT_VERIFIED"

    # Queue status must remain RUNNING and NOT be falsely marked COMPLETED
    reloaded_item = service.store.load_queue_item(item.dispatch_id)
    assert reloaded_item is not None
    assert reloaded_item.status == QueueTaskStatus.RUNNING
    assert reloaded_item.status != QueueTaskStatus.COMPLETED

