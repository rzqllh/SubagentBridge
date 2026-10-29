"""PAR-04 review regressions: truthful router, IPC ownership and reconfigure safety."""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from subagentbridge.domain.team_contracts import WorkerConfig, WorkerStatus, QueueItem, QueueTaskStatus
from subagentbridge.recovery.crash_recovery import resume_task_from_checkpoint
from subagentbridge.execution.worker_process import TimedStreamReader, WorkerProcessController
from subagentbridge.runners.harness_adapters import get_harness_registry
from subagentbridge.storage.team_store import TeamStore


def test_ipc_control_ack_never_consumes_previous_task_result():
    previous = json.dumps({"type": "RESULT", "task_id": "old", "status": "COMPLETED"}) + "\n"
    confirmation = json.dumps({
        "type": "RECONFIGURED", "request_id": "expected",
        "worker_id": "worker", "fallback_to_native": True,
    }) + "\n"
    reader = TimedStreamReader(io.StringIO(previous + confirmation))
    matching = reader.readline_matching(
        lambda raw: json.loads(raw)["request_id"] == "expected"
        if json.loads(raw).get("type") == "RECONFIGURED" else False,
        timeout=1.0,
    )
    assert matching is not None
    assert json.loads(matching)["type"] == "RECONFIGURED"
    assert reader.readline(timeout=1.0) == previous
    assert reader.readline(timeout=0.01) is None


def test_unreachable_router_does_not_fabricate_completion_or_usage(monkeypatch):
    monkeypatch.setenv("NINEROUTER_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("NINEROUTER_API_KEY", "test-not-a-live-router")
    adapter = get_harness_registry().get("9router")
    assert not adapter.get_capabilities().is_available
    res = adapter.execute(
        "r", "invent a success", WorkerConfig(worker_id="w", team_id="t", harness="9router"),
    )
    assert res["status"] == "UNSUPPORTED_HOST"
    assert not any(field in res for field in ("metered_tokens", "evidence", "summary"))


def test_interrupted_idle_worker_keeps_attached_pipes_and_can_resume():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with TeamStore(Path(tmp_dir) / "teams.db") as store:
            controller = WorkerProcessController(store)
            controller.spawn_worker(
                WorkerConfig(worker_id="interrupted", team_id="team", harness="native"),
                worktree_path=tmp_dir,
            )
            try:
                assert controller.interrupt_worker("interrupted", task_id="unused")
                assert controller.has_attached_worker_ipc("interrupted")
                assert not controller.is_worker_dispatchable("interrupted")
                assert controller.resume_worker("interrupted")
                assert controller.is_worker_dispatchable("interrupted")
            finally:
                controller.terminate_worker("interrupted")


def test_fallback_setting_is_preserved_by_live_switch_and_child():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with TeamStore(Path(tmp_dir) / "teams.db") as store:
            controller = WorkerProcessController(store)
            controller.spawn_worker(
                WorkerConfig(
                    worker_id="fallback", team_id="team", harness="native",
                    fallback_to_native=True,
                ), worktree_path=tmp_dir,
            )
            try:
                assert controller.switch_worker_harness("fallback", "9router")
                session = store.load_session("fallback")
                assert session is not None and session.config.fallback_to_native is True
                result = controller.dispatch_task_to_worker(
                    "fallback", "fallback-test",
                    {"instruction": "create_file:fallback.txt:real native fallback"},
                    timeout=5.0,
                )
                assert result["status"] == "COMPLETED"
                assert result["fallback_from"] == "9router"
                assert (Path(tmp_dir) / "fallback.txt").read_text() == "real native fallback"
            finally:
                controller.terminate_worker("fallback")


def test_unacknowledged_reconfigure_fails_closed_and_keeps_old_config():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with TeamStore(Path(tmp_dir) / "teams.db") as store:
            controller = WorkerProcessController(store)
            controller.spawn_worker(
                WorkerConfig(worker_id="no-ack", team_id="team", harness="native"),
                worktree_path=tmp_dir,
            )
            with patch.object(
                controller._readers["no-ack"], "readline_matching", return_value=None,
            ):
                with pytest.raises(RuntimeError, match="No matching RECONFIGURED acknowledgement"):
                    controller.switch_worker_harness("no-ack", "pi")
            session = store.load_session("no-ack")
            assert session is not None
            assert session.config.harness == "native"
            assert not controller.has_attached_worker_ipc("no-ack")


def test_outstanding_async_result_prevents_harness_switch():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with TeamStore(Path(tmp_dir) / "teams.db") as store:
            controller = WorkerProcessController(store)
            controller.spawn_worker(
                WorkerConfig(worker_id="busy", team_id="team", harness="native"),
                worktree_path=tmp_dir,
            )
            try:
                controller.send_task_async("busy", "slow", {
                    "instruction": "create_file:async.txt:async receipt",
                })
                with pytest.raises(RuntimeError, match="outstanding"):
                    controller.switch_worker_harness("busy", "pi")
                result = controller.collect_async_result("busy", "slow", timeout=5.0)
                assert result["status"] == "COMPLETED"
                assert (Path(tmp_dir) / "async.txt").read_text() == "async receipt"
                assert controller.is_worker_dispatchable("busy")
                assert controller.switch_worker_harness("busy", "pi")
                session = store.load_session("busy")
                assert session is not None and session.config.harness == "pi"
            finally:
                controller.terminate_worker("busy")


def test_recovery_blocked_attached_worker_does_not_poison_retry_claim():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with TeamStore(Path(tmp_dir) / "teams.db") as store:
            item = QueueItem(
                dispatch_id="retry-dispatch", team_id="team",
                from_session_id="lead", to_session_id="worker",
                task_id="task", payload={"instruction": "inspect"},
            )
            store.save_queue_item(item)
            controller = WorkerProcessController(store)
            with (
                patch.object(controller, "is_worker_alive", return_value=True),
                patch.object(controller, "has_attached_worker_ipc", return_value=True),
                patch.object(controller, "is_worker_dispatchable", return_value=False),
                patch.object(controller, "resume_worker", return_value=False),
            ):
                blocked = resume_task_from_checkpoint(
                    "retry-dispatch", store=store, controller=controller,
                )
            assert blocked["status"] == "RECOVERY_BLOCKED"
            assert store.load_queue_item("retry-dispatch").status == QueueTaskStatus.DISPATCHED
            retried = store.mark_task_resuming("retry-dispatch")
            assert retried.status == QueueTaskStatus.RUNNING


def test_invalid_capability_is_task_level_denial_not_worker_crash():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with TeamStore(Path(tmp_dir) / "teams.db") as store:
            controller = WorkerProcessController(store)
            controller.spawn_worker(
                WorkerConfig(worker_id="capabilities", team_id="team", harness="native"),
                worktree_path=tmp_dir,
            )
            try:
                invalid = controller.dispatch_task_to_worker(
                    "capabilities", "bad-caps",
                    {"instruction": "echo should not run",
                     "required_capabilities": ["NOT_A_CAPABILITY"]},
                )
                assert invalid["status"] == "DENIED"
                assert controller.has_attached_worker_ipc("capabilities")
                valid = controller.dispatch_task_to_worker(
                    "capabilities", "after-bad-caps",
                    {"instruction": "create_file:after-denial.txt:alive"},
                )
                assert valid["status"] == "COMPLETED"
                assert (Path(tmp_dir) / "after-denial.txt").read_text() == "alive"
            finally:
                controller.terminate_worker("capabilities")
