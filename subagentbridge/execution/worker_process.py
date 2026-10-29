"""Worker process controller for independent OS process execution.

Spawns, monitors, communicates with, and reaps real independent worker processes.
Guarantees distinct OS process boundaries, IPC messaging with timeout deadlines,
safe process-tree cleanup, process identity verification (create_time check),
heartbeat polling, interrupt preemption, and durable crash reconciliation.
"""
from __future__ import annotations

import json
import os
import queue
from collections import deque
import subprocess
import sys
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from secrets import token_hex
from typing import Any, IO

import psutil

from subagentbridge.domain.team_contracts import (
    AgentRole,
    WorkerStatus,
    WorkerConfig,
    AgentSession,
)
from subagentbridge.execution.worker_isolation import WorkerIsolationPolicy, worker_launch_configuration
from subagentbridge.storage.team_store import TeamStore
from subagentbridge.approval.trusted_authority import (
    TrustedApprovalAuthority,
    get_trusted_authority,
)
from subagentbridge.approval.verified_operator_authority import VerifiedOperatorApprovalAuthority


class TimedStreamReader:
    """Non-blocking queue-based line reader with timeout deadlines."""

    def __init__(self, stream: IO[str]) -> None:
        self.stream = stream
        self.queue: queue.Queue[str | None] = queue.Queue()
        self._pending: deque[str] = deque()
        self._consume_lock = threading.RLock()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        try:
            for line in iter(self.stream.readline, ""):
                self.queue.put(line)
        except (ValueError, OSError):
            pass
        finally:
            self.queue.put(None)

    def readline(self, timeout: float = 5.0) -> str | None:
        with self._consume_lock:
            if self._pending:
                return self._pending.popleft()
            try:
                return self.queue.get(timeout=timeout)
            except queue.Empty:
                return None

    def readline_matching(self, predicate: Any, timeout: float = 5.0) -> str | None:
        """Match a specific IPC control event without discarding task results.

        Reconfiguration ACKs must not be confused with late task responses.
        Keep unmatched events in their original order for ordinary readers.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        unmatched: deque[str] = deque()
        with self._consume_lock:
            try:
                while True:
                    line: str | None
                    if self._pending:
                        line = self._pending.popleft()
                    else:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            return None
                        try:
                            line = self.queue.get(timeout=remaining)
                        except queue.Empty:
                            return None
                    if line is None:
                        return None
                    if predicate(line):
                        return line
                    unmatched.append(line)
            finally:
                self._pending.extendleft(reversed(unmatched))


def _is_task_result(raw: str, task_id: str) -> bool:
    try:
        event = json.loads(raw.strip())
    except (ValueError, TypeError):
        return False
    return isinstance(event, dict) and event.get("type") == "RESULT" and event.get("task_id") == task_id


def _is_reconfigure_ack(raw: str, request_id: str) -> bool:
    try:
        event = json.loads(raw.strip())
    except (ValueError, TypeError):
        return False
    return isinstance(event, dict) and event.get("type") == "RECONFIGURED" and event.get("request_id") == request_id


def _is_control_event(raw: str, event_type: str, worker_id: str) -> bool:
    try:
        event = json.loads(raw.strip())
    except (ValueError, TypeError):
        return False
    return (
        isinstance(event, dict)
        and event.get("type") == event_type
        and event.get("worker_id") == worker_id
    )


def kill_process_tree(pid: int, timeout: float = 2.0) -> None:
    """Recursively terminates and reaps child and grandchild processes safely on Windows and Linux."""
    if pid <= 0:
        return
    try:
        parent = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return

    try:
        children = parent.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        children = []

    procs = children + [parent]
    for p in procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    gone, alive = psutil.wait_procs(procs, timeout=timeout)
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def is_process_identically_alive(pid: int, expected_create_time: float | None = None) -> bool:
    """Checks PID existence AND creation timestamp to protect against OS PID reuse."""
    if pid <= 0:
        return False
    try:
        p = psutil.Process(pid)
        if not p.is_running():
            return False
        if p.status() == psutil.STATUS_ZOMBIE:
            return False
        if expected_create_time is not None:
            if abs(p.create_time() - expected_create_time) > 1.0:
                return False  # PID was recycled by another process
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


@dataclass
class WorkerProcessRecord:
    worker_id: str
    team_id: str
    pid: int
    status: WorkerStatus
    started_at: float
    last_heartbeat: float
    create_time: float | None = None
    tokens_consumed: int = 0
    worktree_path: str | None = None
    exit_code: int | None = None
    session_secret: str = ""
    isolation_mode: str = "inherited"


class WorkerProcessController:
    """Manages real independent worker child processes and durable session tracking."""

    def __init__(
        self,
        store: TeamStore,
        approval_authority: TrustedApprovalAuthority | VerifiedOperatorApprovalAuthority | None = None,
        isolation_policy: WorkerIsolationPolicy | None = None,
    ) -> None:
        self.isolation_policy = isolation_policy or WorkerIsolationPolicy()
        self.store = store
        self.approval_authority = approval_authority or get_trusted_authority()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._readers: dict[str, TimedStreamReader] = {}
        self._records: dict[str, WorkerProcessRecord] = {}
        self._job_handles: dict[str, Any] = {}
        # Async dispatch is considered outstanding until externally reconciled.
        # Never allow a live harness switch to race an unconsumed task result.
        self._busy_workers: set[str] = set()

    def spawn_worker(
        self,
        config: WorkerConfig,
        worktree_path: str | None = None,
        branch_name: str | None = None,
    ) -> WorkerProcessRecord:
        """Spawns a real child OS process running worker_runtime_entrypoint."""
        worktree_path = worktree_path or config.working_dir
        session_secret = token_hex(32)
        cmd = [
            sys.executable,
            "-P",  # Python 3.11+ safe-path: never import shadow modules from worker cwd
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
        if config.tokens_consumed:
            cmd.extend(["--tokens-consumed", str(config.tokens_consumed)])
        if config.harness:
            cmd.extend(["--harness", config.harness])
        if config.model:
            cmd.extend(["--model", config.model])
        if config.provider:
            cmd.extend(["--provider", config.provider])
        if config.effort:
            cmd.extend(["--effort", config.effort])
        if config.fallback_to_native:
            cmd.append("--fallback-to-native")
        if worktree_path:
            cmd.extend(["--worktree-path", worktree_path])

        cwd: str | None
        if self.isolation_policy.mode == "dedicated_user":
            # Never fall back to supervisor cwd when a configured isolated
            # workspace is missing, inaccessible, or not a directory.
            if not worktree_path:
                raise ValueError("Dedicated worker requires an explicit working directory")
            workspace = Path(worktree_path).resolve(strict=True)
            if not workspace.is_dir():
                raise NotADirectoryError(f"Dedicated worker workspace is not a directory: {workspace}")
            cwd = str(workspace)
        else:
            cwd = worktree_path if worktree_path and os.path.isdir(worktree_path) else None

        repo_root = Path(__file__).resolve().parent.parent.parent
        # Child environments are allowlisted even in compatibility mode.
        # Dedicated-user mode fails closed: never fall back to inherited UID.
        env, privilege_kwargs = worker_launch_configuration(
            self.isolation_policy, code_root=repo_root
        )

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=cwd,
            env=env,
            **privilege_kwargs,
        )

        if proc.stdout is None or proc.stdin is None:
            proc.kill()
            raise RuntimeError(f"failed to initialize IPC pipes for worker {config.worker_id}")

        if self.isolation_policy.mode == "windows_job_restricted":
            if sys.platform != "win32":
                kill_process_tree(proc.pid)
                raise RuntimeError("WINDOWS_JOB_RESTRICTED_UNAVAILABLE: mode is only supported on Windows")
            try:
                from .worker_isolation import assign_windows_job_restrictions

                job_handle = assign_windows_job_restrictions(int(proc._handle))  # type: ignore[attr-defined]
                self._job_handles[config.worker_id] = job_handle
            except Exception as exc:
                kill_process_tree(proc.pid)
                raise RuntimeError(f"Failed to apply Windows Job Object restrictions: {exc}") from exc

        reader = TimedStreamReader(proc.stdout)
        self._readers[config.worker_id] = reader

        # Read the INIT handshake event from child stdout with timeout
        init_line = reader.readline(timeout=5.0)
        if not init_line:
            err_msg = ""
            if proc.stderr:
                try:
                    err_msg = proc.stderr.read()
                except Exception:
                    pass
            kill_process_tree(proc.pid)
            raise RuntimeError(
                f"worker {config.worker_id} failed to emit INIT event within deadline: {err_msg.strip()}"
            )

        init_event = json.loads(init_line.strip())
        child_pid = int(init_event.get("pid", proc.pid))
        if child_pid != proc.pid:
            kill_process_tree(proc.pid)
            raise RuntimeError("Worker INIT PID mismatch with child process handle")
        if self.isolation_policy.mode == "dedicated_user":
            assert self.isolation_policy.uid is not None and self.isolation_policy.gid is not None
            child_identity = psutil.Process(proc.pid)
            if (
                child_identity.uids().effective != self.isolation_policy.uid
                or child_identity.gids().effective != self.isolation_policy.gid
            ):
                kill_process_tree(proc.pid)
                raise PermissionError("Dedicated worker OS UID/GID verification failed")

        # Send INIT_ACK with session secret over private stdin pipe (no CLI exposure)
        try:
            proc.stdin.write(json.dumps({"command": "INIT_ACK", "session_secret": session_secret}) + "\n")
            proc.stdin.flush()
        except OSError as exc:
            kill_process_tree(proc.pid)
            raise RuntimeError(f"failed to send INIT_ACK to worker {config.worker_id}: {exc}") from exc

        create_time = float(init_event.get("create_time", 0.0))
        if create_time <= 0:
            try:
                create_time = psutil.Process(child_pid).create_time()
            except Exception:
                create_time = time.time()

        now = time.time()
        record = WorkerProcessRecord(
            worker_id=config.worker_id,
            team_id=config.team_id,
            pid=child_pid,
            status=WorkerStatus.IDLE,
            started_at=now,
            last_heartbeat=now,
            create_time=create_time,
            tokens_consumed=config.tokens_consumed,
            worktree_path=worktree_path,
            session_secret=session_secret,
            isolation_mode=self.isolation_policy.mode,
        )

        self._processes[config.worker_id] = proc
        self._records[config.worker_id] = record

        # Persist session to store with child PID and creation time
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
            process_create_time=create_time,
            tokens_consumed=config.tokens_consumed,
            fallback_to_native=config.fallback_to_native,
        )
        session = AgentSession(
            session_id=config.worker_id,
            role=AgentRole.WORKER,
            team_id=config.team_id,
            status=WorkerStatus.IDLE,
            config=config_with_pid,
            created_at=now,
            updated_at=now,
        )
        self.store.save_session(session)

        return record

    def has_attached_worker_ipc(self, worker_id: str) -> bool:
        """Physical IPC attachment, independent of PAUSED/INTERRUPTED status."""
        proc = self._processes.get(worker_id)
        reader = self._readers.get(worker_id)
        record = self._records.get(worker_id)
        return bool(
            proc is not None and proc.poll() is None and proc.stdin is not None
            and not proc.stdin.closed and reader is not None and record is not None
            and is_process_identically_alive(proc.pid, record.create_time)
        )

    def is_worker_dispatchable(self, worker_id: str) -> bool:
        """An attached worker must also be scheduled to accept new tasks."""
        record = self._records.get(worker_id)
        if record and record.status in (
            WorkerStatus.PAUSED, WorkerStatus.INTERRUPTED,
            WorkerStatus.FAILED, WorkerStatus.ARCHIVED,
        ):
            return False
        return self.has_attached_worker_ipc(worker_id)

    def is_worker_alive(self, worker_id: str) -> bool:
        proc = self._processes.get(worker_id)
        record = self._records.get(worker_id)
        if proc and proc.poll() is None:
            pid = proc.pid
            c_time = record.create_time if record else None
            return is_process_identically_alive(pid, c_time)
        if record:
            return is_process_identically_alive(record.pid, record.create_time)
        session = self.store.load_session(worker_id)
        if session and session.config.pid:
            return is_process_identically_alive(session.config.pid, session.config.process_create_time)
        return False

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
                create_time=session.config.process_create_time,
                tokens_consumed=session.config.tokens_consumed,
                worktree_path=session.config.working_dir,
            )
        return None

    def ping_worker(self, worker_id: str, timeout: float = 3.0) -> dict[str, Any] | None:
        proc = self._processes.get(worker_id)
        reader = self._readers.get(worker_id)
        if not proc or proc.poll() is not None or proc.stdin is None or not reader:
            return None

        try:
            proc.stdin.write(json.dumps({"command": "PING"}) + "\n")
            proc.stdin.flush()
        except OSError:
            return None

        line = reader.readline_matching(
            lambda raw: _is_control_event(raw, "PONG", worker_id),
            timeout=timeout,
        )
        if not line:
            return None

        try:
            event_raw = json.loads(line.strip())
        except json.JSONDecodeError:
            return None

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
        reader = self._readers.get(worker_id)
        record = self._records.get(worker_id)
        if not proc or proc.poll() is not None or proc.stdin is None or not reader or not record:
            return {"status": "ERROR", "error": f"worker {worker_id!r} not alive"}

        if record.status in (WorkerStatus.PAUSED, WorkerStatus.INTERRUPTED) or worker_id in self._busy_workers:
            return {
                "status": "DENIED",
                "task_id": task_id,
                "error": f"WorkerNotDispatchable: worker {worker_id!r} is paused, interrupted or busy",
                "reason": "Worker is paused, interrupted, or has an outstanding task",
                "timestamp": time.time(),
            }

        # Handle authorization binding if command is present
        if "command" in payload:
            cmd_val = payload["command"]
            cmd_list = [str(x) for x in cmd_val] if isinstance(cmd_val, list) else [str(cmd_val)]
            action_id = payload.get("approval_action_id") or ""
            ws = record.worktree_path or ""
            valid, reason, ticket = self.approval_authority.issue_execution_ticket(
                action_id=action_id,
                worker_id=worker_id,
                task_id=task_id,
                command=cmd_list,
                workspace_path=ws,
                session_secret=record.session_secret,
            )
            if not valid or not ticket:
                return {
                    "status": "DENIED",
                    "task_id": task_id,
                    "reason": f"Default-deny: {reason}",
                    "error": f"AuthorizationFailed: {reason}",
                    "timestamp": time.time(),
                }
            payload = dict(payload)
            payload["execution_ticket"] = ticket
            payload["workspace_path"] = ws

        self._busy_workers.add(worker_id)
        try:
            proc.stdin.write(json.dumps({"command": "TASK", "task_id": task_id, "payload": payload}) + "\n")
            proc.stdin.flush()
        except OSError as exc:
            self._busy_workers.discard(worker_id)
            return {"status": "ERROR", "error": f"IPC pipe write failed: {exc}"}

        line = reader.readline_matching(
            lambda raw: _is_task_result(raw, task_id),
            timeout=timeout,
        )
        # On timeout execution may still be running; refuse later operations
        # on this controller until the result is explicitly reconciled.
        if line is not None:
            self._busy_workers.discard(worker_id)
        if line is None:
            return {
                "status": "TIMEOUT",
                "task_id": task_id,
                "error": f"Worker IPC deadline exceeded ({timeout}s)",
                "timestamp": time.time(),
            }

        try:
            res_raw = json.loads(line.strip())
        except json.JSONDecodeError:
            return {"status": "ERROR", "error": "malformed JSON from worker"}

        if not isinstance(res_raw, dict):
            return {"status": "ERROR", "error": "malformed JSON response"}

        res: dict[str, Any] = res_raw

        # Update metered token tracking
        if "tokens_consumed" in res:
            record.tokens_consumed = int(res["tokens_consumed"])
            session = self.store.load_session(worker_id)
            if session:
                session.config = WorkerConfig(
                    worker_id=session.config.worker_id,
                    team_id=session.config.team_id,
                    role=session.config.role,
                    harness=session.config.harness,
                    model=session.config.model,
                    provider=session.config.provider,
                    system_prompt=session.config.system_prompt,
                    working_dir=session.config.working_dir,
                    effort=session.config.effort,
                    budget_tokens=session.config.budget_tokens,
                    pid=session.config.pid,
                    process_create_time=session.config.process_create_time,
                    tokens_consumed=record.tokens_consumed,
                    fallback_to_native=session.config.fallback_to_native,
                )
                session.updated_at = time.time()
                self.store.save_session(session)

        return res

    def send_task_async(self, worker_id: str, task_id: str, payload: dict[str, Any]) -> None:
        proc = self._processes.get(worker_id)
        record = self._records.get(worker_id)
        if not proc or proc.poll() is not None or proc.stdin is None or not record:
            raise RuntimeError(f"worker {worker_id!r} not running")

        if record.status in (WorkerStatus.PAUSED, WorkerStatus.INTERRUPTED) or worker_id in self._busy_workers:
            raise RuntimeError(f"worker {worker_id!r} is paused, interrupted or busy")

        # If command is present, attach ticket
        if "command" in payload:
            cmd_val = payload["command"]
            cmd_list = [str(x) for x in cmd_val] if isinstance(cmd_val, list) else [str(cmd_val)]
            action_id = payload.get("approval_action_id") or ""
            ws = record.worktree_path or ""
            valid, reason, ticket = self.approval_authority.issue_execution_ticket(
                action_id=action_id,
                worker_id=worker_id,
                task_id=task_id,
                command=cmd_list,
                workspace_path=ws,
                session_secret=record.session_secret,
            )
            if not valid or not ticket:
                raise PermissionError(f"Default-deny: {reason}")
            payload = dict(payload)
            payload["execution_ticket"] = ticket
            payload["workspace_path"] = ws

        self._busy_workers.add(worker_id)
        try:
            proc.stdin.write(json.dumps({"command": "TASK", "task_id": task_id, "payload": payload}) + "\n")
            proc.stdin.flush()
        except OSError:
            self._busy_workers.discard(worker_id)
            raise

    def interrupt_worker(self, worker_id: str, task_id: str = "") -> bool:
        proc = self._processes.get(worker_id)
        reader = self._readers.get(worker_id)
        if not proc or proc.poll() is not None or proc.stdin is None:
            return False

        try:
            proc.stdin.write(json.dumps({"command": "INTERRUPT", "task_id": task_id}) + "\n")
            proc.stdin.flush()
        except OSError:
            return False

        # Read only this worker's interrupt ACK; preserve unrelated task
        # results in the IPC queue for explicit reconciliation.
        if reader:
            reader.readline_matching(
                lambda raw: _is_control_event(raw, "INTERRUPTED", worker_id),
                timeout=1.0,
            )

        record = self._records.get(worker_id)
        if record:
            record.status = WorkerStatus.INTERRUPTED

        session = self.store.load_session(worker_id)
        if session:
            session.status = WorkerStatus.INTERRUPTED
            session.updated_at = time.time()
            self.store.save_session(session)

        return True

    def pause_worker(self, worker_id: str) -> bool:
        """Transitions worker to PAUSED status, rejecting subsequent task dispatches."""
        record = self._records.get(worker_id)
        if not record or not self.is_worker_alive(worker_id):
            return False
        if record.status not in (WorkerStatus.IDLE, WorkerStatus.RUNNING):
            return False
        record.status = WorkerStatus.PAUSED
        session = self.store.load_session(worker_id)
        if session:
            session.status = WorkerStatus.PAUSED
            session.updated_at = time.time()
            self.store.save_session(session)
        return True

    def resume_worker(self, worker_id: str) -> bool:
        """Restores a PAUSED worker to IDLE status so task dispatches can resume."""
        record = self._records.get(worker_id)
        if not record or not self.is_worker_alive(worker_id):
            return False
        if record.status not in (WorkerStatus.PAUSED, WorkerStatus.INTERRUPTED):
            return False
        if worker_id in self._busy_workers:
            return False
        record.status = WorkerStatus.IDLE
        session = self.store.load_session(worker_id)
        if session:
            session.status = WorkerStatus.IDLE
            session.updated_at = time.time()
            self.store.save_session(session)
        return True

    def switch_worker_harness(
        self,
        worker_id: str,
        new_harness: str,
        new_model: str | None = None,
        new_provider: str | None = None,
        new_effort: str | None = None,
        fallback_to_native: bool | None = None,
    ) -> bool:
        """Safely reconfigures harness, model, provider, and effort on an IDLE or PAUSED worker."""
        record = self._records.get(worker_id)
        if not record or not self.is_worker_alive(worker_id):
            return False
        if record.status not in (WorkerStatus.IDLE, WorkerStatus.PAUSED):
            raise RuntimeError(f"Cannot switch harness on worker in {record.status.value} state")
        if worker_id in self._busy_workers:
            raise RuntimeError("Cannot switch harness while task response is still outstanding")

        from subagentbridge.runners.harness_adapters import HarnessCapability, get_harness_registry

        registry = get_harness_registry()
        adapter = registry.get(new_harness)
        caps = adapter.get_capabilities()

        # Validate target model/provider/effort
        if new_model and not adapter.validate_model(new_model):
            raise ValueError(f"ModelNotSupported: harness {new_harness!r} does not support {new_model!r}")
        if new_provider and not adapter.validate_provider(new_provider):
            raise ValueError(f"ProviderNotSupported: harness {new_harness!r} does not support {new_provider!r}")
        if new_effort and HarnessCapability.THINKING_BUDGET not in caps.supported_capabilities:
            raise ValueError(f"CapabilityMismatch: harness {new_harness!r} does not support THINKING_BUDGET for effort={new_effort!r}")

        session = self.store.load_session(worker_id)
        if session is None:
            raise RuntimeError("Cannot reconfigure worker without durable session")
        old_cfg = session.config
        effective_fallback = (
            fallback_to_native if fallback_to_native is not None else old_cfg.fallback_to_native
        )

        # Notify running child process over IPC if live
        proc = self._processes.get(worker_id)
        reader = self._readers.get(worker_id)
        if proc and proc.poll() is None and proc.stdin:
            reconfig_request_id = token_hex(16)
            reconfig_msg = {
                "command": "RECONFIGURE",
                "request_id": reconfig_request_id,
                "harness": new_harness,
                "model": new_model or caps.default_model,
                "provider": new_provider or caps.default_provider,
                "effort": new_effort,
                "fallback_to_native": effective_fallback,
            }
            try:
                proc.stdin.write(json.dumps(reconfig_msg) + "\n")
                proc.stdin.flush()
                if reader is None:
                    raise RuntimeError("Worker IPC reply stream is unavailable")
                ack = reader.readline_matching(
                    lambda raw: _is_reconfigure_ack(raw, reconfig_request_id),
                    timeout=2.0,
                )
                if ack is None:
                    raise RuntimeError("No matching RECONFIGURED acknowledgement")
                ack_obj = json.loads(ack.strip())
                if (
                    ack_obj.get("worker_id") != worker_id
                    or ack_obj.get("harness") != new_harness
                    or ack_obj.get("fallback_to_native") is not effective_fallback
                ):
                    raise RuntimeError("Worker reconfiguration ACK payload mismatch")
            except Exception as exc:
                # The child may apply a delayed reconfiguration after timeout.
                # Kill it rather than persisting a configuration it did not ACK.
                self.terminate_worker(worker_id)
                raise RuntimeError(f"Failed to confirm worker RECONFIGURE: {exc}") from exc

        # Update persisted session config in store
        if session:
            updated_cfg = WorkerConfig(
                worker_id=old_cfg.worker_id,
                team_id=old_cfg.team_id,
                role=old_cfg.role,
                harness=new_harness,
                model=new_model or (caps.default_model if new_harness != "native" else "native"),
                provider=new_provider or (caps.default_provider if new_harness != "native" else "local"),
                system_prompt=old_cfg.system_prompt,
                working_dir=old_cfg.working_dir,
                effort=new_effort,
                budget_tokens=old_cfg.budget_tokens,
                pid=old_cfg.pid,
                process_create_time=old_cfg.process_create_time,
                tokens_consumed=old_cfg.tokens_consumed,
                fallback_to_native=effective_fallback,
            )
            session.config = updated_cfg
            session.updated_at = time.time()
            self.store.save_session(session)

        return True

    def terminate_worker(self, worker_id: str, timeout: float = 3.0) -> bool:
        proc = self._processes.get(worker_id)
        record = self._records.get(worker_id)
        pid = proc.pid if proc else (record.pid if record else 0)

        # 1. Try sending graceful STOP command over IPC
        if proc and proc.poll() is None and proc.stdin:
            try:
                proc.stdin.write(json.dumps({"command": "STOP"}) + "\n")
                proc.stdin.flush()
                proc.wait(timeout=min(timeout, 1.0))
            except (subprocess.TimeoutExpired, OSError):
                pass

        # 2. Force recursive process tree cleanup if still alive
        if pid > 0:
            kill_process_tree(pid, timeout=1.0)

        # 3. Clean up pipes
        if proc:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream:
                    try:
                        stream.close()
                    except OSError:
                        pass

        if record:
            ret_code = proc.returncode if proc else 0
            record.exit_code = ret_code
            record.status = WorkerStatus.ARCHIVED if ret_code == 0 else WorkerStatus.FAILED

        session = self.store.load_session(worker_id)
        if session:
            ret_code = proc.returncode if proc else 0
            session.status = WorkerStatus.ARCHIVED if ret_code == 0 else WorkerStatus.FAILED
            session.updated_at = time.time()
            self.store.save_session(session)

        self._processes.pop(worker_id, None)
        self._readers.pop(worker_id, None)
        job_handle = self._job_handles.pop(worker_id, None)
        if job_handle and sys.platform == "win32":
            try:
                import ctypes

                getattr(ctypes, "windll").kernel32.CloseHandle(job_handle)
            except Exception:
                pass
        return True

    def terminate_all(self, timeout: float = 3.0) -> None:
        """Terminates all tracked worker child processes safely."""
        for worker_id in list(self._processes.keys()):
            self.terminate_worker(worker_id, timeout=timeout)

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
                self._readers.pop(worker_id, None)
        return reaped

    def register_persisted_session(
        self,
        worker_id: str,
        config: WorkerConfig,
        pid: int,
        create_time: float | None = None,
    ) -> None:
        now = time.time()
        record = WorkerProcessRecord(
            worker_id=worker_id,
            team_id=config.team_id,
            pid=pid,
            status=WorkerStatus.RUNNING,
            started_at=now,
            last_heartbeat=now,
            create_time=create_time,
            tokens_consumed=config.tokens_consumed,
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
            process_create_time=create_time,
            tokens_consumed=config.tokens_consumed,
            fallback_to_native=config.fallback_to_native,
        )
        session = AgentSession(
            session_id=worker_id,
            role=AgentRole.WORKER,
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
            if not is_process_identically_alive(record.pid, record.create_time):
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
            if session.role == AgentRole.WORKER and session.status in (WorkerStatus.RUNNING, WorkerStatus.IDLE):
                pid = session.config.pid
                c_time = session.config.process_create_time
                if pid is None or not is_process_identically_alive(pid, c_time):
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
                        create_time=c_time,
                        tokens_consumed=session.config.tokens_consumed,
                    )
        return reconciled
