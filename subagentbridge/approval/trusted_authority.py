"""subagentbridge/approval/trusted_authority.py — Trusted human approval gate for worker commands.

Binds approval strictly to:
1. Exact worker_id (session_id)
2. Exact task_id
3. Exact command and arguments
4. Exact workspace path
5. Single-use replay protection
6. Authenticated out-of-band human resolution (rejecting spoofed in-payload booleans)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from threading import Lock
from typing import Any

from subagentbridge.approval.broker import ApprovalBroker, ApprovalState, ApprovalAction


def compute_action_resource(command: list[str], workspace_path: str, task_id: str) -> str:
    payload = json.dumps({
        "command": command,
        "workspace_path": workspace_path,
        "task_id": task_id,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class TrustedApprovalAuthority:
    """Manages command approvals with exact context binding and replay prevention."""

    def __init__(self, broker: ApprovalBroker | None = None) -> None:
        self.broker = broker or ApprovalBroker()
        self._consumed_actions: set[str] = set()
        self._lock = Lock()

    def request_command_approval(
        self,
        worker_id: str,
        task_id: str,
        command: list[str],
        workspace_path: str,
    ) -> ApprovalAction:
        resource = compute_action_resource(command, workspace_path, task_id)
        return self.broker.create_action(
            session_id=worker_id,
            operation="execute_command",
            resource=resource,
            metadata={"command": command, "workspace": workspace_path, "task_id": task_id},
        )

    def approve_by_human(
        self,
        action_id: str,
        auth_token: str,
        reason: str = "Approved by human",
    ) -> ApprovalAction:
        return self.broker.resolve_by_human(
            action_id,
            approved=True,
            auth_token=auth_token,
            reason=reason,
        )

    def is_action_consumed(self, action_id: str) -> bool:
        """Return whether an approval has already issued an execution ticket."""
        with self._lock:
            return action_id in self._consumed_actions

    def verify_and_consume(
        self,
        action_id: str,
        worker_id: str,
        task_id: str,
        command: list[str],
        workspace_path: str,
    ) -> tuple[bool, str]:
        """Verifies action validity, exact context binding, and consumes single-use token."""
        with self._lock:
            if not action_id:
                return False, "DENIED: missing approval action_id"

            if action_id in self._consumed_actions:
                return False, "DENIED: approval action already consumed (replay prevented)"

            action = self.broker.get_action(action_id)
            if action is None:
                return False, f"DENIED: unknown approval action {action_id!r}"

            if action.state != ApprovalState.APPROVED:
                return False, f"DENIED: action is in state {action.state.value}, human approval required"

            if action.session_id != worker_id:
                return False, f"DENIED: action session {action.session_id!r} does not match worker {worker_id!r}"

            expected_resource = compute_action_resource(command, workspace_path, task_id)
            if action.resource != expected_resource:
                return False, "DENIED: command, task, or workspace mismatch with approved action"

            self._consumed_actions.add(action_id)
            return True, "APPROVED"

    def issue_execution_ticket(
        self,
        action_id: str,
        worker_id: str,
        task_id: str,
        command: list[str],
        workspace_path: str,
        session_secret: str,
        ttl_seconds: float = 60.0,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Verifies human approval, consumes it, and issues an HMAC execution ticket for IPC."""
        valid, reason = self.verify_and_consume(action_id, worker_id, task_id, command, workspace_path)
        if not valid:
            return False, reason, None

        resource = compute_action_resource(command, workspace_path, task_id)
        expiry = time.time() + ttl_seconds
        payload_str = f"{action_id}:{worker_id}:{task_id}:{resource}:{expiry:.3f}"
        sig = hmac.new(session_secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()

        ticket = {
            "action_id": action_id,
            "worker_id": worker_id,
            "task_id": task_id,
            "resource": resource,
            "expiry": expiry,
            "signature": sig,
        }
        return True, "APPROVED", ticket


def verify_ticket_binding(
    ticket: dict[str, Any],
    session_secret: str,
    worker_id: str,
    task_id: str,
    command: list[str],
    workspace_path: str,
) -> tuple[bool, str]:
    """Independent ticket verification callable by worker child process."""
    if not isinstance(ticket, dict):
        return False, "DENIED: invalid ticket format"

    action_id = ticket.get("action_id", "")
    t_worker = ticket.get("worker_id", "")
    t_task = ticket.get("task_id", "")
    t_resource = ticket.get("resource", "")
    t_expiry = ticket.get("expiry", 0.0)
    sig = ticket.get("signature", "")

    if not action_id:
        return False, "DENIED: ticket missing action_id"
    if t_worker != worker_id:
        return False, f"DENIED: ticket worker {t_worker!r} mismatch with {worker_id!r}"
    if t_task != task_id:
        return False, f"DENIED: ticket task {t_task!r} mismatch with {task_id!r}"
    if time.time() > t_expiry:
        return False, "DENIED: ticket expired"

    expected_resource = compute_action_resource(command, workspace_path, task_id)
    if t_resource != expected_resource:
        return False, "DENIED: ticket resource mismatch with command/task/workspace"

    payload_str = f"{action_id}:{t_worker}:{t_task}:{t_resource}:{t_expiry:.3f}"
    expected_sig = hmac.new(session_secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False, "DENIED: ticket cryptographic signature invalid"

    return True, "VALID"


# Global authority instance for worker process verification
_global_authority: TrustedApprovalAuthority = TrustedApprovalAuthority()


def get_trusted_authority() -> TrustedApprovalAuthority:
    return _global_authority
