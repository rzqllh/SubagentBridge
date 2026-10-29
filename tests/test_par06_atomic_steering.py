"""PAR-06: durable queue steering/priority concurrency and permission regressions."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from subagentbridge.domain.team_contracts import QueueTaskStatus, WorkerConfig
from subagentbridge.storage.team_store import TeamStore
from subagentbridge.team.team_manager import TeamManager


def _setup(store: TeamStore) -> tuple[TeamManager, str]:
    manager = TeamManager(store)
    manager.create_team("team-a", "lead-a", "A")
    manager.create_team("team-b", "lead-b", "B")
    manager.create_worker("team-a", WorkerConfig(worker_id="worker-a", team_id="team-a"))
    item = manager.dispatch_task("lead-a", "worker-a", "task", {"instruction": "readonly"}, priority=1)
    return manager, item.dispatch_id


def test_steering_and_priority_preserve_original_task_and_owner():
    with TemporaryDirectory() as td, TeamStore(Path(td) / "store.db") as store:
        manager, task_id = _setup(store)
        with pytest.raises(PermissionError):
            manager.steer_task("lead-b", task_id, "overwrite")
        with pytest.raises(PermissionError):
            manager.steer_task("worker-a", task_id, "worker self-guidance")
        with pytest.raises(PermissionError):
            manager.steer_task("lead-a", task_id, {"approved": True})
        with pytest.raises(ValueError):
            manager.reprioritize_task("lead-a", task_id, 1000)
        original = manager.get_queue_item(task_id)
        assert original is not None
        result = manager.steer_task("lead-a", task_id, {"note": "prioritize QA"})
        assert result.payload == original.payload
        assert result.status == QueueTaskStatus.PENDING
        assert result.steering_instructions[-1]["steered_by"] == "lead-a"
        prioritized = manager.reprioritize_task("lead-a", task_id, 90)
        assert prioritized.priority == 90
        assert prioritized.payload == original.payload


def test_concurrent_steering_never_drops_events_or_duplicates_task():
    with TemporaryDirectory() as td:
        db = Path(td) / "store.db"
        with TeamStore(db) as root:
            _, task_id = _setup(root)
        with TeamStore(db) as a, TeamStore(db) as b:
            ma, mb = TeamManager(a), TeamManager(b)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(ma.steer_task, "lead-a", task_id, "from-a"),
                    pool.submit(mb.steer_task, "lead-a", task_id, "from-b"),
                ]
                for future in futures:
                    assert future.result(timeout=10).status == QueueTaskStatus.PENDING
            stored = a.load_queue_item(task_id)
            assert stored is not None
            assert {x["guidance"] for x in stored.steering_instructions} == {"from-a", "from-b"}


def test_cancel_vs_steer_and_reprioritize_cannot_resurrect_terminal_task():
    with TemporaryDirectory() as td:
        db = Path(td) / "store.db"
        with TeamStore(db) as root:
            _, task_id = _setup(root)
        with TeamStore(db) as left, TeamStore(db) as right:
            lead_a = TeamManager(left)
            lead_b = TeamManager(right)
            with ThreadPoolExecutor(max_workers=2) as pool:
                cancel = pool.submit(lead_a.cancel_task, "lead-a", task_id, "stop")
                steer = pool.submit(lead_b.steer_task, "lead-a", task_id, "late")
                assert cancel.result(timeout=10).status == QueueTaskStatus.CANCELLED
                try:
                    assert steer.result(timeout=10).status == QueueTaskStatus.PENDING
                except ValueError:
                    pass
            row = left.load_queue_item(task_id)
            assert row is not None and row.status == QueueTaskStatus.CANCELLED
            assert row.payload == {"instruction": "readonly"}
            with pytest.raises(ValueError):
                lead_a.steer_task("lead-a", task_id, "post-cancel")
            with pytest.raises(ValueError):
                lead_a.reprioritize_task("lead-a", task_id, 99)
            assert left.load_queue_item(task_id).status == QueueTaskStatus.CANCELLED


def test_priority_is_refused_once_task_is_dispatched():
    with TemporaryDirectory() as td, TeamStore(Path(td) / "store.db") as store:
        manager, task_id = _setup(store)
        manager.update_queue_status(task_id, QueueTaskStatus.DISPATCHED)
        with pytest.raises(ValueError, match="pending"):
            manager.reprioritize_task("lead-a", task_id, 45)
        assert manager.steer_task("lead-a", task_id, "context only").priority == 1
