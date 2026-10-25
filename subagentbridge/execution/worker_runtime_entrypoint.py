"""Worker runtime entrypoint for independent OS process execution.

Runs as a separate Python child process spawned by WorkerProcessController.
Communicates strictly via JSON-lines over stdin/stdout IPC.
Enforces default-deny tool execution and budget checks inside its own process boundary.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any


def send_event(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="SubagentBridge Worker Process Entrypoint")
    parser.add_argument("--worker-id", required=True, help="Unique worker session ID")
    parser.add_argument("--team-id", required=True, help="Team ID")
    parser.add_argument("--role", default="worker", help="Worker role")
    parser.add_argument("--budget-tokens", type=int, default=None, help="Token budget ceiling")
    args = parser.parse_args()

    worker_id: str = args.worker_id
    team_id: str = args.team_id
    role: str = args.role
    budget_tokens: int | None = args.budget_tokens

    # 1. Send INIT event with real OS PID
    send_event({
        "type": "INIT",
        "worker_id": worker_id,
        "team_id": team_id,
        "role": role,
        "pid": os.getpid(),
        "timestamp": time.time(),
    })

    # 2. Main IPC event loop
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            send_event({"type": "ERROR", "error": f"Invalid JSON: {exc}"})
            continue

        cmd = msg.get("command")

        if cmd == "PING":
            send_event({
                "type": "PONG",
                "worker_id": worker_id,
                "pid": os.getpid(),
                "timestamp": time.time(),
            })

        elif cmd == "TASK":
            task_id = msg.get("task_id", "unknown")
            payload = msg.get("payload", {})

            # Budget check
            requested_tokens = payload.get("tokens_requested", 0)
            if budget_tokens is not None and requested_tokens > budget_tokens:
                send_event({
                    "type": "RESULT",
                    "task_id": task_id,
                    "status": "DENIED",
                    "error": f"BudgetExceeded: requested {requested_tokens} tokens exceeds budget {budget_tokens}",
                    "timestamp": time.time(),
                })
                continue

            # Command execution authorization gate (fail-closed default-deny)
            if "command" in payload:
                approved = payload.get("approved", False)
                approver = payload.get("approver")
                if not approved or not approver:
                    send_event({
                        "type": "RESULT",
                        "task_id": task_id,
                        "status": "DENIED",
                        "reason": "Default-deny: unapproved command execution blocked by policy",
                        "timestamp": time.time(),
                    })
                    continue

            # Task execution simulation / completion
            instruction = payload.get("instruction", "execute")
            duration = payload.get("duration", 0)
            if duration > 0:
                time.sleep(min(duration, 0.5))

            send_event({
                "type": "RESULT",
                "task_id": task_id,
                "status": "COMPLETED",
                "summary": f"Worker {worker_id} executed instruction: {instruction}",
                "timestamp": time.time(),
            })

        elif cmd == "INTERRUPT":
            task_id = msg.get("task_id", "")
            send_event({
                "type": "INTERRUPTED",
                "worker_id": worker_id,
                "task_id": task_id,
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
