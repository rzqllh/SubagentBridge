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
from subagentbridge.execution.worker_process import (
    WorkerProcessController,
    kill_process_tree,
)
from subagentbridge.recovery.crash_recovery import (
    reconcile_team_after_crash,
    resume_task_from_checkpoint,
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


def test_c05_worktree_never_deletes_existing_user_dir():
    """Gate 1: Verify manager rejects existing directory and preserves user files without deletion."""
    with tempfile.TemporaryDirectory() as tmp_git_root, tempfile.TemporaryDirectory() as tmp_db:
        repo_path = Path(tmp_git_root)
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "test@test.com"], check=True)
        (repo_path / "README.md").write_text("# Repo")
        subprocess.run(["git", "-C", str(repo_path), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True)

        with OrcaStore(Path(tmp_db) / "orca_wt.db") as store:
            manager = GitWorktreeManager(repo_root=repo_path, store=store)

            # Pre-create a target directory where the worker would be allocated
            pre_existing_dir = manager.worktrees_dir / "w-user_worker"
            pre_existing_dir.mkdir(parents=True)
            precious_file = pre_existing_dir / "precious_user_data.txt"
            precious_file.write_text("DO_NOT_DELETE")

            # Must raise FileExistsError and refuse to delete or overwrite
            with pytest.raises(FileExistsError):
                manager.create_worktree(
                    worker_id="user_worker",
                    team_id="team-wt",
                    branch_name="simpul/worker-user-1",
                )

            # Assert file was NOT deleted
            assert precious_file.exists()
            assert precious_file.read_text() == "DO_NOT_DELETE"


def test_c05_worktree_cleanup_rejects_dirty_tracked_files():
    """Gate 1: Cleanup must fail closed when uncommitted tracked changes exist in the worktree."""
    with tempfile.TemporaryDirectory() as tmp_git_root, tempfile.TemporaryDirectory() as tmp_db:
        repo_path = Path(tmp_git_root)
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "test@test.com"], check=True)
        (repo_path / "README.md").write_text("# Repo")
        subprocess.run(["git", "-C", str(repo_path), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True)

        with OrcaStore(Path(tmp_db) / "orca_wt.db") as store:
            manager = GitWorktreeManager(repo_root=repo_path, store=store)
            assignment = manager.create_worktree(
                worker_id="dirty_worker",
                team_id="team-wt",
                branch_name="simpul/dirty-1",
            )
            wt_path = Path(assignment.worktree_path)

            # Introduce uncommitted change to a tracked file
            (wt_path / "README.md").write_text("# Uncommitted Changes")

            # Must raise RuntimeError and refuse cleanup
            with pytest.raises(RuntimeError, match="Cannot cleanup dirty worktree"):
                manager.cleanup_worktree(worker_id="dirty_worker")

            # Assert directory and uncommitted changes are preserved
            assert wt_path.exists()
            assert (wt_path / "README.md").read_text() == "# Uncommitted Changes"

            # Assert ownership record in store was preserved
            assert store.load_worktree("dirty_worker") is not None


def test_c05_worktree_cleanup_rejects_untracked_files():
    """Gate 1: Cleanup must fail closed when untracked user files exist in the worktree."""
    with tempfile.TemporaryDirectory() as tmp_git_root, tempfile.TemporaryDirectory() as tmp_db:
        repo_path = Path(tmp_git_root)
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "test@test.com"], check=True)
        (repo_path / "README.md").write_text("# Repo")
        subprocess.run(["git", "-C", str(repo_path), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True)

        with OrcaStore(Path(tmp_db) / "orca_wt.db") as store:
            manager = GitWorktreeManager(repo_root=repo_path, store=store)
            assignment = manager.create_worktree(
                worker_id="untracked_worker",
                team_id="team-wt",
                branch_name="simpul/untracked-1",
            )
            wt_path = Path(assignment.worktree_path)

            # Introduce untracked file
            (wt_path / "untracked_new_file.py").write_text("print('user code')")

            with pytest.raises(RuntimeError, match="untracked files"):
                manager.cleanup_worktree(worker_id="untracked_worker")

            # Assert untracked file and worktree still exist
            assert wt_path.exists()
            assert (wt_path / "untracked_new_file.py").exists()
            assert store.load_worktree("untracked_worker") is not None


def test_c05_worktree_rejects_normalization_collision_and_path_traversal():
    """Gate 1: Refuse worker ID normalization collisions and path traversal escapes."""
    with tempfile.TemporaryDirectory() as tmp_git_root, tempfile.TemporaryDirectory() as tmp_db:
        repo_path = Path(tmp_git_root)
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "test@test.com"], check=True)
        (repo_path / "README.md").write_text("# Repo")
        subprocess.run(["git", "-C", str(repo_path), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True)

        with OrcaStore(Path(tmp_db) / "orca_wt.db") as store:
            manager = GitWorktreeManager(repo_root=repo_path, store=store)

            # Ambiguous normalization attempts must be rejected with ValueError
            with pytest.raises(ValueError, match="Invalid worker_id"):
                manager.create_worktree(
                    worker_id="worker/1",
                    team_id="team-wt",
                    branch_name="simpul/branch-1",
                )

            with pytest.raises(ValueError, match="Invalid worker_id"):
                manager.create_worktree(
                    worker_id="worker:1",
                    team_id="team-wt",
                    branch_name="simpul/branch-2",
                )

            with pytest.raises(ValueError, match="Invalid worker_id"):
                manager.create_worktree(
                    worker_id="../../escape",
                    team_id="team-wt",
                    branch_name="simpul/branch-3",
                )


def test_c05_true_durable_task_resume_without_duplicate_execution():
    """Gate 2: Start bounded work, checkpoint, kill worker, restart controller, resume logical task."""
    with tempfile.TemporaryDirectory() as tmp_git_root, tempfile.TemporaryDirectory() as tmp_db:
        repo_path = Path(tmp_git_root)
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "test@test.com"], check=True)
        (repo_path / "README.md").write_text("# Init")
        subprocess.run(["git", "-C", str(repo_path), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True)

        with OrcaStore(Path(tmp_db) / "orca_resume.db") as store:
            service = OrcaTeamService(store=store)
            manager = GitWorktreeManager(repo_root=repo_path, store=store)

            team = service.create_team(lead_session_id="lead-resume-gate2", title="Gate 2 Team")

            # 1. Create worker and assign worktree
            wt_assign = manager.create_worktree(
                worker_id="w-resume-task",
                team_id=team.team_id,
                branch_name="simpul/resume-task-1",
            )
            cfg = WorkerConfig(
                worker_id="w-resume-task",
                team_id=team.team_id,
                role="coder",
                harness="native",
                working_dir=wt_assign.worktree_path,
                tokens_consumed=100,
            )
            worker = service.register_worker(cfg)

            # Controller spawns initial worker child process
            ctrl1 = WorkerProcessController(store=store)
            rec1 = ctrl1.spawn_worker(worker.config, worktree_path=wt_assign.worktree_path)

            try:
                # 2. Dispatch a 2-step bounded task to the worker
                # Step 1: create module_a.py
                # Step 2: create module_b.py
                task_payload = {
                    "task_type": "multi_step",
                    "steps": [
                        {"name": "step_a", "instruction": "create_file:module_a.py:def fa(): return 1\n"},
                        {"name": "step_b", "instruction": "create_file:module_b.py:def fb(): return 2\n"},
                    ],
                }
                item = service.dispatch_task(
                    from_session_id=team.lead_session_id,
                    to_session_id=worker.session_id,
                    task_id="task-multi-step",
                    payload=task_payload,
                )

                # 3. Simulate execution of step 1 only and record checkpoint
                res1 = ctrl1.dispatch_task_to_worker(
                    worker.session_id,
                    f"{item.task_id}-step_a",
                    {"instruction": "create_file:module_a.py:def fa(): return 1\n", "workspace_path": wt_assign.worktree_path},
                )
                assert res1["status"] == "COMPLETED"
                file_a = Path(wt_assign.worktree_path) / "module_a.py"
                assert file_a.exists()
                assert "def fa():" in file_a.read_text()

                # Record step 1 checkpoint
                cp1 = WorkerCheckpoint(
                    checkpoint_id="cp-step-a",
                    worker_id=worker.session_id,
                    team_id=team.team_id,
                    step_index=1,
                    state_summary="Completed step_a (created module_a.py)",
                    tokens_consumed=250,
                    context_snapshot={
                        "dispatch_id": item.dispatch_id,
                        "task_id": item.task_id,
                        "completed_steps": ["step_a"],
                        "worktree_path": wt_assign.worktree_path,
                    },
                )
                store.save_checkpoint(cp1)

                # 4. KILL executing worker child process (simulate mid-task crash)
                kill_process_tree(rec1.pid)

                # Verify worker is dead
                assert not ctrl1.is_worker_alive(worker.session_id)

                # Reconcile team after crash
                report = reconcile_team_after_crash(team.team_id, store=store)
                assert report["reconciled_workers"] == 1
                assert "w-resume-task" in report["dead_workers"]

            finally:
                ctrl1.terminate_all()

            # 5. RESTART controller and resume logical task from checkpoint
            ctrl2 = WorkerProcessController(store=store)
            try:
                resume_report = resume_task_from_checkpoint(
                    dispatch_id=item.dispatch_id,
                    store=store,
                    controller=ctrl2,
                )

                # 6. Verify continuation properties
                assert resume_report["status"] == "COMPLETED"
                # Step A was skipped without duplicate execution
                assert "step_a" in resume_report["skipped_steps"]
                # Step B was executed
                assert "step_b" in resume_report["completed_steps"]

                # File B exists now
                file_b = Path(wt_assign.worktree_path) / "module_b.py"
                assert file_b.exists()
                assert "def fb():" in file_b.read_text()

                # File A was untouched
                assert file_a.exists()
                assert "def fa():" in file_a.read_text()

                # Token budget accounted for both steps without loss
                assert resume_report["tokens_consumed"] >= 250

                # Queue item transitioned to COMPLETED
                reloaded_item = store.load_queue_item(item.dispatch_id)
                assert reloaded_item is not None
                assert reloaded_item.status == QueueTaskStatus.COMPLETED

            finally:
                ctrl2.terminate_all()


def test_c05_worktree_cleanup_rejects_ignored_user_files():
    """Gate 1: Verify cleanup fails closed when user-created ignored files are present."""
    with tempfile.TemporaryDirectory() as tmp_git_root, tempfile.TemporaryDirectory() as tmp_db:
        repo_path = Path(tmp_git_root)
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "config", "user.email", "test@test.com"], check=True)
        (repo_path / ".gitignore").write_text("*.log\n")
        (repo_path / "README.md").write_text("# Repo")
        subprocess.run(["git", "-C", str(repo_path), "add", ".gitignore", "README.md"], check=True)
        subprocess.run(["git", "-C", str(repo_path), "commit", "-m", "init"], check=True)

        with OrcaStore(Path(tmp_db) / "orca_wt.db") as store:
            manager = GitWorktreeManager(repo_root=repo_path, store=store)
            assignment = manager.create_worktree(
                worker_id="ignored_worker",
                team_id="team-wt",
                branch_name="simpul/ignored-1",
            )
            wt_path = Path(assignment.worktree_path)

            # Introduce an ignored file created by user/worker
            user_log = wt_path / "user_debug.log"
            user_log.write_text("IMPORTANT_USER_DEBUG_LOG")

            # Must fail closed on ignored user files
            with pytest.raises(RuntimeError, match="uncommitted changes, untracked files, or user modifications present"):
                manager.cleanup_worktree(worker_id="ignored_worker")

            # Assert file and assignment survive
            assert user_log.exists()
            assert store.load_worktree("ignored_worker") is not None


def test_c05_resume_task_rejects_checkpoint_from_different_dispatch():
    """Gate 2: Checkpoint from another dispatch must never cause steps of a new dispatch to be skipped."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "orca_resume_mismatch.db"
        with OrcaStore(db_path) as store:
            service = OrcaTeamService(store=store)
            controller = WorkerProcessController(store=store)

            team = service.create_team(lead_session_id="lead-res-mismatch", title="Resume Mismatch Team")
            cfg = WorkerConfig(
                worker_id="w-mismatch-1",
                team_id=team.team_id,
                role="worker",
                harness="native",
                working_dir=tmp_dir,
            )
            worker = service.register_worker(cfg)

            # Pre-seed a checkpoint belonging to an OLD dispatch (dispatch_id: 'dsp-old-123')
            store.save_checkpoint(
                WorkerCheckpoint(
                    checkpoint_id="cp-old-dispatch",
                    worker_id=worker.session_id,
                    team_id=team.team_id,
                    step_index=1,
                    state_summary="Completed step_x in old dispatch",
                    tokens_consumed=100,
                    context_snapshot={
                        "dispatch_id": "dsp-old-123",
                        "task_id": "task-old-1",
                        "completed_steps": ["step_x"],
                        "worktree_path": tmp_dir,
                    },
                )
            )

            # Dispatch NEW task with a step named 'step_x' that should NOT be skipped
            item = service.dispatch_task(
                from_session_id=team.lead_session_id,
                to_session_id=worker.session_id,
                task_id="task-new-1",
                payload={
                    "steps": [
                        {"name": "step_x", "instruction": "create_file:new_target.txt:NEW_DATA\n"},
                    ]
                },
            )

            try:
                report = resume_task_from_checkpoint(
                    dispatch_id=item.dispatch_id,
                    store=store,
                    controller=controller,
                )

                assert report["status"] == "COMPLETED"
                # step_x was NOT skipped because the checkpoint belonged to dsp-old-123
                assert "step_x" not in report.get("skipped_steps", [])
                assert "step_x" in report.get("completed_steps", [])

                target_file = Path(tmp_dir) / "new_target.txt"
                assert target_file.exists()
                assert target_file.read_text().strip() == "NEW_DATA"

            finally:
                controller.terminate_all()


