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
import sqlite3
from pathlib import Path
from secrets import compare_digest

import pytest

from subagentbridge.approval.operator_boundary import (
    ApprovalState,
    IndependentOperatorApprovalBoundary,
    OperatorDecision,
    OperatorIdentity,
)
from subagentbridge.storage.audit_ledger import AuditLedger


# TEST-ONLY assertion checker. This is NOT an OIDC/WebAuthn verifier and
# is intentionally never installed or used by production runtime.
def _test_only_verify_operator(identity: OperatorIdentity) -> bool:
    fixture_tokens = {
        ("operator_lead@enterprise.internal", "security_lead", "webauthn"): "verified_webauthn_signature_token_abc123",
        ("sec-lead-1", "security_admin", "webauthn"): "token-abc",
    }
    expected = fixture_tokens.get((identity.operator_id, identity.role, identity.channel))
    return expected is not None and compare_digest(identity.auth_token, expected)


def fixture_boundary(*args, **kwargs) -> IndependentOperatorApprovalBoundary:
    return IndependentOperatorApprovalBoundary(
        *args, operator_verifier=_test_only_verify_operator, **kwargs
    )


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
    boundary = fixture_boundary(
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
    boundary = fixture_boundary()
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
    boundary = fixture_boundary()
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
    boundary = fixture_boundary()
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
    b1 = fixture_boundary(db_path=db_file)

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
    b2 = fixture_boundary(db_path=db_file)
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


def test_audit_ledger_multi_decision_transition_preserves_trail(tmp_path: Path):
    ledger = AuditLedger(tmp_path / "multi_dec_ledger.jsonl")
    boundary = fixture_boundary(
        db_path=tmp_path / "multi_dec.db",
        ledger=ledger,
    )

    operator = OperatorIdentity(
        operator_id="sec-lead-1",
        role="security_admin",
        channel="webauthn",
        auth_token="token-abc",
    )

    req = boundary.create_request(
        session_id="w-q-1",
        task_id="t-q-1",
        command=["python", "script.py"],
        workspace_path=str(tmp_path),
        questions=["Is production credential needed?"],
    )

    # 1. First decision: Answer questions
    r1 = boundary.resolve_by_operator(
        req.action_id,
        decision=OperatorDecision.ANSWER_QUESTIONS,
        operator=operator,
        answers={"Is production credential needed?": "No, mock credentials only"},
    )
    assert r1.state == ApprovalState.QUESTION_PENDING
    assert r1.answers["Is production credential needed?"] == "No, mock credentials only"

    # 2. Subsequent decision: Allow Once (must not raise ReplayConflict on ledger append)
    r2 = boundary.resolve_by_operator(
        req.action_id,
        decision=OperatorDecision.ALLOW_ONCE,
        operator=operator,
        notes="Approved with mock creds",
    )
    assert r2.state == ApprovalState.APPROVED

    # 3. Consume for execution
    ok, status, ticket = boundary.consume_for_execution(
        req.action_id,
        session_id="w-q-1",
        task_id="t-q-1",
        command=["python", "script.py"],
        workspace_path=str(tmp_path),
    )
    assert ok
    assert ticket is not None

    # Verify audit ledger chain integrity
    tail = ledger.verify(stream="operator_approvals")
    assert tail is not None and len(tail) == 64
    events = ledger.read(stream="operator_approvals", reader_stream="operator_approvals")
    event_types = [e.event_type for e in events]
    assert event_types == [
        "REQUEST_CREATED",
        "OPERATOR_DECISION",
        "OPERATOR_DECISION",
        "APPROVAL_CONSUMED",
    ]


def test_unverified_self_declared_admin_cannot_resolve_without_trusted_verifier(tmp_path: Path):
    boundary = IndependentOperatorApprovalBoundary(db_path=tmp_path / "default_deny.db")
    req = boundary.create_request(
        session_id="w-attacker", task_id="t-attacker", command=["echo", "unsafe"],
        workspace_path=str(tmp_path),
    )
    forged = OperatorIdentity(
        operator_id="security-admin", role="security_admin",
        channel="webauthn", auth_token="any-attacker-controlled-token",
    )
    with pytest.raises(PermissionError, match="verifier is not configured"):
        boundary.resolve_by_operator(req.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=forged)
    assert boundary.get_request(req.action_id).state == ApprovalState.BLOCKED
    ok, reason, ticket = boundary.consume_for_execution(
        req.action_id, session_id="w-attacker", task_id="t-attacker",
        command=["echo", "unsafe"], workspace_path=str(tmp_path),
    )
    assert not ok and ticket is None and "not APPROVED" in reason


@pytest.mark.parametrize("decision", [
    OperatorDecision.ALLOW_ONCE, OperatorDecision.DENY, OperatorDecision.ANSWER_QUESTIONS,
])
def test_untrusted_assertion_rejected_for_every_decision(tmp_path: Path, decision: OperatorDecision):
    boundary = fixture_boundary()
    req = boundary.create_request(
        session_id="w", task_id="t", command=["echo", "test"], workspace_path=str(tmp_path),
    )
    forged = OperatorIdentity(
        operator_id="operator_lead@enterprise.internal", role="security_lead",
        channel="webauthn", auth_token="forged-string",
    )
    with pytest.raises(PermissionError, match="not been authenticated"):
        boundary.resolve_by_operator(req.action_id, decision=decision, operator=forged)
    assert boundary.get_request(req.action_id).state == ApprovalState.BLOCKED


def test_verifier_failure_does_not_mutate_approval(tmp_path: Path, operator: OperatorIdentity):
    def unavailable(_: OperatorIdentity) -> bool:
        raise ConnectionError("identity provider unavailable")

    boundary = IndependentOperatorApprovalBoundary(operator_verifier=unavailable)
    req = boundary.create_request(
        session_id="w", task_id="t", command=["echo", "test"], workspace_path=str(tmp_path),
    )
    with pytest.raises(PermissionError, match="verification failed"):
        boundary.resolve_by_operator(req.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=operator)
    assert boundary.get_request(req.action_id).state == ApprovalState.BLOCKED


def test_public_request_objects_cannot_modify_trusted_decision_state(tmp_path: Path):
    boundary = fixture_boundary()
    req = boundary.create_request(
        session_id="w", task_id="t", command=["echo", "test"], workspace_path=str(tmp_path),
    )
    req.state = ApprovalState.APPROVED
    req.operator_verified = True
    from_lookup = boundary.get_request(req.action_id)
    assert from_lookup is not None
    from_lookup.state = ApprovalState.APPROVED
    from_lookup.operator_verified = True
    from_pending = boundary.list_pending()[0]
    from_pending.state = ApprovalState.APPROVED
    from_pending.operator_verified = True
    assert boundary.get_request(req.action_id).state == ApprovalState.BLOCKED
    ok, reason, ticket = boundary.consume_for_execution(
        req.action_id, session_id="w", task_id="t", command=["echo", "test"],
        workspace_path=str(tmp_path),
    )
    assert not ok and ticket is None and "not APPROVED" in reason


def test_pre_upgrade_persisted_approved_action_without_verification_is_denied(tmp_path: Path):
    db = tmp_path / "legacy.db"
    before = fixture_boundary(db_path=db)
    req = before.create_request(
        session_id="w", task_id="t", command=["echo", "test"], workspace_path=str(tmp_path),
    )
    # Simulates an APPROVED row from the previous self-asserted operator code.
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE operator_approvals SET state='APPROVED' WHERE action_id=?", (req.action_id,))
    after = fixture_boundary(db_path=db)
    assert after.rehydrate_from_disk() == 1
    ok, reason, ticket = after.consume_for_execution(
        req.action_id, session_id="w", task_id="t", command=["echo", "test"],
        workspace_path=str(tmp_path),
    )
    assert not ok and ticket is None and "no verified operator provenance" in reason


def test_old_schema_migrates_with_unverified_default(tmp_path: Path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE operator_approvals (
            action_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, task_id TEXT NOT NULL,
            command_json TEXT NOT NULL, workspace_path TEXT NOT NULL,
            nonce TEXT NOT NULL UNIQUE, created_at REAL NOT NULL,
            expires_at REAL NOT NULL, state TEXT NOT NULL, decision TEXT,
            operator_id TEXT, operator_role TEXT, operator_channel TEXT,
            operator_notes TEXT, questions_json TEXT, answers_json TEXT
        )""")
    fixture_boundary(db_path=db)
    with sqlite3.connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(operator_approvals)")}
    assert "operator_verified" in columns
