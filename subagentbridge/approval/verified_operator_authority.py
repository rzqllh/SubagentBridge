"""Explicit opt-in adapter between verified operator decisions and production IPC.

Does NOT implement WebAuthn/OIDC verification itself. The trusted host must
configure IndependentOperatorApprovalBoundary with an external verifier and
must prevent workers/MCP tools from invoking resolve_by_operator.

In contrast to fixture broker approval, only the durable operator boundary
can mint a command ticket in this adapter. Missing verifier fails closed.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import time
from typing import Any

from subagentbridge.approval.operator_boundary import (
    ApprovalState as OperatorApprovalState,
    IndependentOperatorApprovalBoundary,
    OperatorApprovalRequest,
)
from subagentbridge.approval.trusted_authority import compute_action_resource


class VerifiedOperatorApprovalAuthority:
    """Production-dispatch-compatible trusted operator approval adapter.

    Deliberately does not initialize the legacy in-process ApprovalBroker.
    A caller must explicitly supply an operator boundary, with independently
    validated assertions configured by a trusted host.
    """

    def __init__(self, boundary: IndependentOperatorApprovalBoundary) -> None:
        if not isinstance(boundary, IndependentOperatorApprovalBoundary):
            raise TypeError("boundary must be IndependentOperatorApprovalBoundary")
        self.boundary = boundary

    def request_command_approval(
        self,
        worker_id: str,
        task_id: str,
        command: list[str],
        workspace_path: str,
    ) -> OperatorApprovalRequest:
        return self.boundary.create_request(
            session_id=worker_id,
            task_id=task_id,
            command=command,
            workspace_path=workspace_path,
        )

    def approve_by_human(
        self,
        action_id: str,
        auth_token: str,
        reason: str = "Approved by human",
    ) -> OperatorApprovalRequest:
        raise PermissionError(
            "DENIED: legacy broker tokens cannot approve commands; "
            "use a trusted out-of-band operator identity verifier"
        )

    def is_action_consumed(self, action_id: str) -> bool:
        req = self.boundary.get_request(action_id)
        return req is not None and req.state == OperatorApprovalState.CONSUMED

    def verify_and_consume(
        self,
        action_id: str,
        worker_id: str,
        task_id: str,
        command: list[str],
        workspace_path: str,
    ) -> tuple[bool, str]:
        # This legacy API provides no worker IPC secret. Never consume an
        # independently authenticated grant without minting a bound ticket.
        return False, "DENIED: verified operator grants require IPC ticket issuance"

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
        if (
            type(ttl_seconds) not in (float, int)
            or not 0 < ttl_seconds <= 60.0
            or not math.isfinite(ttl_seconds)
        ):
            return False, "DENIED: ticket TTL must be finite in (0, 60]", None
        if not isinstance(session_secret, str) or len(session_secret) < 32:
            return False, "DENIED: missing valid IPC session secret", None

        allowed, reason, operator_receipt = self.boundary.consume_for_execution(
            action_id,
            session_id=worker_id,
            task_id=task_id,
            command=command,
            workspace_path=workspace_path,
            ticket_ttl_seconds=ttl_seconds,
        )
        if not allowed or operator_receipt is None:
            return False, reason, None

        # Issue the existing wire-format ticket that worker_runtime_entrypoint
        # validates with verify_ticket_binding. The model cannot create a
        # ticket by supplying an action_id or self-asserted operator identity.
        digest = compute_action_resource(command, workspace_path, task_id)
        expiry = time.time() + ttl_seconds
        payload = f"{action_id}:{worker_id}:{task_id}:{digest}:{expiry:.3f}"
        signature = hmac.new(
            session_secret.encode(), payload.encode(), hashlib.sha256,
        ).hexdigest()
        ticket: dict[str, Any] = {
            "action_id": action_id,
            "worker_id": worker_id,
            "task_id": task_id,
            "resource": digest,
            "expiry": expiry,
            "signature": signature,
        }
        return True, "APPROVED_BY_VERIFIED_OPERATOR", ticket
