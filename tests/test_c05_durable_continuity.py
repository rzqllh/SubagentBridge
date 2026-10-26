"""Tests for Phase C05: Durable Continuity, Checkpoints, Worktrees, and Crash Recovery.

Validates:
- Checkpoint creation, step indexing, context snapshotting, and token tracking.
- Git worktree automated creation, branch binding, tracking, and cleanup.
- Crash recovery: detecting dead child OS processes without false completion claims.
- Worker resume from checkpoint with cumulative token restoration.
- Cold-restart rehydration of teams, sessions, queues, and worktree assignments from disk.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from subagentbridge.domain.orca_contracts import (
    OrcaRole,
    QueueTaskStatus,
    WorkerCheckpoint,
    WorkerConfig,
    WorkerStatus,
)
from subagentbridge.execution.worker_process import WorkerProcessController
from subagentbridge.recovery.crash_recovery import (
    reconcile_team_after_crash,
    resume_worker_from_checkpoint,
)
from subagentbridge.storage.orca_store import OrcaStore
from subagentbridge.team.orca_team import OrcaTeamService
from subagentbridge.workspaces.worktree_manager import GitWorktreeManager


@pytest.fixture
def store_and_service():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_c05.db"
        with OrcaStore(db_path) as store:
            service = OrcaTeamService(store=store)
            yield store, service, db_path


def test_c05_checkpoint_save_and_latest_retrieval(store_and_service):
    """Save successive checkpoints for a worker; verify latest retrieval and list order."""
    store, service, _ = store_and_service
    team = service.create_team(lead_session_id="lead-c05", title="C05 Team")
    worker = service.register_worker(
        WorkerConfig(worker_id="w-cp-1", team_id=team.team_id, role="coder", harness="native")
    )

    cp1 = WorkerCheckpoint(
        checkpoint_id="cp-1",
        worker_id=worker.session_id,
        team_id=team.team_id,
        step_index=1,
        state_summary="Loaded dependencies",
        tokens_consumed=450,
        context_snapshot={"stage": "init"},
    )
    store.save_checkpoint(cp1)

    cp2 = WorkerCheckpoint(
        checkpoint_id="cp-2",
        worker_id=worker.session_id,
        team_id=team.team_id,
        step_index=2,
        state_summary="Implemented parsing functions",
        tokens_consumed=1250,
        context_snapshot={"stage": "implemented", "files": ["parser.py"]},
    )
    store.save_checkpoint(cp2)

    latest = store.load_latest_checkpoint(worker.session_id)
    assert latest is not None
    assert latest.checkpoint_id == "cp-2"
    assert latest.step_index == 2
    assert latest.tokens_consumed == 1250
    assert latest.context_snapshot["files"] == ["parser.py"]

    all_cps = store.list_checkpoints(worker.session_id)
    assert len(all_cps) == 2
    assert all_cps[0].checkpoint_id == "cp-1"
    assert all_cps[1].checkpoint_id == "cp-2"


def test_c05_git_worktree_lifecycle():
    """Create a temporary git repo, spawn isolated worker worktree, and clean it up."""
    with tempfile.TemporaryDirectory() as tmp_git_root, tempfile.TemporaryDirectory() as tmp_db:
        repo_path = Path(tmp_git_root)
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test User"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@example.com"],
            check=True,
            capture_output=True,
        )
        (repo_path / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "-C", str(repo_path), "add", "README.md"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True, capture_output=True)

        with OrcaStore(Path(tmp_db) / "orca_wt.db") as store:
            manager = GitWorktreeManager(repo_root=repo_path, store=store)

            assignment = manager.create_worktree(
                worker_id="w-wt-1",
                team_id="team-wt",
                branch_name="simpul/worker-wt-1",
            )
            assert assignment.worker_id == "w-wt-1"
            assert Path(assignment.worktree_path).is_dir()
            assert (Path(assignment.worktree_path) / "README.md").exists()

            # Verify persisted in store
            stored_wt = store.load_worktree("w-wt-1")
            assert stored_wt is not None
            assert stored_wt.branch_name == "simpul/worker-wt-1"

            # Clean up worktree
            ok = manager.cleanup_worktree(worker_id="w-wt-1", delete_branch=True)
            assert ok is True
            assert not Path(assignment.worktree_path).exists()


def test_c05_crash_recovery_detects_dead_worker(store_and_service):
    """Detect dead worker process and transition state to FAILED without false completion."""
    store, service, _ = store_and_service
    team = service.create_team(lead_session_id="lead-crash", title="Crash Test Team")

    # Worker configured with a definitely non-existent PID
    dead_pid = 999999
    cfg = WorkerConfig(
        worker_id="w-dead-1",
        team_id=team.team_id,
        role="coder",
        pid=dead_pid,
        process_create_time=1000.0,
    )
    worker = service.register_worker(cfg)
    service.set_worker_status(worker.session_id, WorkerStatus.RUNNING)

    # Dispatch task to this worker
    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker.session_id,
        task_id="task-crash-1",
        payload={"instruction": "critical work"},
    )
    service.update_queue_status(item.dispatch_id, QueueTaskStatus.RUNNING)

    # Reconcile team after crash
    report = reconcile_team_after_crash(team.team_id, store=store)
    assert report["reconciled_workers"] == 1
    assert "w-dead-1" in report["dead_workers"]

    # Worker status must now be FAILED, NOT RUNNING or COMPLETED
    reloaded_worker = store.load_session(worker.session_id)
    assert reloaded_worker.status == WorkerStatus.FAILED

    # Task status must now be FAILED
    reloaded_item = store.load_queue_item(item.dispatch_id)
    assert reloaded_item.status == QueueTaskStatus.FAILED


def test_c05_resume_worker_from_checkpoint(store_and_service):
    """Resume a failed worker from latest checkpoint and restore cumulative tokens."""
    store, service, _ = store_and_service
    team = service.create_team(lead_session_id="lead-resume", title="Resume Team")

    cfg = WorkerConfig(
        worker_id="w-resume-1",
        team_id=team.team_id,
        role="coder",
        harness="native",
        tokens_consumed=500,
    )
    worker = service.register_worker(cfg)

    # Save checkpoint
    cp = WorkerCheckpoint(
        checkpoint_id="cp-resume-1",
        worker_id=worker.session_id,
        team_id=team.team_id,
        step_index=3,
        state_summary="Midway checkpoint before power loss",
        tokens_consumed=850,
        context_snapshot={"last_file": "utils.py"},
    )
    store.save_checkpoint(cp)

    # Simulate worker crash
    service.set_worker_status(worker.session_id, WorkerStatus.FAILED)

    controller = WorkerProcessController(store=store)
    resumed_session = resume_worker_from_checkpoint(worker.session_id, store=store, controller=controller)

    try:
        assert resumed_session.session_id == worker.session_id
        assert resumed_session.status in (WorkerStatus.IDLE, WorkerStatus.RUNNING)
        # Cumulative tokens must reflect the checkpoint
        assert resumed_session.config.tokens_consumed == 850
        assert resumed_session.config.pid is not None
        assert resumed_session.config.pid > 0
    finally:
        controller.terminate_all()


def test_c05_durable_rehydration_across_restart(store_and_service):
    """Verify teams, workers, queues, and checkpoints survive cold disk rehydration."""
    store, service, db_path = store_and_service
    team = service.create_team(lead_session_id="lead-persist", title="Persistent Team")
    worker = service.register_worker(
        WorkerConfig(worker_id="w-persist-1", team_id=team.team_id, role="coder", harness="native")
    )
    item = service.dispatch_task(
        from_session_id=team.lead_session_id,
        to_session_id=worker.session_id,
        task_id="task-persist-1",
        payload={"data": 42},
    )
    store.save_checkpoint(
        WorkerCheckpoint(
            checkpoint_id="cp-persist-1",
            worker_id=worker.session_id,
            team_id=team.team_id,
            step_index=1,
            state_summary="Persisted checkpoint",
            tokens_consumed=100,
        )
    )

    # Close store to simulate shutdown
    store.close()

    # Reopen brand new store and service from the same db file
    with OrcaStore(db_path) as fresh_store:
        fresh_service = OrcaTeamService(store=fresh_store)

        loaded_team = fresh_service.load_team(team.team_id)
        assert loaded_team is not None
        assert loaded_team.title == "Persistent Team"

        loaded_worker = fresh_service.get_session(worker.session_id)
        assert loaded_worker is not None
        assert loaded_worker.orca_role == OrcaRole.WORKER

        loaded_queue = fresh_service.list_team_queue(team.team_id)
        assert len(loaded_queue) == 1
        assert loaded_queue[0].dispatch_id == item.dispatch_id

        loaded_cp = fresh_store.load_latest_checkpoint(worker.session_id)
        assert loaded_cp is not None
        assert loaded_cp.checkpoint_id == "cp-persist-1"
        assert loaded_cp.tokens_consumed == 100
