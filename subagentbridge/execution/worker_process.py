"""Worker process controller for independent OS process execution.

Spawns, monitors, communicates with, and reaps real independent worker processes.
Guarantees distinct OS process boundaries, IPC messaging, heartbeat polling,
interrupt preemption, clean resource cleanup, and durable crash reconciliation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

import psutil

from subagentbridge.domain.orca_contracts import (
    OrcaRole,
    WorkerStatus,
    WorkerConfig,
    OrcaSession,
)
from subagentbridge.storage.orca_store import OrcaStore


@dataclass
class WorkerProcessRecord:
    worker_id: str
    team_id: str
    pid: int
    status: WorkerStatus
    started_at: float
    last_heartbeat: float
    worktree_path: str | None = None
    exit_code: int | None = None


class WorkerProcessController:
    """Manages real independent worker child processes and durable session tracking."""

    def __init__(self, store: OrcaStore) -> None:
        self.store = store
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._records: dict[str, WorkerProcessRecord] = {}

    def spawn_worker(
        self,
        config: WorkerConfig,
        worktree_path: str | None = None,
        branch_name: str | None = None,
    ) -> WorkerProcessRecord:
        """Spawns a real child OS process running worker_runtime_entrypoint."""
        cmd = [
            sys.executable,
            "-m",
            "subagentbridge.execution.worker_runtime_entrypoint",
            "--worker-id",
            config.worker_id,
            "--team-id",
            config.team_id,
            "--role",
            config.role,
        ]
        if config.budget_tokens is not None:
            cmd.extend(["--budget-tokens", str(config.budget_tokens)])

        cwd = worktree_path if worktree_path and os.path.isdir(worktree_path) else None

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=cwd,
        )

        # Read the INIT handshake event from child stdout
        if proc.stdout is None or proc.stdin is None:
            proc.kill()
            raise RuntimeError(f"failed to initialize IPC pipes for worker {config.worker_id}")

        init_line = proc.stdout.readline().strip()
        if not init_line:
            proc.kill()
            raise RuntimeError(f"worker {config.worker_id} failed to emit INIT event")

        init_event = json.loads(init_line)
        child_pid = init_event.get("pid", proc.pid)

        now = time.time()
        record = WorkerProcessRecord(
            worker_id=config.worker_id,
            team_id=config.team_id,
            pid=child_pid,
            status=WorkerStatus.IDLE,
            started_at=now,
            last_heartbeat=now,
            worktree_path=worktree_path,
        )

        self._processes[config.worker_id] = proc
        self._records[config.worker_id] = record

        # Persist session to store with child PID
        config_with_pid = WorkerConfig(
            worker_id=config.worker_id,
            team_id=config.team_id,
            role=config.role,
            harness=config.harness,
            model=config.model,
            provider=config.provider,
            system_prompt=config.system_prompt,
            working_dir=config.working_dir,
            effort=config.effort,
            budget_tokens=config.budget_tokens,
            pid=child_pid,
        )
        session = OrcaSession(
            session_id=config.worker_id,
            orca_role=OrcaRole.WORKER,
            team_id=config.team_id,
            status=WorkerStatus.IDLE,
            config=config_with_pid,
            created_at=now,
            updated_at=now,
        )
        self.store.save_session(session)

        return record

    def is_worker_alive(self, worker_id: str) -> bool:
        proc = self._processes.get(worker_id)
        if not proc:
            record = self._records.get(worker_id)
            if record and psutil.pid_exists(record.pid):
                return True
            session = self.store.load_session(worker_id)
            if session and session.config.pid and psutil.pid_exists(session.config.pid):
                return True
            return False
        return proc.poll() is None

    def get_worker_record(self, worker_id: str) -> WorkerProcessRecord | None:
        rec = self._records.get(worker_id)
        if rec:
            return rec
        session = self.store.load_session(worker_id)
        if session:
            return WorkerProcessRecord(
                worker_id=session.session_id,
                team_id=session.team_id,
                pid=session.config.pid or 0,
                status=session.status,
                started_at=session.created_at,
                last_heartbeat=session.updated_at,
                worktree_path=session.config.working_dir,
            )
        return None

    def ping_worker(self, worker_id: str, timeout: float = 3.0) -> dict[str, Any] | None:
        proc = self._processes.get(worker_id)
        if not proc or proc.poll() is not None or proc.stdin is None or proc.stdout is None:
            return None

        proc.stdin.write(json.dumps({"command": "PING"}) + "\n")
        proc.stdin.flush()

        line = proc.stdout.readline().strip()
        if not line:
            return None

        event_raw = json.loads(line)
        if not isinstance(event_raw, dict):
            return None
        event: dict[str, Any] = event_raw
        if event.get("type") == "PONG":
            record = self._records.get(worker_id)
            if record:
                record.last_heartbeat = time.time()
        return event

    def dispatch_task_to_worker(
        self,
        worker_id: str,
        task_id: str,
        payload: dict[str, Any],
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        proc = self._processes.get(worker_id)
        if not proc or proc.poll() is not None or proc.stdin is None or proc.stdout is None:
            return {"status": "ERROR", "error": f"worker {worker_id!r} not alive"}

        proc.stdin.write(json.dumps({"command": "TASK", "task_id": task_id, "payload": payload}) + "\n")
        proc.stdin.flush()

        line = proc.stdout.readline().strip()
        if not line:
            return {"status": "ERROR", "error": "worker returned empty response"}

        res_raw = json.loads(line)
        if not isinstance(res_raw, dict):
            return {"status": "ERROR", "error": "malformed JSON from worker"}
        res: dict[str, Any] = res_raw
        return res

    def send_task_async(self, worker_id: str, task_id: str, payload: dict[str, Any]) -> None:
        proc = self._processes.get(worker_id)
        if not proc or proc.poll() is not None or proc.stdin is None:
            raise RuntimeError(f"worker {worker_id!r} not running")

        proc.stdin.write(json.dumps({"command": "TASK", "task_id": task_id, "payload": payload}) + "\n")
        proc.stdin.flush()

    def interrupt_worker(self, worker_id: str) -> bool:
        proc = self._processes.get(worker_id)
        if not proc or proc.poll() is not None or proc.stdin is None:
            return False

        proc.stdin.write(json.dumps({"command": "INTERRUPT"}) + "\n")
        proc.stdin.flush()

        record = self._records.get(worker_id)
        if record:
            record.status = WorkerStatus.INTERRUPTED

        session = self.store.load_session(worker_id)
        if session:
            session.status = WorkerStatus.INTERRUPTED
            session.updated_at = time.time()
            self.store.save_session(session)

        return True

    def terminate_worker(self, worker_id: str, timeout: float = 3.0) -> bool:
        proc = self._processes.get(worker_id)
        if not proc:
            return True

        # 1. Try sending graceful STOP command over IPC
        if proc.poll() is None and proc.stdin:
            try:
                proc.stdin.write(json.dumps({"command": "STOP"}) + "\n")
                proc.stdin.flush()
                proc.wait(timeout=min(timeout, 1.0))
            except (subprocess.TimeoutExpired, OSError):
                pass

        # 2. Force termination if still alive
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except (subprocess.TimeoutExpired, OSError):
                proc.kill()
                proc.wait(timeout=1.0)

        # 3. Clean up pipes
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream:
                try:
                    stream.close()
                except OSError:
                    pass

        record = self._records.get(worker_id)
        if record:
            record.exit_code = proc.returncode
            record.status = WorkerStatus.ARCHIVED if proc.returncode == 0 else WorkerStatus.FAILED

        session = self.store.load_session(worker_id)
        if session:
            session.status = WorkerStatus.ARCHIVED if proc.returncode == 0 else WorkerStatus.FAILED
            session.updated_at = time.time()
            self.store.save_session(session)

        self._processes.pop(worker_id, None)
        return True

    def reap_dead_workers(self) -> list[str]:
        reaped: list[str] = []
        for worker_id, proc in list(self._processes.items()):
            code = proc.poll()
            if code is not None:
                record = self._records.get(worker_id)
                if record:
                    record.exit_code = code
                    record.status = WorkerStatus.FAILED
                session = self.store.load_session(worker_id)
                if session:
                    session.status = WorkerStatus.FAILED
                    session.updated_at = time.time()
                    self.store.save_session(session)
                reaped.append(worker_id)
                self._processes.pop(worker_id, None)
        return reaped

    def register_persisted_session(self, worker_id: str, config: WorkerConfig, pid: int) -> None:
        now = time.time()
        record = WorkerProcessRecord(
            worker_id=worker_id,
            team_id=config.team_id,
            pid=pid,
            status=WorkerStatus.RUNNING,
            started_at=now,
            last_heartbeat=now,
        )
        self._records[worker_id] = record

        cfg_with_pid = WorkerConfig(
            worker_id=config.worker_id,
            team_id=config.team_id,
            role=config.role,
            harness=config.harness,
            model=config.model,
            provider=config.provider,
            system_prompt=config.system_prompt,
            working_dir=config.working_dir,
            effort=config.effort,
            budget_tokens=config.budget_tokens,
            pid=pid,
        )
        session = OrcaSession(
            session_id=worker_id,
            orca_role=OrcaRole.WORKER,
            team_id=config.team_id,
            status=WorkerStatus.RUNNING,
            config=cfg_with_pid,
            created_at=now,
            updated_at=now,
        )
        self.store.save_session(session)

    def reconcile_rehydrated_sessions(self) -> dict[str, WorkerStatus]:
        reconciled: dict[str, WorkerStatus] = {}

        # 1. Check in-memory records
        for worker_id, record in list(self._records.items()):
            if not psutil.pid_exists(record.pid):
                record.status = WorkerStatus.FAILED
                reconciled[worker_id] = WorkerStatus.FAILED
                session = self.store.load_session(worker_id)
                if session:
                    session.status = WorkerStatus.FAILED
                    session.updated_at = time.time()
                    self.store.save_session(session)

        # 2. Check persisted sessions from database
        persisted = self.store.list_all_sessions()
        for session in persisted:
            w_id = session.session_id
            if w_id in reconciled:
                continue
            if session.orca_role == OrcaRole.WORKER and session.status == WorkerStatus.RUNNING:
                pid = session.config.pid
                if pid is None or not psutil.pid_exists(pid):
                    session.status = WorkerStatus.FAILED
                    session.updated_at = time.time()
                    self.store.save_session(session)
                    reconciled[w_id] = WorkerStatus.FAILED
                    self._records[w_id] = WorkerProcessRecord(
                        worker_id=w_id,
                        team_id=session.team_id,
                        pid=pid or 0,
                        status=WorkerStatus.FAILED,
                        started_at=session.created_at,
                        last_heartbeat=session.updated_at,
                    )
        return reconciled
