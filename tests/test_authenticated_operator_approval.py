"""Tests for independent authenticated operator approval boundary (Issue #22).

Verifies:
1. Operator identity validation & untrusted role rejection.
2. Context binding (session, task, canonical command, canonical workspace).
3. Triad policy: ALLOW_ONCE, DENY, ANSWER_QUESTIONS.
4. Durable replay prevention: one-time consumption.
5. Durable tamper-evident audit trail via AuditLedger SHA-256 chain.
6. Orchestrator restart recovery: pending approvals survive and replay is prevented.
7. Hostile model/worker cannot self-approve.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from subagentbridge.approval.operator_boundary import (
    ApprovalState,
    IndependentOperatorApprovalBoundary,
    OperatorDecision,
    OperatorIdentity,
)
from subagentbridge.storage.audit_ledger import AuditLedger


@pytest.fixture
def operator() -> OperatorIdentity:
    return OperatorIdentity(
        operator_id="operator_lead@enterprise.internal",
        role="security_lead",
        channel="webauthn",
        auth_token="verified_webauthn_signature_token_abc123",
    )


def test_operator_identity_rejects_untrusted_roles():
    for untrusted_role in ("worker", "agent", "subagent", "untrusted"):
        with pytest.raises(PermissionError, match="not an authorized operator role"):
            OperatorIdentity(
                operator_id="bad_actor",
                role=untrusted_role,
                channel="webauthn",
                auth_token="some_token",
            )


def test_operator_approval_lifecycle_allow_once(tmp_path: Path, operator: OperatorIdentity):
    ledger = AuditLedger(tmp_path / "audit.db")
    boundary = IndependentOperatorApprovalBoundary(
        db_path=tmp_path / "approvals.db",
        ledger=ledger,
    )

    req = boundary.create_request(
        session_id="worker-01",
        task_id="task-build",
        command=["git", "status"],
        workspace_path=str(tmp_path),
    )
    assert req.state == ApprovalState.BLOCKED

    # Operator approves with ALLOW_ONCE
    resolved = boundary.resolve_by_operator(
        req.action_id,
        decision=OperatorDecision.ALLOW_ONCE,
        operator=operator,
        notes="Approved for standard git check",
    )
    assert resolved.state == ApprovalState.APPROVED
    assert resolved.operator_id == operator.operator_id

    # Consume for execution
    ok, reason, ticket = boundary.consume_for_execution(
        req.action_id,
        session_id="worker-01",
        task_id="task-build",
        command=["git", "status"],
        workspace_path=str(tmp_path),
    )
    assert ok and ticket is not None
    assert ticket["action_id"] == req.action_id
    assert ticket["nonce"] == req.nonce

    # Replay attempt fails closed
    ok2, reason2, _ = boundary.consume_for_execution(
        req.action_id,
        session_id="worker-01",
        task_id="task-build",
        command=["git", "status"],
        workspace_path=str(tmp_path),
    )
    assert not ok2
    assert "CONSUMED" in reason2 or "replay prevented" in reason2

    # Verify audit ledger chain
    events = ledger.read(stream="operator_approvals", reader_stream="operator_approvals")
    assert len(events) == 3
    assert events[0].event_type == "REQUEST_CREATED"
    assert events[1].event_type == "OPERATOR_DECISION"
    assert events[2].event_type == "APPROVAL_CONSUMED"


def test_operator_approval_context_mismatch_rejected(tmp_path: Path, operator: OperatorIdentity):
    boundary = IndependentOperatorApprovalBoundary()
    req = boundary.create_request(
        session_id="worker-01",
        task_id="task-build",
        command=["pytest", "-v"],
        workspace_path=str(tmp_path),
    )
    boundary.resolve_by_operator(
        req.action_id,
        decision=OperatorDecision.ALLOW_ONCE,
        operator=operator,
    )

    # Command mismatch
    ok, reason, _ = boundary.consume_for_execution(
        req.action_id,
        session_id="worker-01",
        task_id="task-build",
        command=["rm", "-rf", "/"],
        workspace_path=str(tmp_path),
    )
    assert not ok and "mismatch" in reason

    # Session mismatch
    ok, reason, _ = boundary.consume_for_execution(
        req.action_id,
        session_id="worker-02",
        task_id="task-build",
        command=["pytest", "-v"],
        workspace_path=str(tmp_path),
    )
    assert not ok and "mismatch" in reason


def test_operator_approval_deny_policy(tmp_path: Path, operator: OperatorIdentity):
    boundary = IndependentOperatorApprovalBoundary()
    req = boundary.create_request(
        session_id="worker-01",
        task_id="task-01",
        command=["make", "deploy"],
        workspace_path=str(tmp_path),
    )
    resolved = boundary.resolve_by_operator(
        req.action_id,
        decision=OperatorDecision.DENY,
        operator=operator,
        notes="Deployment not allowed during maintenance window",
    )
    assert resolved.state == ApprovalState.DENIED

    ok, reason, ticket = boundary.consume_for_execution(
        req.action_id,
        session_id="worker-01",
        task_id="task-01",
        command=["make", "deploy"],
        workspace_path=str(tmp_path),
    )
    assert not ok
    assert "not APPROVED" in reason
    assert ticket is None


def test_operator_approval_answer_questions_policy(tmp_path: Path, operator: OperatorIdentity):
    boundary = IndependentOperatorApprovalBoundary()
    req = boundary.create_request(
        session_id="worker-01",
        task_id="task-01",
        command=["python", "script.py"],
        workspace_path=str(tmp_path),
        questions=["Target environment?", "Run migrations?"],
    )
    resolved = boundary.resolve_by_operator(
        req.action_id,
        decision=OperatorDecision.ANSWER_QUESTIONS,
        operator=operator,
        answers={"Target environment?": "staging", "Run migrations?": "false"},
    )
    assert resolved.state == ApprovalState.QUESTION_PENDING
    assert resolved.answers["Target environment?"] == "staging"


def test_orchestrator_restart_recovery_and_replay_prevention(tmp_path: Path, operator: OperatorIdentity):
    db_file = tmp_path / "durable_approvals.db"
    b1 = IndependentOperatorApprovalBoundary(db_path=db_file)

    # 1. Action that gets consumed before restart
    req1 = b1.create_request(
        session_id="w1", task_id="t1", command=["echo", "1"], workspace_path=str(tmp_path),
    )
    b1.resolve_by_operator(req1.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=operator)
    ok1, _, _ = b1.consume_for_execution(
        req1.action_id, session_id="w1", task_id="t1", command=["echo", "1"], workspace_path=str(tmp_path),
    )
    assert ok1

    # 2. Action that is pending during restart
    req2 = b1.create_request(
        session_id="w2", task_id="t2", command=["echo", "2"], workspace_path=str(tmp_path),
    )

    # 3. Action that expires during downtime
    req3 = b1.create_request(
        session_id="w3", task_id="t3", command=["echo", "3"], workspace_path=str(tmp_path), ttl_seconds=0.01,
    )
    time.sleep(0.05)

    # Simulate orchestrator restart: create brand-new boundary instance
    b2 = IndependentOperatorApprovalBoundary(db_path=db_file)
    count = b2.rehydrate_from_disk()
    assert count == 3

    # Replay on previously consumed action must fail
    ok_replay, reason_replay, _ = b2.consume_for_execution(
        req1.action_id, session_id="w1", task_id="t1", command=["echo", "1"], workspace_path=str(tmp_path),
    )
    assert not ok_replay
    assert "replay prevented" in reason_replay or "CONSUMED" in reason_replay

    # Pending action survives and can now be resolved
    b2.resolve_by_operator(req2.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=operator)
    ok2, _, _ = b2.consume_for_execution(
        req2.action_id, session_id="w2", task_id="t2", command=["echo", "2"], workspace_path=str(tmp_path),
    )
    assert ok2

    # Expired action is expired
    r3 = b2.get_request(req3.action_id)
    assert r3 is not None and r3.state == ApprovalState.EXPIRED
