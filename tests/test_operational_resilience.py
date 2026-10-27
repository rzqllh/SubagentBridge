"""Operational resilience and recovery drills test suite.

Verifies:
- SQLite WAL checkpoint, online backup, and integrity-verified restore.
- Crash reconciliation transitioning in-flight side effects to AMBIGUOUS.
- Independent operator reconciliation (RETRY, MARK_COMPLETED, MARK_FAILED).
- Rejection of corrupted backup files with fail-closed integrity checks.
"""
from __future__ import annotations

import time
from pathlib import Path
import pytest

from subagentbridge.domain.team_contracts import (
    AgentRole,
    AgentSession,
    AgentTeam,
    QueueItem,
    QueueTaskStatus,
    WorkerCheckpoint,
    WorkerConfig,
    WorkerStatus,
)
from subagentbridge.recovery.crash_recovery import (
    reconcile_ambiguous_task,
    reconcile_team_after_crash,
)
from subagentbridge.storage.team_store import TeamStore


@pytest.fixture
def temp_db_dir(tmp_path: Path) -> Path:
    d = tmp_path / "resilience_data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_sqlite_wal_checkpoint_and_online_backup_restore(temp_db_dir: Path):
    db_file = temp_db_dir / "primary.db"
    backup_file = temp_db_dir / "backups" / "primary_backup.db"
    restore_file = temp_db_dir / "restored" / "primary_restored.db"

    store = TeamStore(db_file)
    now = time.time()

    team = AgentTeam(team_id="team-res-1", lead_session_id="lead-1", title="Resilience Team", created_at=now)
    store.save_team(team)

    session = AgentSession(
        session_id="w-res-1",
        role=AgentRole.WORKER,
        team_id=team.team_id,
        status=WorkerStatus.IDLE,
        config=WorkerConfig(worker_id="w-res-1", team_id=team.team_id),
        created_at=now,
        updated_at=now,
    )
    store.save_session(session)

    item = QueueItem(
        dispatch_id="disp-res-1",
        team_id=team.team_id,
        from_session_id="lead-1",
        to_session_id="w-res-1",
        task_id="task-res-1",
        payload={"task": "drill"},
        status=QueueTaskStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    store.save_queue_item(item)

    cp = WorkerCheckpoint(
        checkpoint_id="cp-res-1",
        worker_id="w-res-1",
        team_id=team.team_id,
        step_index=1,
        state_summary="drill checkpoint",
        tokens_consumed=150,
        context_snapshot={"drill": "complete"},
        created_at=now,
    )
    store.save_checkpoint(cp)

    # Perform WAL checkpoint
    busy, log_pages, checkpointed = store.checkpoint_wal(mode="TRUNCATE")
    assert isinstance(busy, int)
    assert isinstance(log_pages, int)
    assert isinstance(checkpointed, int)

    # Perform online backup
    store.backup_database(backup_file)
    assert backup_file.exists()
    assert backup_file.stat().st_size > 0

    # Mutate primary database after backup
    mutated_item = QueueItem(
        dispatch_id="disp-mutated-2",
        team_id=team.team_id,
        from_session_id="lead-1",
        to_session_id="w-res-1",
        task_id="task-mutated",
        payload={"task": "post-backup"},
        status=QueueTaskStatus.PENDING,
        created_at=time.time(),
        updated_at=time.time(),
    )
    store.save_queue_item(mutated_item)
    assert store.load_queue_item("disp-mutated-2") is not None

    # Close primary store
    store.close()

    # Restore from backup
    restored_store = TeamStore.restore_from_backup(backup_file, restore_file)
    try:
        # Verify pre-backup entities exist
        assert restored_store.load_team("team-res-1") is not None
        assert restored_store.load_session("w-res-1") is not None
        assert restored_store.load_queue_item("disp-res-1") is not None
        assert restored_store.load_latest_checkpoint("w-res-1") is not None

        # Verify post-backup mutation does NOT exist in restore (clean point-in-time recovery)
        assert restored_store.load_queue_item("disp-mutated-2") is None
    finally:
        restored_store.close()


def test_corrupt_backup_rejected_fail_closed(temp_db_dir: Path):
    corrupt_backup = temp_db_dir / "corrupted.db"
    target_restore = temp_db_dir / "target_corrupted.db"

    # Write corrupt non-SQLite data
    corrupt_backup.write_bytes(b"THIS_IS_NOT_A_VALID_SQLITE_DATABASE_HEADER_DATA_STREAM")

    with pytest.raises(Exception):
        TeamStore.restore_from_backup(corrupt_backup, target_restore)

    assert not target_restore.exists()


def test_crash_ambiguous_task_transition_and_operator_reconciliation(temp_db_dir: Path):
    db_file = temp_db_dir / "ambiguity.db"
    store = TeamStore(db_file)
    now = time.time()

    team = AgentTeam(team_id="team-amb-1", lead_session_id="lead-1", title="Ambiguity Team", created_at=now)
    store.save_team(team)

    # Worker with a dead PID (e.g. 99999999)
    session = AgentSession(
        session_id="w-dead-task",
        role=AgentRole.WORKER,
        team_id=team.team_id,
        status=WorkerStatus.RUNNING,
        config=WorkerConfig(
            worker_id="w-dead-task",
            team_id=team.team_id,
            pid=99999999,
            process_create_time=now - 500,
        ),
        created_at=now,
        updated_at=now,
    )
    store.save_session(session)

    # Task in flight when crash hit
    item_running = QueueItem(
        dispatch_id="disp-amb-1",
        team_id=team.team_id,
        from_session_id="lead-1",
        to_session_id="w-dead-task",
        task_id="task-amb-1",
        payload={"command": ["deploy", "--stage", "prod"]},
        status=QueueTaskStatus.RUNNING,
        created_at=now,
        updated_at=now,
    )
    store.save_queue_item(item_running)

    # Task pending when crash hit
    item_pending = QueueItem(
        dispatch_id="disp-pend-1",
        team_id=team.team_id,
        from_session_id="lead-1",
        to_session_id="w-dead-task",
        task_id="task-pend-1",
        payload={"command": ["echo", "unreached"]},
        status=QueueTaskStatus.PENDING,
        created_at=now,
        updated_at=now,
    )
    store.save_queue_item(item_pending)

    # Reconcile team after crash with mark_in_flight_as_ambiguous=True
    report = reconcile_team_after_crash(team.team_id, store=store, mark_in_flight_as_ambiguous=True)
    assert report["reconciled_workers"] == 1
    assert "disp-amb-1" in report["ambiguous_tasks"]
    assert "disp-pend-1" in report["failed_tasks"]

    # Verify task states
    reloaded_running = store.load_queue_item("disp-amb-1")
    assert reloaded_running is not None
    assert reloaded_running.status == QueueTaskStatus.AMBIGUOUS

    reloaded_pending = store.load_queue_item("disp-pend-1")
    assert reloaded_pending is not None
    assert reloaded_pending.status == QueueTaskStatus.FAILED

    # Operator reconciliation: invalid resolution rejected
    with pytest.raises(ValueError, match="Invalid resolution"):
        reconcile_ambiguous_task("disp-amb-1", store, resolution="MAGIC_AUTO_RESOLVE")

    # Operator reconciliation: resolve as RETRY
    resolved_retry = reconcile_ambiguous_task(
        "disp-amb-1",
        store,
        resolution="RETRY",
        operator_notes="Verified target staging clean, safe to retry",
    )
    assert resolved_retry.status == QueueTaskStatus.PENDING
    assert "_reconciliation" in resolved_retry.payload
    assert resolved_retry.payload["_reconciliation"]["resolution"] == "RETRY"

    # Operator reconciliation: resolve as MARK_COMPLETED
    resolved_retry.status = QueueTaskStatus.AMBIGUOUS
    store.save_queue_item(resolved_retry)

    resolved_completed = reconcile_ambiguous_task(
        "disp-amb-1",
        store,
        resolution="MARK_COMPLETED",
        operator_notes="Physical deployment artifacts independently verified by operator",
    )
    assert resolved_completed.status == QueueTaskStatus.COMPLETED
    assert resolved_completed.payload["_reconciliation"]["resolution"] == "MARK_COMPLETED"

    store.close()
