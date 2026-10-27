"""Release correctness regressions: mixed legacy schema, queue concurrency, resume governance."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from subagentbridge.approval.broker import ApprovalBroker
from subagentbridge.approval.trusted_authority import TrustedApprovalAuthority
from subagentbridge.domain.team_contracts import QueueTaskStatus, WorkerConfig
from subagentbridge.execution.worker_process import WorkerProcessController
from subagentbridge.recovery.crash_recovery import resume_task_from_checkpoint
from subagentbridge.storage.team_store import TeamStore
from subagentbridge.team.team_manager import TeamManager


def make_team(store: TeamStore) -> tuple[TeamManager, str, str]:
    manager = TeamManager(store)
    team = manager.create_team(lead_session_id="lead-release", title="Release Team")
    worker = manager.register_worker(WorkerConfig(
        worker_id="worker-release", team_id=team.team_id, role="worker", harness="native",
    ))
    return manager, team.lead_session_id, worker.session_id


@pytest.mark.parametrize("optional", [
    {"dedup_key": ("TEXT", "kept-key")},
    {"priority": ("INTEGER NOT NULL DEFAULT 0", 17), "dedup_key": ("TEXT", "kept-key")},
    {"steering_json": ("TEXT NOT NULL DEFAULT '[]'", '["keep"]'), "priority": ("INTEGER NOT NULL DEFAULT 0", 9)},
])
def test_c08_partial_legacy_queue_columns_preserved(optional):
    with tempfile.TemporaryDirectory() as root:
        db = Path(root) / "legacy.db"
        conn = sqlite3.connect(str(db))
        columns = [
            "dispatch_id TEXT PRIMARY KEY", "team_id TEXT NOT NULL",
            "from_session_id TEXT NOT NULL", "to_session_id TEXT NOT NULL",
            "task_id TEXT NOT NULL", "payload_json TEXT NOT NULL",
            "status TEXT NOT NULL",
            *[f"{name} {definition}" for name, (definition, _) in optional.items()],
            "created_at REAL NOT NULL", "updated_at REAL NOT NULL",
        ]
        conn.executescript("""
            CREATE TABLE orca_teams (
                team_id TEXT PRIMARY KEY, lead_session_id TEXT NOT NULL,
                title TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE orca_sessions (
                session_id TEXT PRIMARY KEY, orca_role TEXT NOT NULL,
                team_id TEXT NOT NULL, status TEXT NOT NULL,
                config_json TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
        """ + "CREATE TABLE orca_queue (" + ", ".join(columns) + ");")
        conn.execute("INSERT INTO orca_teams VALUES (?, ?, ?, ?)", ("t", "lead", "T", 1.0))
        for identifier, role in (("lead", "lead"), ("worker", "worker")):
            conn.execute(
                "INSERT INTO orca_sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (identifier, role, "t", "IDLE", json.dumps({"worker_id": identifier, "team_id": "t", "role": role}), 1.0, 1.0),
            )
        row_data = {
            "dispatch_id": "d", "team_id": "t", "from_session_id": "lead",
            "to_session_id": "worker", "task_id": "task", "payload_json": "{}",
            "status": "PENDING", "created_at": 1.0, "updated_at": 1.0,
            **{key: value for key, (_, value) in optional.items()},
        }
        names = list(row_data)
        conn.execute(
            "INSERT INTO orca_queue (" + ", ".join(names) + ") VALUES (" + ", ".join("?" for _ in names) + ")",
            tuple(row_data.values()),
        )
        conn.commit()
        conn.close()
        with TeamStore(db) as store:
            row = store._conn.execute("SELECT * FROM simpul_queue WHERE dispatch_id = 'd'").fetchone()
            assert row is not None
            assert row["dedup_key"] == optional.get("dedup_key", (None, None))[1]
            assert row["priority"] == optional.get("priority", (None, 0))[1]
            assert row["steering_json"] == optional.get("steering_json", (None, "[]"))[1]
        with TeamStore(db) as store:
            assert store.load_queue_item("d") is not None


def test_c08_dedup_prefers_active_retry_over_cancelled_history():
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "tasks.db") as store:
        manager, lead, worker = make_team(store)
        first = manager.dispatch_task(lead, worker, "first", {"instruction": "A"}, dedup_key="same")
        manager.cancel_task(lead, first.dispatch_id)
        retry = manager.dispatch_task(lead, worker, "retry", {"instruction": "B"}, dedup_key="same")
        repeated = manager.dispatch_task(lead, worker, "repeated", {"instruction": "B"}, dedup_key="same")
        assert retry.dispatch_id != first.dispatch_id
        assert retry.dispatch_id == repeated.dispatch_id
        assert len([x for x in manager.list_team_queue(retry.team_id)
                    if x.status == QueueTaskStatus.PENDING]) == 1


def test_c08_dedup_single_dispatch_across_concurrent_connections():
    with tempfile.TemporaryDirectory() as root:
        db = Path(root) / "concurrent.db"
        with TeamStore(db) as seed:
            _, lead, worker = make_team(seed)
        barrier = threading.Barrier(2)
        ids: list[str] = []
        errors: list[Exception] = []

        def dispatch() -> None:
            try:
                with TeamStore(db) as store:
                    manager = TeamManager(store)
                    barrier.wait(timeout=10)
                    item = manager.dispatch_task(lead, worker, "same-task", {"instruction": "build"}, dedup_key="atomic")
                    ids.append(item.dispatch_id)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=dispatch) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        assert not any(thread.is_alive() for thread in threads)
        assert not errors, errors
        assert len(ids) == 2 and len(set(ids)) == 1
        with TeamStore(db) as store:
            assert len([x for x in store.list_queue_by_team(store.load_session(lead).team_id)
                        if x.dedup_key == "atomic"]) == 1


def test_c08_cancel_cannot_reverse_completed_outcome():
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "tasks.db") as store:
        manager, lead, worker = make_team(store)
        item = manager.dispatch_task(lead, worker, "finished", {})
        manager.update_queue_status(item.dispatch_id, QueueTaskStatus.COMPLETED)
        with pytest.raises(ValueError, match="terminal"):
            manager.cancel_task(lead, item.dispatch_id)
        assert store.load_queue_item(item.dispatch_id).status == QueueTaskStatus.COMPLETED


def test_c08_orphaned_os_worker_is_not_treated_as_attached_ipc(monkeypatch):
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "state.db") as store:
        manager, lead, worker = make_team(store)
        item = manager.dispatch_task(lead, worker, "resume", {"instruction": "do something"})
        controller = WorkerProcessController(store)
        monkeypatch.setattr(controller, "is_worker_alive", lambda _: True)
        assert controller.has_attached_worker(worker) is False
        result = resume_task_from_checkpoint(item.dispatch_id, store, controller)
        assert result["status"] == "BLOCKED"
        assert result["reason"] == "ORPHANED_WORKER_IPC"
        assert store.load_queue_item(item.dispatch_id).status == QueueTaskStatus.DISPATCHED


def test_c08_resume_does_not_replace_existing_pending_human_approval():
    with tempfile.TemporaryDirectory() as root, TeamStore(Path(root) / "approval.db") as store:
        manager, lead, worker = make_team(store)
        item = manager.dispatch_task(
            lead, worker, "approved-work",
            {"steps": [{"name": "step-1", "command": [sys.executable, "-c", "print('allowed')"]}]},
        )
        broker = ApprovalBroker()
        authority = TrustedApprovalAuthority(broker)
        controller = WorkerProcessController(store, approval_authority=authority)
        try:
            first = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert first["status"] == "BLOCKED"
            assert first["reason"] == "HUMAN_APPROVAL_REQUIRED"
            second = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert second["status"] == "BLOCKED"
            assert first["action_id"] == second["action_id"]
            # A real external approval is required. Test-only credential stays in fixture.
            authority.approve_by_human(first["action_id"], auth_token=broker._secret)
            resumed = resume_task_from_checkpoint(item.dispatch_id, store, controller, authority)
            assert resumed["status"] == "COMPLETED"
        finally:
            controller.terminate_all()
