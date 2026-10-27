"""Approval lifetime & renewal regressions; fixture secret is NOT human identity."""
from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from subagentbridge.approval.broker import ApprovalBroker, ApprovalState
from subagentbridge.approval.trusted_authority import TrustedApprovalAuthority, verify_ticket_binding


def test_broker_rejects_expired_pending_action(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 10000.0
    monkeypatch.setattr("subagentbridge.approval.broker.time.time", lambda: now)
    broker = ApprovalBroker(approval_ttl_seconds=15.0)
    action = broker.create_action(session_id="worker", operation="execute_command", resource="resource")
    assert action.expires_at == now + 15.0
    monkeypatch.setattr("subagentbridge.approval.broker.time.time", lambda: now + 16.0)
    assert broker.get_action(action.action_id).state == ApprovalState.EXPIRED
    assert broker.list_blocked() == []
    with pytest.raises(PermissionError, match="EXPIRED"):
        broker.resolve_by_human(action.action_id, approved=True, auth_token=broker._secret)


def test_broker_rejects_expired_approved_action(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 10000.0
    monkeypatch.setattr("subagentbridge.approval.broker.time.time", lambda: now)
    broker = ApprovalBroker(approval_ttl_seconds=10.0)
    action = broker.create_action(session_id="worker", operation="execute_command", resource="resource")
    broker.resolve_by_human(action.action_id, approved=True, auth_token=broker._secret)
    monkeypatch.setattr("subagentbridge.approval.broker.time.time", lambda: now + 11.0)
    assert broker.get_action(action.action_id).state == ApprovalState.EXPIRED
    authority = TrustedApprovalAuthority(broker)
    accepted, reason = authority.verify_and_consume(
        action.action_id, "worker", "task", ["echo", "hi"], "/tmp",
    )
    assert not accepted
    assert "EXPIRED" in reason


def test_approval_token_mismatch_rejected_and_ttl_validated() -> None:
    with pytest.raises(ValueError):
        ApprovalBroker(approval_ttl_seconds=0)
    with pytest.raises(ValueError):
        ApprovalBroker(approval_ttl_seconds=86401)
    broker = ApprovalBroker()
    action = broker.create_action(session_id="worker", operation="execute_command", resource="resource")
    with pytest.raises(PermissionError, match="unauthorized"):
        broker.resolve_by_human(action.action_id, approved=True, auth_token="incorrect")
    assert broker.get_action(action.action_id).state == ApprovalState.BLOCKED


def test_expired_action_cannot_become_valid_again(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 10000.0
    monkeypatch.setattr("subagentbridge.approval.broker.time.time", lambda: now)
    broker = ApprovalBroker(approval_ttl_seconds=1.0)
    action = broker.create_action(session_id="worker", operation="execute_command", resource="resource")
    monkeypatch.setattr("subagentbridge.approval.broker.time.time", lambda: now + 2.0)
    assert broker.get_action(action.action_id).state == ApprovalState.EXPIRED
    monkeypatch.setattr("subagentbridge.approval.broker.time.time", lambda: now)
    assert broker.get_action(action.action_id).state == ApprovalState.EXPIRED


@pytest.mark.parametrize("ttl", [0, -1, 61, float("inf"), float("nan"), "long", 10**1000])
def test_invalid_ticket_ttl_does_not_consume_human_approval(ttl) -> None:
    broker = ApprovalBroker()
    authority = TrustedApprovalAuthority(broker)
    command = ["echo", "safe"]
    action = authority.request_command_approval("worker", "task", command, "workspace")
    authority.approve_by_human(action.action_id, auth_token=broker._secret)
    approved, reason, ticket = authority.issue_execution_ticket(
        action.action_id, "worker", "task", command, "workspace", "session", ttl_seconds=ttl,
    )
    assert not approved and ticket is None and "TTL" in reason
    assert not authority.is_action_consumed(action.action_id)
    approved, _, ticket = authority.issue_execution_ticket(
        action.action_id, "worker", "task", command, "workspace", "session",
    )
    assert approved and ticket is not None


@pytest.mark.parametrize("expiry", ["future", None, float("nan"), float("inf"), -1, 10**1000, True])
def test_malformed_ticket_expiry_rejected_without_exception(expiry) -> None:
    ticket = {
        "action_id": "action",
        "worker_id": "worker",
        "task_id": "task",
        "resource": "resource",
        "expiry": expiry,
        "signature": "bad",
    }
    approved, reason = verify_ticket_binding(
        ticket, "session", "worker", "task", ["echo"], "workspace",
    )
    assert not approved and "DENIED" in reason


def test_non_ascii_signature_does_not_crash_ticket_validation() -> None:
    ticket = {
        "action_id": "action",
        "worker_id": "worker",
        "task_id": "task",
        "resource": "resource",
        "expiry": time.time() + 30,
        "signature": "é" * 64,
    }
    approved, reason = verify_ticket_binding(
        ticket, "session", "worker", "task", ["echo"], "workspace",
    )
    assert not approved and "signature malformed" in reason


def test_signed_far_future_ticket_denied_even_with_valid_hmac() -> None:
    worker, task, secret, command, workspace = "worker", "task", "session", ["echo"], "workspace"
    from subagentbridge.approval.trusted_authority import compute_action_resource

    action_id = "action"
    resource = compute_action_resource(command, workspace, task)
    expiry = time.time() + 3600
    payload = f"{action_id}:{worker}:{task}:{resource}:{expiry:.3f}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    ticket = {
        "action_id": action_id, "worker_id": worker, "task_id": task,
        "resource": resource, "expiry": expiry, "signature": signature,
    }
    approved, reason = verify_ticket_binding(ticket, secret, worker, task, command, workspace)
    assert not approved and "maximum TTL" in reason
