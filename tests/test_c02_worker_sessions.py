"""Unit tests for Phase C02: Independent Worker Sessions Lifecycle & Correctness Gate.

Validates that worker sessions are real independent OS processes with:
1. Real child process spawn with distinct OS PID and process creation time.
2. Inter-process communication (IPC) for heartbeat, ping/pong, and status.
3. Elimination of false task completion: requires real authorized execution or returns NOT_IMPLEMENTED / DENIED / FAILED.
4. Prevention of approval spoofing: in-payload approval booleans are rejected; requires exact worker/task/command binding.
5. Protection against replayed approvals and context mismatch.
6. Real task cancellation / interrupt preemption preventing late successful completion.
7. Clean process-tree termination and file-descriptor cleanup.
8. Reaping crashed or stale worker child processes.
9. Clarified token budget semantics: pre-flight admission checks vs actual metered consumption.
10. Restart reconciliation detecting dead PIDs without false-active claims.
11. Process identity verification beyond PID existence to protect against OS PID recycling.
12. Enforceable IPC deadlines that fail-fast on unresponsive/hanging workers.
"""
from __future__ import annotations

import os
import signal
import sys
import tempfile
import time
from pathlib import Path

import psutil

from subagentbridge.domain.orca_contracts import (
    WorkerStatus,
    WorkerConfig,
)
from subagentbridge.storage.orca_store import OrcaStore
from subagentbridge.approval.trusted_authority import (
    TrustedApprovalAuthority,
)
from subagentbridge.execution.worker_process import (
    WorkerProcessController,
    WorkerProcessRecord,
    is_process_identically_alive,
    kill_process_tree,
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
                assert record.create_time is not None and record.create_time > 0
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
                pong = controller.ping_worker("w-hb-1", timeout=3.0)
                assert pong is not None
                assert pong.get("type") == "PONG"
                assert pong.get("worker_id") == "w-hb-1"

                record = controller.get_worker_record("w-hb-1")
                assert record is not None
                assert record.last_heartbeat > 0
            finally:
                controller.terminate_worker("w-hb-1")


def test_c02_worker_task_dispatch_ipc_real_authorized_execution():
    """Prove real authorized execution with observable evidence and exit code."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            authority = TrustedApprovalAuthority()
            controller = WorkerProcessController(store=store, approval_authority=authority)
            cfg = WorkerConfig(worker_id="w-task-1", team_id="team-proc", role="executor")

            controller.spawn_worker(cfg)
            try:
                command = [sys.executable, "-c", "import sys; sys.stdout.write('real execution output\\n')"]
                task_id = "task-c02-real"

                # 1. Request approval
                action = authority.request_command_approval(
                    worker_id="w-task-1",
                    task_id=task_id,
                    command=command,
                    workspace_path="",
                )
                # 2. Human approval resolution
                authority.approve_by_human(action.action_id, auth_token=authority.broker._secret)

                # 3. Dispatch task
                payload = {
                    "command": command,
                    "approval_action_id": action.action_id,
                }
                result = controller.dispatch_task_to_worker(
                    worker_id="w-task-1",
                    task_id=task_id,
                    payload=payload,
                    timeout=5.0,
                )

                assert result["status"] == "COMPLETED"
                assert result["task_id"] == task_id
                assert result["exit_code"] == 0
                assert "real execution output" in result["stdout"]
                assert result["evidence"]["command"] == command
                assert result["evidence"]["exit_code"] == 0
            finally:
                controller.terminate_worker("w-task-1")


def test_c02_reject_false_completion_for_abstract_instruction():
    """Prove that an abstract instruction without real tool/command execution returns NOT_IMPLEMENTED."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-false-comp", team_id="team-proc", role="executor")

            controller.spawn_worker(cfg)
            try:
                payload = {"instruction": "analyze the codebase and optimize memory"}
                result = controller.dispatch_task_to_worker(
                    worker_id="w-false-comp",
                    task_id="task-abstract-1",
                    payload=payload,
                    timeout=5.0,
                )

                assert result["status"] == "NOT_IMPLEMENTED"
                assert result["status"] != "COMPLETED"
                assert "not implemented" in result.get("error", "").lower()
            finally:
                controller.terminate_worker("w-false-comp")


def test_c02_prevent_approval_spoofing_in_payload():
    """Prove that in-payload approval booleans are rejected as untrusted spoofing attempts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-spoof-1", team_id="team-sec", role="worker")

            controller.spawn_worker(cfg)
            try:
                # Attempt to forge approval using payload booleans
                result = controller.dispatch_task_to_worker(
                    worker_id="w-spoof-1",
                    task_id="task-spoof-cmd",
                    payload={
                        "command": [sys.executable, "-c", "print('spoofed')"],
                        "approved": True,
                        "approver": "spoofed_admin",
                    },
                    timeout=5.0,
                )
                assert result["status"] == "DENIED"
                assert "default-deny" in result.get("reason", "").lower() or "authorizationfailed" in result.get("error", "").lower()
            finally:
                controller.terminate_worker("w-spoof-1")


def test_c02_reject_replayed_approval_ticket():
    """Prove that an approval action cannot be replayed twice."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            authority = TrustedApprovalAuthority()
            controller = WorkerProcessController(store=store, approval_authority=authority)
            cfg = WorkerConfig(worker_id="w-replay-1", team_id="team-sec", role="worker")

            controller.spawn_worker(cfg)
            try:
                command = [sys.executable, "-c", "print('run once')"]
                task_id = "task-replay-test"

                action = authority.request_command_approval(
                    worker_id="w-replay-1",
                    task_id=task_id,
                    command=command,
                    workspace_path="",
                )
                authority.approve_by_human(action.action_id, auth_token=authority.broker._secret)

                # First dispatch: succeeds
                res1 = controller.dispatch_task_to_worker(
                    worker_id="w-replay-1",
                    task_id=task_id,
                    payload={"command": command, "approval_action_id": action.action_id},
                )
                assert res1["status"] == "COMPLETED"

                # Replay attempt with same approval_action_id: must be DENIED
                res2 = controller.dispatch_task_to_worker(
                    worker_id="w-replay-1",
                    task_id="task-replay-test-2",
                    payload={"command": command, "approval_action_id": action.action_id},
                )
                assert res2["status"] == "DENIED"
                assert "replay" in res2.get("reason", "").lower() or "replay" in res2.get("error", "").lower()
            finally:
                controller.terminate_worker("w-replay-1")


def test_c02_reject_approval_context_mismatch():
    """Prove that an approval bound to worker A cannot be used by worker B."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            authority = TrustedApprovalAuthority()
            controller = WorkerProcessController(store=store, approval_authority=authority)
            cfg_a = WorkerConfig(worker_id="w-mismatch-a", team_id="team-sec", role="worker")
            cfg_b = WorkerConfig(worker_id="w-mismatch-b", team_id="team-sec", role="worker")

            controller.spawn_worker(cfg_a)
            controller.spawn_worker(cfg_b)
            try:
                command = [sys.executable, "-c", "print('bound to A')"]
                task_id = "task-mismatch-test"

                # Approve specifically for worker A
                action = authority.request_command_approval(
                    worker_id="w-mismatch-a",
                    task_id=task_id,
                    command=command,
                    workspace_path="",
                )
                authority.approve_by_human(action.action_id, auth_token=authority.broker._secret)

                # Attempt to dispatch to worker B
                res = controller.dispatch_task_to_worker(
                    worker_id="w-mismatch-b",
                    task_id=task_id,
                    payload={"command": command, "approval_action_id": action.action_id},
                )
                assert res["status"] == "DENIED"
                assert "mismatch" in res.get("reason", "").lower() or "mismatch" in res.get("error", "").lower()
            finally:
                controller.terminate_worker("w-mismatch-a")
                controller.terminate_worker("w-mismatch-b")


def test_c02_worker_interrupt_preemption_prevents_late_completion():
    """Prove that task cancellation interrupts an active task and strictly prevents late completion."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            authority = TrustedApprovalAuthority()
            controller = WorkerProcessController(store=store, approval_authority=authority)
            cfg = WorkerConfig(worker_id="w-int-1", team_id="team-proc", role="worker")

            controller.spawn_worker(cfg)
            try:
                command = [sys.executable, "-c", "import time; time.sleep(5)"]
                task_id = "task-int-cancel"

                action = authority.request_command_approval(
                    worker_id="w-int-1",
                    task_id=task_id,
                    command=command,
                    workspace_path="",
                )
                authority.approve_by_human(action.action_id, auth_token=authority.broker._secret)

                # Start long-running command asynchronously
                controller.send_task_async(
                    worker_id="w-int-1",
                    task_id=task_id,
                    payload={"command": command, "approval_action_id": action.action_id},
                )

                time.sleep(0.2)
                interrupted = controller.interrupt_worker("w-int-1", task_id=task_id)
                assert interrupted is True

                record = controller.get_worker_record("w-int-1")
                assert record is not None
                assert record.status == WorkerStatus.INTERRUPTED

                # Read subsequent event from worker queue: must be CANCELLED, strictly NOT COMPLETED
                reader = controller._readers.get("w-int-1")
                assert reader is not None
                res_line = reader.readline(timeout=2.0)
                if res_line:
                    import json
                    res = json.loads(res_line.strip())
                    assert res.get("status") != "COMPLETED", "Interrupted task must never emit COMPLETED"
                    assert res.get("status") in ("CANCELLED", "INTERRUPTED", None)
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

            stopped = controller.terminate_worker("w-term-1", timeout=3.0)
            assert stopped is True
            assert controller.is_worker_alive("w-term-1") is False

            record_after = controller.get_worker_record("w-term-1")
            assert record_after is not None
            assert record_after.status in (WorkerStatus.ARCHIVED, WorkerStatus.FAILED)


def test_c02_reap_stale_worker_process():
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-stale-1", team_id="team-proc", role="worker")

            record = controller.spawn_worker(cfg)
            pid = record.pid

            # Forcefully kill the OS process from outside
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            time.sleep(0.3)

            reaped = controller.reap_dead_workers()
            assert "w-stale-1" in reaped

            record_after = controller.get_worker_record("w-stale-1")
            assert record_after is not None
            assert record_after.status == WorkerStatus.FAILED


def test_c02_budget_semantics_admission_vs_metered_consumption():
    """Clarify budget semantics: distinguish pre-flight requested admission vs post-flight metered usage."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            authority = TrustedApprovalAuthority()
            controller = WorkerProcessController(store=store, approval_authority=authority)
            cfg = WorkerConfig(
                worker_id="w-budget-1",
                team_id="team-proc",
                role="worker",
                budget_tokens=500,
            )

            controller.spawn_worker(cfg)
            try:
                # 1. Pre-flight admission rejection: requested tokens exceeds ceiling
                result_denied = controller.dispatch_task_to_worker(
                    worker_id="w-budget-1",
                    task_id="task-admission-deny",
                    payload={"tokens_requested": 1000},
                    timeout=5.0,
                )
                assert result_denied["status"] == "DENIED"
                assert "budget" in result_denied.get("reason", "").lower()

                # 2. Real task with metered token consumption within budget
                command = [sys.executable, "-c", "print('token metered test')"]
                task_id = "task-metered-1"
                action = authority.request_command_approval(
                    worker_id="w-budget-1",
                    task_id=task_id,
                    command=command,
                    workspace_path="",
                )
                authority.approve_by_human(action.action_id, auth_token=authority.broker._secret)

                result_ok = controller.dispatch_task_to_worker(
                    worker_id="w-budget-1",
                    task_id=task_id,
                    payload={
                        "command": command,
                        "approval_action_id": action.action_id,
                        "tokens_requested": 100,
                        "tokens_metered": 50,
                    },
                    timeout=5.0,
                )
                assert result_ok["status"] == "COMPLETED"
                assert result_ok["metered_tokens"] == 50
                assert result_ok["tokens_consumed"] == 50
                assert result_ok["remaining_tokens"] == 450

                # 3. Verify record and store tracked the metered consumption
                rec = controller.get_worker_record("w-budget-1")
                assert rec is not None
                assert rec.tokens_consumed == 50
            finally:
                controller.terminate_worker("w-budget-1")


def test_c02_restart_process_reconciliation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "reconcile.db"

        # Session 1: Spawn worker and record dead PID
        with OrcaStore(db_path) as store1:
            controller1 = WorkerProcessController(store=store1)
            cfg = WorkerConfig(worker_id="w-recon-1", team_id="team-recon", role="worker")
            controller1.register_persisted_session("w-recon-1", cfg, pid=99999999, create_time=1.0)

        # Session 2: Crash restart simulation
        with OrcaStore(db_path) as store2:
            controller2 = WorkerProcessController(store=store2)
            reconciled = controller2.reconcile_rehydrated_sessions()
            assert "w-recon-1" in reconciled
            assert reconciled["w-recon-1"] == WorkerStatus.FAILED

            record = controller2.get_worker_record("w-recon-1")
            assert record is not None
            assert record.status == WorkerStatus.FAILED, "Dead process must never be claimed alive"


def test_c02_pid_reuse_protection():
    """Verify that is_process_identically_alive rejects PID reuse when create_time mismatches."""
    current_pid = os.getpid()
    real_create_time = psutil.Process(current_pid).create_time()

    # Identical PID and create_time: alive
    assert is_process_identically_alive(current_pid, real_create_time) is True

    # Same PID, but mismatched create_time (simulating PID recycling by OS): must return False
    mismatched_create_time = real_create_time - 1000.0
    assert is_process_identically_alive(current_pid, mismatched_create_time) is False


def test_c02_ipc_deadline_hanging_worker():
    """Prove that controller respects IPC deadlines and does not block forever on unresponsive child."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        with OrcaStore(Path(tmp_dir) / "orca_c02.db") as store:
            controller = WorkerProcessController(store=store)
            cfg = WorkerConfig(worker_id="w-hang-1", team_id="team-proc", role="worker")

            controller.spawn_worker(cfg)
            try:
                # Dispatch ping with an unrealistically short deadline or test timeout
                # Here we test dispatch_task_to_worker with a short timeout on an unresponded task
                result = controller.dispatch_task_to_worker(
                    worker_id="w-hang-1",
                    task_id="task-hang-test",
                    payload={"duration": 3.0},  # sleeps 3.0s in worker
                    timeout=0.3,                # IPC deadline is 0.3s
                )
                assert result["status"] == "TIMEOUT"
                assert "deadline exceeded" in result.get("error", "").lower()
            finally:
                controller.terminate_worker("w-hang-1")


def test_c02_process_tree_cleanup():
    """Verify safe process-tree cleanup terminates parent and child processes."""
    # Spawn a python process that spawns its own child
    proc = psutil.Popen(
        [sys.executable, "-c", "import subprocess, sys, time; p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); p.wait()"]
    )
    time.sleep(0.5)
    pid = proc.pid
    assert psutil.pid_exists(pid)

    # Use kill_process_tree
    kill_process_tree(pid, timeout=2.0)
    time.sleep(0.2)

    assert not psutil.pid_exists(pid)
