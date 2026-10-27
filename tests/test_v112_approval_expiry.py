"""Approval lifetime & renewal regressions; fixture secret is NOT human identity."""
from __future__ import annotations

import time

import pytest

from subagentbridge.approval.broker import ApprovalBroker, ApprovalState
from subagentbridge.approval.trusted_authority import TrustedApprovalAuthority


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
