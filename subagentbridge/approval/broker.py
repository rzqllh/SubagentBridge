"""subagentbridge/approval/broker.py — Out-of-band human approval broker (D-03, INV-04, INV-08).

Enforces:
1. Separated human identity: untrusted workers have no access to approval secrets.
2. Operation-bound, one-time approvals: replay protection via unique action fingerprints.
3. Fail-closed: unapproved or timed-out actions remain BLOCKED.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from secrets import token_hex
from threading import Lock
from typing import Any, Mapping


class ApprovalState(str, Enum):
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ApprovalAction:
    action_id: str
    session_id: str
    operation: str
    resource: str
    fingerprint: str
    state: ApprovalState = ApprovalState.BLOCKED
    reason: str = ""


class ApprovalBroker:
    """Out-of-band authenticated human approval broker."""

    def __init__(self, *, broker_secret: str | None = None) -> None:
        self._secret = broker_secret or token_hex(32)
        self._actions: dict[str, ApprovalAction] = {}
        self._consumed_fingerprints: set[str] = set()
        self._lock = Lock()

    def create_action(self, *, session_id: str, operation: str, resource: str, metadata: Mapping[str, Any] | None = None) -> ApprovalAction:
        if not session_id or not operation:
            raise ValueError("session_id and operation required")
        raw = f"{session_id}:{operation}:{resource}:{token_hex(8)}"
        action_id = f"act_{sha256(raw.encode()).hexdigest()[:16]}"
        fp = sha256(f"{action_id}:{operation}:{resource}".encode()).hexdigest()

        action = ApprovalAction(
            action_id=action_id,
            session_id=session_id,
            operation=operation,
            resource=resource,
            fingerprint=fp,
            state=ApprovalState.BLOCKED,
        )
        with self._lock:
            self._actions[action_id] = action
        return action

    def resolve_by_human(self, action_id: str, *, approved: bool, auth_token: str, reason: str = "") -> ApprovalAction:
        """Resolve an action strictly by an authenticated human using broker_secret."""
        if type(approved) is not bool:
            raise TypeError("approved parameter must be an explicit boolean")
        with self._lock:
            if auth_token != self._secret:
                raise PermissionError("unauthorized caller cannot resolve human approval")
            action = self._actions.get(action_id)
            if action is None:
                raise KeyError(f"unknown action {action_id!r}")
            if action.state != ApprovalState.BLOCKED:
                raise PermissionError(f"action {action_id!r} is already resolved to {action.state.value} and cannot be modified")
            if action.fingerprint in self._consumed_fingerprints:
                raise PermissionError("one-time approval already consumed (replay prevented)")

            new_state = ApprovalState.APPROVED if approved else ApprovalState.REJECTED
            updated = ApprovalAction(
                action_id=action.action_id,
                session_id=action.session_id,
                operation=action.operation,
                resource=action.resource,
                fingerprint=action.fingerprint,
                state=new_state,
                reason=reason,
            )
            self._actions[action_id] = updated
            self._consumed_fingerprints.add(action.fingerprint)
            return updated

    def get_action(self, action_id: str) -> ApprovalAction | None:
        with self._lock:
            return self._actions.get(action_id)

    def list_blocked(self) -> list[ApprovalAction]:
        with self._lock:
            return [a for a in self._actions.values() if a.state == ApprovalState.BLOCKED]
