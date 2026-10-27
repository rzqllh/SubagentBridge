"""Post-v1.1.0 regression tests for explicit approval, SQLite transactions, and recovery."""
from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

from subagentbridge.approval.broker import ApprovalBroker
from subagentbridge.approval.trusted_authority import TrustedApprovalAuthority
from subagentbridge.domain.team_contracts import QueueTaskStatus, WorkerConfig
from subagentbridge.execution.worker_process import WorkerProcessController
from subagentbridge.recovery.crash_recovery import resume_task_from_checkpoint
from subagentbridge.storage.team_store import TeamStore
from subagentbridge.team.team_manager import TeamManager


def _setup(store: TeamStore, working_dir: str | None = None):
    manager = TeamManager(store)
    team = manager.create_team(lead_session_id="lead-v111", title="Runtime Guard")
    worker = manager.register_worker(
        WorkerConfig(worker_id="worker-v111", team_id=team.team_id,
                     role="coder", harness="native", working_dir=working_dir)
    )
    return manager, team, worker


def test_resume_claim_is_atomic_between_connections():
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "claims.db"
        with TeamStore(path) as store:
            manager, team, worker = _setup(store)
            task = manager.dispatch_task(team.lead_session_id, worker.session_id, "claim", {})
        barrier = threading.Barrier(2)
        successes: list[str] = []
        failures: list[Exception] = []

        def claim() -> None:
            with TeamStore(path) as store:
                barrier.wait(timeout=10)
                try:
                    successes.append(store.mark_task_resuming(task.dispatch_id).dispatch_id)
                except (RuntimeError, Exception) as err:
                    failures.append(err)

        threads = [threading.Thread(target=claim) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert not any(t.is_alive() for t in threads)
        assert successes == [task.dispatch_id]
        assert len(failures) == 1 and "already RUNNING" in str(failures[0])


def test_shared_connection_writes_are_serialized_under_dispatch_contention():
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "shared.db") as store:
        manager, team, worker = _setup(store)
        gate = threading.Barrier(3)
        errors: list[Exception] = []
        results: list[str] = []

        def dispatch() -> None:
            try:
                gate.wait(timeout=10)
                for _ in range(30):
                    item = manager.dispatch_task(
                        team.lead_session_id, worker.session_id,
                        "same-logical-task", {"instruction": "build"},
                        dedup_key="unique-cross-thread",
                    )
                    results.append(item.dispatch_id)
            except Exception as exc:
                errors.append(exc)

        def session_update() -> None:
            try:
                gate.wait(timeout=10)
                for _ in range(60):
                    current = store.load_session(worker.session_id)
                    assert current is not None
                    store.save_session(current)
            except Exception as exc:
                errors.append(exc)

        ts = [threading.Thread(target=dispatch), threading.Thread(target=dispatch),
              threading.Thread(target=session_update)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=20)
        assert not any(t.is_alive() for t in ts)
        assert not errors, errors
        assert len(results) == 60
        assert len(set(results)) == 1


def test_approval_is_preflighted_for_all_steps_before_any_command_executes():
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "approval.db") as store:
        manager, team, worker = _setup(store, root)
        counter = Path(root) / "counter.txt"
        code = ("from pathlib import Path; p=Path('counter.txt'); "
                "n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1))")
        item = manager.dispatch_task(
            team.lead_session_id, worker.session_id, "two-command-steps",
            {"steps": [
                {"name": "one", "command": [sys.executable, "-c", code]},
                {"name": "two", "command": [sys.executable, "-c", code]},
            ]},
        )
        broker = ApprovalBroker()
        authority = TrustedApprovalAuthority(broker)
        controller = WorkerProcessController(store, approval_authority=authority)
        try:
            first = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert first["status"] == "AWAITING_APPROVAL", first
            actions = first["pending_actions"]
            assert len(actions) == 2
            assert not counter.exists()
            authority.approve_by_human(actions[0]["action_id"], auth_token=broker._secret)
            second = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert second["status"] == "AWAITING_APPROVAL"
            assert second["pending_actions"][0]["action_id"] == actions[1]["action_id"]
            assert not counter.exists(), "A partial approval must never execute a first step"
            authority.approve_by_human(actions[1]["action_id"], auth_token=broker._secret)
            final = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert final["status"] == "COMPLETED", final
            assert counter.read_text() == "2"
        finally:
            controller.terminate_all()


def test_consumed_approval_is_renewed_not_replayed():
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "reapproval.db") as store:
        manager, team, worker = _setup(store, root)
        command = [sys.executable, "-c", "print('do-not-execute-until-authorized')"]
        item = manager.dispatch_task(team.lead_session_id, worker.session_id, "reapproval",
                                     {"command": command})
        broker = ApprovalBroker()
        authority = TrustedApprovalAuthority(broker)
        controller = WorkerProcessController(store, approval_authority=authority)
        try:
            first = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert first["status"] == "AWAITING_APPROVAL"
            authority.approve_by_human(first["action_id"], auth_token=broker._secret)
            valid, _ = authority.verify_and_consume(first["action_id"], worker.session_id,
                                                     item.task_id, command, root)
            assert valid
            next_attempt = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert next_attempt["status"] == "AWAITING_APPROVAL"
            assert next_attempt["action_id"] != first["action_id"]
        finally:
            controller.terminate_all()


def test_atomic_command_matches_configured_workspace_and_requires_approval():
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "atomic.db") as store:
        manager, team, worker = _setup(store, root)
        item = manager.dispatch_task(team.lead_session_id, worker.session_id, "atomic",
                                     {"command": [sys.executable, "-c", "print('approved')"]})
        broker = ApprovalBroker()
        authority = TrustedApprovalAuthority(broker)
        controller = WorkerProcessController(store, approval_authority=authority)
        try:
            pending = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert pending["status"] == "AWAITING_APPROVAL"
            assert controller.get_worker_record(worker.session_id).worktree_path == root
            authority.approve_by_human(pending["action_id"], auth_token=broker._secret)
            completed = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert completed["status"] == "COMPLETED", completed
            assert store.load_queue_item(item.dispatch_id).status == QueueTaskStatus.COMPLETED
        finally:
            controller.terminate_all()


def test_command_without_trusted_authority_fails_closed():
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "default_deny.db") as store:
        manager, team, worker = _setup(store, root)
        item = manager.dispatch_task(team.lead_session_id, worker.session_id, "default-deny",
                                     {"command": [sys.executable, "-c", "print('blocked')"]})
        controller = WorkerProcessController(store)
        try:
            response = resume_task_from_checkpoint(item.dispatch_id, store, controller)
            assert response["status"] == "RECOVERY_BLOCKED"
            assert store.load_queue_item(item.dispatch_id).status == QueueTaskStatus.DISPATCHED
        finally:
            controller.terminate_all()
