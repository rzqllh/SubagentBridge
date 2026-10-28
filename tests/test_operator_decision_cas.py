"""Regression: independent operator supervisors cannot overwrite a decision.

This is a database-concurrency security property; it is NOT a WebAuthn test.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from subagentbridge.approval.operator_boundary import (
    ApprovalState,
    IndependentOperatorApprovalBoundary,
    OperatorDecision,
    OperatorIdentity,
)


def _verified(identity: OperatorIdentity) -> bool:
    return (
        identity.operator_id == "security-operator"
        and identity.role == "security_lead"
        and identity.channel == "test"
        and identity.auth_token == "fixture-verified"
    )


def _operator() -> OperatorIdentity:
    return OperatorIdentity(
        operator_id="security-operator",
        role="security_lead",
        channel="test",
        auth_token="fixture-verified",
    )


def _boundary(db):
    return IndependentOperatorApprovalBoundary(db_path=db, operator_verifier=_verified)


def _request(boundary, tmp_path):
    return boundary.create_request(
        session_id="worker",
        task_id="task",
        command=["python", "-c", "print('test')"],
        workspace_path=str(tmp_path),
    )


def test_stale_blocked_snapshot_cannot_reject_or_reapprove_approved_grant(tmp_path):
    db = tmp_path / "decision.db"
    one = _boundary(db)
    req = _request(one, tmp_path)
    stale = _boundary(db)
    assert stale.rehydrate_from_disk() == 1

    approved = one.resolve_by_operator(
        req.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=_operator(),
    )
    assert approved.state == ApprovalState.APPROVED
    for decision in (OperatorDecision.DENY, OperatorDecision.ALLOW_ONCE):
        with pytest.raises(PermissionError, match="stale operator decision"):
            stale.resolve_by_operator(
                req.action_id, decision=decision, operator=_operator(),
            )

    restarted = _boundary(db)
    assert restarted.rehydrate_from_disk() == 1
    assert restarted.get_request(req.action_id).state == ApprovalState.APPROVED
    allowed, _, _ = one.consume_for_execution(
        req.action_id, session_id="worker", task_id="task",
        command=["python", "-c", "print('test')"],
        workspace_path=str(tmp_path),
    )
    assert allowed
    denied, reason, ticket = stale.consume_for_execution(
        req.action_id, session_id="worker", task_id="task",
        command=["python", "-c", "print('test')"],
        workspace_path=str(tmp_path),
    )
    assert not denied and ticket is None
    assert "durable approval already consumed" in reason


def test_parallel_opposite_decisions_have_one_durable_winner(tmp_path):
    db = tmp_path / "parallel.db"
    one = _boundary(db)
    req = _request(one, tmp_path)
    two = _boundary(db)
    assert two.rehydrate_from_disk() == 1

    barrier = Barrier(2)

    def decide(boundary, decision):
        barrier.wait(timeout=5)
        try:
            return boundary.resolve_by_operator(
                req.action_id, decision=decision, operator=_operator(),
            ).state.value
        except PermissionError as exc:
            assert "stale operator decision" in str(exc)
            return "STALE_REJECTED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        one_result = executor.submit(decide, one, OperatorDecision.ALLOW_ONCE)
        two_result = executor.submit(decide, two, OperatorDecision.DENY)
        results = [one_result.result(timeout=10), two_result.result(timeout=10)]

    assert results.count("STALE_REJECTED") == 1, results
    assert len([state for state in results if state in ("APPROVED", "DENIED")]) == 1
    recovered = _boundary(db)
    assert recovered.rehydrate_from_disk() == 1
    state = recovered.get_request(req.action_id).state.value
    assert state in ("APPROVED", "DENIED")
    assert state in results


def test_parallel_question_answer_updates_cannot_overwrite_each_other(tmp_path):
    db = tmp_path / "answers.db"
    one = _boundary(db)
    req = _request(one, tmp_path)
    two = _boundary(db)
    assert two.rehydrate_from_disk() == 1

    one.resolve_by_operator(
        req.action_id,
        decision=OperatorDecision.ANSWER_QUESTIONS,
        operator=_operator(),
        answers={"environment": "staging"},
    )
    with pytest.raises(PermissionError, match="stale operator decision"):
        two.resolve_by_operator(
            req.action_id,
            decision=OperatorDecision.ANSWER_QUESTIONS,
            operator=_operator(),
            answers={"environment": "production"},
        )
    fresh = _boundary(db)
    assert fresh.rehydrate_from_disk() == 1
    assert fresh.get_request(req.action_id).answers["environment"] == "staging"
    assert fresh.get_request(req.action_id).state == ApprovalState.QUESTION_PENDING
    assert fresh.get_request(req.action_id).operator_verified
