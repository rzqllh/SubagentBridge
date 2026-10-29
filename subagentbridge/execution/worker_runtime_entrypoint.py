"""Worker runtime entrypoint for independent OS process execution.

Runs as a separate Python child process spawned by WorkerProcessController.
Communicates strictly via JSON-lines over stdin/stdout IPC.
Enforces default-deny tool execution, verified human approval tickets,
real command execution with observable evidence, interrupt preemption,
and cumulative metered token budget enforcement.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

from subagentbridge.approval.trusted_authority import verify_ticket_binding
from subagentbridge.domain.team_contracts import WorkerConfig
from subagentbridge.runners.harness_adapters import get_harness_registry


def send_event(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="SubagentBridge Worker Process Entrypoint")
    parser.add_argument("--worker-id", required=True, help="Unique worker session ID")
    parser.add_argument("--team-id", required=True, help="Team ID")
    parser.add_argument("--role", default="worker", help="Worker role")
    parser.add_argument("--budget-tokens", type=int, default=None, help="Token budget ceiling")
    parser.add_argument("--tokens-consumed", type=int, default=0, help="Initial tokens consumed")
    parser.add_argument("--session-secret", default=None, help="Deprecated session secret argument")
    parser.add_argument("--worktree-path", default=None, help="Assigned worktree directory path")
    parser.add_argument("--harness", default="native", help="Configured worker harness adapter")
    parser.add_argument("--model", default=None, help="Worker model name")
    parser.add_argument("--provider", default=None, help="Worker provider name")
    parser.add_argument("--effort", default=None, help="Reasoning effort level")
    parser.add_argument("--fallback-to-native", action="store_true", default=False, help="Allow fallback to native")
    args = parser.parse_args()

    worker_id: str = args.worker_id
    team_id: str = args.team_id
    role: str = args.role
    budget_tokens: int | None = args.budget_tokens
    session_secret: str = args.session_secret or os.environ.get("SIMPUL_WORKER_SECRET", "")
    worktree_path: str | None = args.worktree_path
    harness_name: str = args.harness
    model_name: str | None = args.model
    provider_name: str | None = args.provider
    effort_level: str | None = args.effort
    fallback_to_native: bool = bool(args.fallback_to_native)

    # Process identity metadata
    current_pid = os.getpid()
    proc_create_time = time.time()
    if psutil is not None:
        try:
            proc_identity = psutil.Process(current_pid)
            proc_create_time = proc_identity.create_time()
        except Exception:
            pass

    # 1. Send INIT event with real OS PID and process creation timestamp
    send_event({
        "type": "INIT",
        "worker_id": worker_id,
        "team_id": team_id,
        "role": role,
        "pid": current_pid,
        "create_time": proc_create_time,
        "timestamp": time.time(),
    })

    # Read INIT_ACK with session secret securely over private stdin pipe
    if not session_secret:
        try:
            ack_line = sys.stdin.readline()
            if ack_line:
                ack_data = json.loads(ack_line.strip())
                if isinstance(ack_data, dict) and ack_data.get("command") == "INIT_ACK":
                    session_secret = str(ack_data.get("session_secret", ""))
        except Exception:
            pass

    # Internal state tracking
    total_tokens_consumed: int = int(args.tokens_consumed or 0)
    consumed_action_ids: set[str] = set()

    # Threading controls for interrupt preemption
    cancel_event = threading.Event()
    active_subproc: subprocess.Popen[str] | None = None
    subproc_lock = threading.Lock()

    msg_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def stdin_reader_thread() -> None:
        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                    if isinstance(data, dict):
                        # Preempt immediately on interrupt line arrival
                        if data.get("command") == "INTERRUPT":
                            cancel_event.set()
                            with subproc_lock:
                                if active_subproc is not None:
                                    try:
                                        active_subproc.terminate()
                                    except OSError:
                                        pass
                        msg_queue.put(data)
                except json.JSONDecodeError as exc:
                    send_event({"type": "ERROR", "error": f"Invalid JSON: {exc}"})
        except (ValueError, OSError):
            pass
        finally:
            msg_queue.put(None)

    reader = threading.Thread(target=stdin_reader_thread, daemon=True)
    reader.start()

    # 2. Main IPC event loop
    while True:
        try:
            msg = msg_queue.get()
        except Exception:
            break

        if msg is None:
            break

        cmd = msg.get("command")

        if cmd == "PING":
            send_event({
                "type": "PONG",
                "worker_id": worker_id,
                "pid": current_pid,
                "create_time": proc_create_time,
                "timestamp": time.time(),
            })

        elif cmd == "INTERRUPT":
            task_id = msg.get("task_id", "")
            cancel_event.set()
            with subproc_lock:
                if active_subproc is not None:
                    try:
                        active_subproc.terminate()
                    except OSError:
                        pass
            send_event({
                "type": "INTERRUPTED",
                "worker_id": worker_id,
                "task_id": task_id,
                "timestamp": time.time(),
            })

        elif cmd == "RECONFIGURE":
            if "harness" in msg and msg["harness"]:
                harness_name = str(msg["harness"])
            if "model" in msg:
                model_name = msg.get("model")
            if "provider" in msg:
                provider_name = msg.get("provider")
            if "effort" in msg:
                effort_level = msg.get("effort")
            if "fallback_to_native" in msg:
                fallback_to_native = bool(msg.get("fallback_to_native"))
            send_event({
                "type": "RECONFIGURED",
                "worker_id": worker_id,
                "harness": harness_name,
                "model": model_name,
                "provider": provider_name,
                "effort": effort_level,
                "timestamp": time.time(),
            })

        elif cmd == "TASK":
            task_id = msg.get("task_id", "unknown")
            payload = msg.get("payload", {})
            cancel_event.clear()

            # Pre-flight budget admission check
            requested_tokens = payload.get("tokens_requested", 0)
            if budget_tokens is not None and (total_tokens_consumed + requested_tokens) > budget_tokens:
                remaining = max(0, budget_tokens - total_tokens_consumed)
                send_event({
                    "type": "RESULT",
                    "task_id": task_id,
                    "status": "DENIED",
                    "reason": f"BudgetExceeded: requested {requested_tokens} tokens exceeds remaining budget {remaining}",
                    "error": f"BudgetExceeded: requested {requested_tokens} tokens exceeds remaining budget {remaining}",
                    "tokens_consumed": total_tokens_consumed,
                    "remaining_tokens": remaining,
                    "timestamp": time.time(),
                })
                continue

            # Anti-spoofing check: reject untrusted in-payload booleans
            if "approved" in payload or "approver" in payload:
                send_event({
                    "type": "RESULT",
                    "task_id": task_id,
                    "status": "DENIED",
                    "reason": "Default-deny: unapproved command execution blocked by policy",
                    "error": "ApprovalSpoofingDetected: in-payload approval booleans are untrusted and rejected by policy",
                    "timestamp": time.time(),
                })
                continue

            # Check if this task requests command execution
            if "command" in payload:
                command = payload.get("command")
                if isinstance(command, str):
                    command_list = [command]
                elif isinstance(command, list):
                    command_list = [str(x) for x in command]
                else:
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "DENIED",
                        "reason": "Default-deny: invalid command payload",
                        "error": "InvalidCommandFormat",
                        "timestamp": time.time(),
                    })
                    continue

                # Verify human execution ticket
                ticket = payload.get("execution_ticket")
                if not ticket or not session_secret:
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "DENIED",
                        "reason": "Default-deny: unapproved command execution blocked by policy",
                        "error": "AuthorizationFailed: missing execution ticket or session secret",
                        "timestamp": time.time(),
                    })
                    continue

                effective_ws = payload.get("workspace_path") or worktree_path or ""
                valid, reason = verify_ticket_binding(
                    ticket, session_secret, worker_id, task_id, command_list, effective_ws
                )
                if not valid:
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "DENIED",
                        "reason": f"Default-deny: {reason}",
                        "error": f"AuthorizationFailed: {reason}",
                        "timestamp": time.time(),
                    })
                    continue

                # Replay check in worker process
                action_id = ticket.get("action_id", "")
                if action_id in consumed_action_ids:
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "DENIED",
                        "reason": "Default-deny: replayed execution ticket rejected",
                        "error": "TicketReplayPrevented",
                        "timestamp": time.time(),
                    })
                    continue
                consumed_action_ids.add(action_id)

                # Real command execution
                if cancel_event.is_set():
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "CANCELLED",
                        "reason": "Task execution was cancelled before spawn",
                        "timestamp": time.time(),
                    })
                    continue

                exec_cwd = effective_ws if effective_ws and os.path.isdir(effective_ws) else None
                start_time = time.time()
                timeout = float(payload.get("timeout", 30.0))

                try:
                    proc = subprocess.Popen(
                        command_list,
                        cwd=exec_cwd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    with subproc_lock:
                        active_subproc = proc

                    is_timed_out = False
                    while proc.poll() is None:
                        if cancel_event.is_set():
                            try:
                                proc.terminate()
                                proc.wait(timeout=0.5)
                            except (subprocess.TimeoutExpired, OSError):
                                proc.kill()
                            break
                        if (time.time() - start_time) > timeout:
                            is_timed_out = True
                            proc.kill()
                            break
                        time.sleep(0.05)

                    with subproc_lock:
                        active_subproc = None

                    if cancel_event.is_set():
                        send_event({
                            "type": "RESULT",
                            "task_id": task_id,
                            "status": "CANCELLED",
                            "reason": "Task was interrupted by controller",
                            "timestamp": time.time(),
                        })
                        continue

                    stdout, stderr = proc.communicate()
                    duration = time.time() - start_time

                    if is_timed_out:
                        send_event({
                            "type": "RESULT",
                            "task_id": task_id,
                            "status": "FAILED",
                            "error": f"Command timed out after {timeout}s",
                            "duration": duration,
                            "timestamp": time.time(),
                        })
                        continue

                    # Metered token accounting
                    metered_tokens = int(payload.get("tokens_metered", max(1, len(stdout) // 4)))
                    total_tokens_consumed += metered_tokens
                    rem = (budget_tokens - total_tokens_consumed) if budget_tokens is not None else None

                    if proc.returncode == 0:
                        send_event({
                            "type": "RESULT",
                            "task_id": task_id,
                            "status": "COMPLETED",
                            "summary": f"Worker {worker_id} executed command successfully",
                            "stdout": stdout,
                            "stderr": stderr,
                            "exit_code": proc.returncode,
                            "duration": duration,
                            "metered_tokens": metered_tokens,
                            "tokens_consumed": total_tokens_consumed,
                            "remaining_tokens": rem,
                            "evidence": {
                                "command": command_list,
                                "exit_code": 0,
                                "pid": proc.pid,
                                "duration": duration,
                            },
                            "timestamp": time.time(),
                        })
                    else:
                        send_event({
                            "type": "RESULT",
                            "task_id": task_id,
                            "status": "FAILED",
                            "error": f"Command failed with exit code {proc.returncode}",
                            "stdout": stdout,
                            "stderr": stderr,
                            "exit_code": proc.returncode,
                            "duration": duration,
                            "metered_tokens": metered_tokens,
                            "tokens_consumed": total_tokens_consumed,
                            "remaining_tokens": rem,
                            "timestamp": time.time(),
                        })

                except Exception as exc:
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "FAILED",
                        "error": f"SubprocessExecutionError: {exc}",
                        "timestamp": time.time(),
                    })
                continue

            # Non-command task: handle simulation duration or reject false completion
            duration = payload.get("duration", 0)
            if duration > 0:
                was_cancelled = cancel_event.wait(timeout=min(float(duration), 10.0))
                if was_cancelled or cancel_event.is_set():
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "CANCELLED",
                        "reason": "Task was interrupted by controller",
                        "timestamp": time.time(),
                    })
                else:
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "NOT_IMPLEMENTED",
                        "reason": "Simulated sleep cannot report COMPLETED without real tool execution",
                        "error": "Simulated sleep cannot report COMPLETED without real tool execution",
                        "timestamp": time.time(),
                    })
                continue

            # Instruction execution via configured harness adapter
            instruction = payload.get("instruction")
            if instruction:
                try:
                    registry = get_harness_registry()
                    adapter = registry.get(harness_name)
                    task_model = payload.get("model") or model_name
                    task_provider = payload.get("provider") or provider_name
                    task_effort = payload.get("effort") or effort_level
                    task_fallback = payload.get("fallback_to_native", fallback_to_native)
                    cfg_obj = WorkerConfig(
                        worker_id=worker_id,
                        team_id=team_id,
                        role=role,
                        harness=harness_name,
                        model=task_model,
                        provider=task_provider,
                        effort=task_effort,
                        budget_tokens=budget_tokens,
                        tokens_consumed=total_tokens_consumed,
                        fallback_to_native=task_fallback,
                    )
                    eff_ws = payload.get("workspace_path") or worktree_path or ""
                    req_caps = None
                    if "required_capabilities" in payload and payload["required_capabilities"]:
                        from subagentbridge.runners.harness_adapters import HarnessCapability

                        req_caps = {HarnessCapability(c) for c in payload["required_capabilities"]}
                    res = adapter.execute(
                        task_id,
                        str(instruction),
                        cfg_obj,
                        workspace_path=eff_ws,
                        required_capabilities=req_caps,
                    )
                    if "metered_tokens" in res:
                        total_tokens_consumed += int(res["metered_tokens"])
                        res["tokens_consumed"] = total_tokens_consumed
                        if budget_tokens is not None:
                            res["remaining_tokens"] = max(0, budget_tokens - total_tokens_consumed)
                    send_event(res)
                    continue
                except KeyError as exc:
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "UNSUPPORTED_HOST",
                        "error": str(exc),
                        "timestamp": time.time(),
                    })
                    continue

            # Fallback for missing instruction or unsupported payload
            send_event({
                "type": "RESULT",
                "task_id": task_id,
                "status": "NOT_IMPLEMENTED",
                "reason": "Task without command or instruction cannot be executed",
                "error": "Task without command or instruction cannot be executed",
                "timestamp": time.time(),
            })

        elif cmd == "STOP":
            send_event({
                "type": "STOPPED",
                "worker_id": worker_id,
                "timestamp": time.time(),
            })
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
