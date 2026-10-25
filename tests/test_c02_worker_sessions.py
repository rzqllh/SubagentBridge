"""Unit tests for Phase C02: Independent Worker Sessions Lifecycle.

Validates that worker sessions are real independent OS processes, not
in-process role simulations:
1. Real child process spawn with distinct OS PID.
2. Inter-process communication (IPC) for heartbeat and status.
3. IPC task dispatch and structured result receipt.
4. Worker interrupt preemption over IPC.
5. Clean process termination and file-descriptor cleanup.
6. Reaping crashed or stale worker child processes.
7. Per-worker token/turn budget enforcement.
8. Restart reconciliation detecting dead PIDs without false-active claims.
9. Fail-closed rejection of unapproved commands inside worker process.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from subagentbridge.domain.orca_contracts import (
    WorkerStatus,
    WorkerConfig,
)
from subagentbridge.storage.orca_store import OrcaStore
from subagentbridge.execution.worker_process import (
    WorkerProcessController,
    WorkerProcessRecord,
)


def test_c02_real_worker_process_spawn():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(
                worker_id="w-proc-1",
                team_id="team-proc",
                role="coder",
                harness="native",
                model="claude-3-5-sonnet",
            )

            record = controller.spawn_worker(cfg)
            try:
                assert isinstance(record, WorkerProcessRecord)
                assert record.worker_id == "w-proc-1"
                assert record.pid > 0
                assert record.pid != os.getpid(), "Worker must be a distinct OS process, not same process"
                assert record.status == WorkerStatus.IDLE
                assert controller.is_worker_alive("w-proc-1") is True
            finally:
                controller.terminate_worker("w-proc-1")


def test_c02_worker_heartbeat_and_status():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-hb-1", team_id="team-proc", role="tester")

            controller.spawn_worker(cfg)
            try:
                # Ping worker process over IPC
                pong = controller.ping_worker("w-hb-1", timeout=3.0)
                assert pong is not None
                assert pong.get("type") == "PONG"
                assert pong.get("worker_id") == "w-hb-1"

                record = controller.get_worker_record("w-hb-1")
                assert record is not None
                assert record.last_heartbeat > 0
            finally:
                controller.terminate_worker("w-hb-1")


def test_c02_worker_task_dispatch_ipc():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-task-1", team_id="team-proc", role="executor")

            controller.spawn_worker(cfg)
            try:
                payload = {"instruction": "echo hello", "args": ["hello"]}
                result = controller.dispatch_task_to_worker(
                    worker_id="w-task-1",
                    task_id="task-c02-1",
                    payload=payload,
                    timeout=5.0,
                )

                assert result["status"] == "COMPLETED"
                assert result["task_id"] == "task-c02-1"
                assert "summary" in result
            finally:
                controller.terminate_worker("w-task-1")


def test_c02_worker_interrupt_preemption():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-int-1", team_id="team-proc", role="worker")

            controller.spawn_worker(cfg)
            try:
                # Start a long-running task
                controller.send_task_async(
                    worker_id="w-int-1",
                    task_id="task-int-1",
                    payload={"instruction": "sleep", "duration": 10},
                )

                # Send interrupt command over IPC
                time.sleep(0.2)
                interrupted = controller.interrupt_worker("w-int-1")
                assert interrupted is True

                record = controller.get_worker_record("w-int-1")
                assert record is not None
                assert record.status == WorkerStatus.INTERRUPTED
            finally:
                controller.terminate_worker("w-int-1")


def test_c02_worker_clean_termination_resource_cleanup():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-term-1", team_id="team-proc", role="worker")

            record = controller.spawn_worker(cfg)
            assert record.pid > 0
            assert controller.is_worker_alive("w-term-1") is True

            # Terminate cleanly
            stopped = controller.terminate_worker("w-term-1", timeout=3.0)
            assert stopped is True
            assert controller.is_worker_alive("w-term-1") is False

            record_after = controller.get_worker_record("w-term-1")
            assert record_after is not None
            assert record_after.status == WorkerStatus.ARCHIVED or record_after.status == WorkerStatus.FAILED


def test_c02_reap_stale_worker_process():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-stale-1", team_id="team-proc", role="worker")

            record = controller.spawn_worker(cfg)
            pid = record.pid

            # Forcefully kill the OS process from outside
            import signal
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            time.sleep(0.3)

            # Reaping should detect process is gone
            reaped = controller.reap_dead_workers()
            assert "w-stale-1" in reaped

            record_after = controller.get_worker_record("w-stale-1")
            assert record_after is not None
            assert record_after.status == WorkerStatus.FAILED


def test_c02_per_worker_budget_enforcement():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            # Budget set to 500 tokens
            cfg = WorkerConfig(
                worker_id="w-budget-1",
                team_id="team-proc",
                role="worker",
                budget_tokens=500,
            )

            controller.spawn_worker(cfg)
            try:
                # Task requesting 1000 tokens should be rejected by worker
                result = controller.dispatch_task_to_worker(
                    worker_id="w-budget-1",
                    task_id="task-heavy-tokens",
                    payload={"tokens_requested": 1000},
                    timeout=5.0,
                )
                assert result["status"] == "DENIED" or result["status"] == "ERROR"
                assert "budget" in result.get("reason", "").lower() or "budget" in result.get("error", "").lower()
            finally:
                controller.terminate_worker("w-budget-1")


def test_c02_restart_process_reconciliation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "reconcile.db"

        # Session 1: Spawn worker and record fake dead PID
        with OrcaStore(db_path) as store1:
            controller1 = WorkerProcessController(store=store1)
            cfg = WorkerConfig(worker_id="w-recon-1", team_id="team-recon", role="worker")
            # Save a record with an impossible PID
            controller1.register_persisted_session("w-recon-1", cfg, pid=99999999)

        # Session 2: Crash restart simulation
        with OrcaStore(db_path) as store2:
            controller2 = WorkerProcessController(store=store2)
            # Reconcile on startup
            reconciled = controller2.reconcile_rehydrated_sessions()
            assert "w-recon-1" in reconciled
            assert reconciled["w-recon-1"] == WorkerStatus.FAILED

            record = controller2.get_worker_record("w-recon-1")
            assert record is not None
            assert record.status == WorkerStatus.FAILED, "Dead process must never be claimed alive"


def test_c02_fail_closed_unauthorized_tool_execution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-sec-proc", team_id="team-sec", role="worker")

            controller.spawn_worker(cfg)
            try:
                # Attempt unapproved command execution
                result = controller.dispatch_task_to_worker(
                    worker_id="w-sec-proc",
                    task_id="task-unapproved-cmd",
                    payload={"command": ["rm", "-rf", "/"]},
                    timeout=5.0,
                )
                assert result["status"] == "DENIED"
                assert "default-deny" in result.get("reason", "").lower()
            finally:
                controller.terminate_worker("w-sec-proc")
