"""Security acceptance for explicit operator-bound runtime IPC dispatch.

Test-only identity verifier is not an actual WebAuthn or OIDC implementation.
"""
from __future__ import annotations

import hmac
import sys

import pytest

from subagentbridge.approval.operator_boundary import (
    IndependentOperatorApprovalBoundary, OperatorDecision, OperatorIdentity,
)
from subagentbridge.approval.trusted_authority import verify_ticket_binding
from subagentbridge.approval.verified_operator_authority import VerifiedOperatorApprovalAuthority
from subagentbridge.domain.team_contracts import WorkerConfig
from subagentbridge.execution.worker_process import WorkerProcessController
from subagentbridge.recovery.crash_recovery import resume_task_from_checkpoint
from subagentbridge.team.team_manager import OrcaTeamService
from subagentbridge.storage.team_store import TeamStore


def _fixture_verifier(identity: OperatorIdentity) -> bool:
    return (
        identity.operator_id == "test-operator"
        and identity.role == "security_lead"
        and identity.channel == "webauthn"
        and hmac.compare_digest(identity.auth_token, "fixture-proof")
    )


def _identity() -> OperatorIdentity:
    return OperatorIdentity(
        operator_id="test-operator",
        role="security_lead",
        channel="webauthn",
        auth_token="fixture-proof",
    )


def test_verified_operator_approval_mints_compatible_single_use_ipc_ticket(tmp_path):
    boundary = IndependentOperatorApprovalBoundary(
        db_path=tmp_path / "operator.db", operator_verifier=_fixture_verifier,
    )
    authority = VerifiedOperatorApprovalAuthority(boundary)
    cmd = ["git", "status"]
    ws = str(tmp_path)
    action = authority.request_command_approval("worker-1", "task-1", cmd, ws)
    assert action.state.value == "BLOCKED"
    with pytest.raises(PermissionError, match="legacy broker"):
        authority.approve_by_human(action.action_id, auth_token="any")

    denied, reason, ticket = authority.issue_execution_ticket(
        action.action_id, "worker-1", "task-1", cmd, ws, "s" * 64,
    )
    assert not denied and ticket is None and "not APPROVED" in reason

    boundary.resolve_by_operator(
        action.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=_identity(),
    )
    ok, reason, ticket = authority.issue_execution_ticket(
        action.action_id, "worker-1", "task-1", cmd, ws, "s" * 64,
    )
    assert ok and ticket is not None and reason == "APPROVED_BY_VERIFIED_OPERATOR"
    assert verify_ticket_binding(ticket, "s" * 64, "worker-1", "task-1", cmd, ws)[0]
    assert authority.is_action_consumed(action.action_id)

    again, reason, second = authority.issue_execution_ticket(
        action.action_id, "worker-1", "task-1", cmd, ws, "s" * 64,
    )
    assert not again and second is None and "not APPROVED" in reason


def test_verified_operator_does_not_consume_when_ipc_secret_or_ttl_invalid(tmp_path):
    boundary = IndependentOperatorApprovalBoundary(operator_verifier=_fixture_verifier)
    authority = VerifiedOperatorApprovalAuthority(boundary)
    cmd = ["git", "status"]
    ws = str(tmp_path)
    action = authority.request_command_approval("worker-1", "task-1", cmd, ws)
    boundary.resolve_by_operator(
        action.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=_identity(),
    )
    for ttl in (0, -1, 61, float("nan"), float("inf"), 10**1000, True):
        ok, _, ticket = authority.issue_execution_ticket(
            action.action_id, "worker-1", "task-1", cmd, ws, "s" * 64, ttl_seconds=ttl,
        )
        assert not ok and ticket is None
    ok, _, ticket = authority.issue_execution_ticket(
        action.action_id, "worker-1", "task-1", cmd, ws, "",
    )
    assert not ok and ticket is None and not authority.is_action_consumed(action.action_id)
    ok, _, ticket = authority.issue_execution_ticket(
        action.action_id, "worker-1", "task-1", cmd, ws, "s" * 64,
    )
    assert ok and ticket is not None


def test_unauthenticated_operator_cannot_authorize_runtime_ticket(tmp_path):
    boundary = IndependentOperatorApprovalBoundary(db_path=tmp_path / "operator.db")
    authority = VerifiedOperatorApprovalAuthority(boundary)
    cmd = ["git", "status"]
    ws = str(tmp_path)
    action = authority.request_command_approval("worker-1", "task-1", cmd, ws)
    with pytest.raises(PermissionError, match="verifier is not configured"):
        boundary.resolve_by_operator(
            action.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=_identity(),
        )
    valid, reason, ticket = authority.issue_execution_ticket(
        action.action_id, "worker-1", "task-1", cmd, ws, "s" * 64,
    )
    assert not valid and ticket is None and "not APPROVED" in reason


def test_work_process_dispatch_requires_verified_operator(tmp_path):
    boundary = IndependentOperatorApprovalBoundary(
        db_path=tmp_path / "operator.db", operator_verifier=_fixture_verifier,
    )
    authority = VerifiedOperatorApprovalAuthority(boundary)
    with TeamStore(tmp_path / "state.db") as store:
        controller = WorkerProcessController(store, approval_authority=authority)
        cfg = WorkerConfig(
            worker_id="verified-1", team_id="verified-team",
            role="worker", working_dir=str(tmp_path),
        )
        controller.spawn_worker(cfg)
        try:
            cmd = [sys.executable, "-c", "print('VERIFIED_OPERATOR_DISPATCH')"]
            action = authority.request_command_approval(cfg.worker_id, "run-once", cmd, str(tmp_path))
            denied = controller.dispatch_task_to_worker(cfg.worker_id, "run-once", {
                "command": cmd, "approval_action_id": action.action_id,
            })
            assert denied["status"] == "DENIED", denied
            boundary.resolve_by_operator(
                action.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=_identity(),
            )
            success = controller.dispatch_task_to_worker(cfg.worker_id, "run-once", {
                "command": cmd, "approval_action_id": action.action_id,
            })
            assert success["status"] == "COMPLETED", success
            assert "VERIFIED_OPERATOR_DISPATCH" in success["stdout"]
            denied_replay = controller.dispatch_task_to_worker(cfg.worker_id, "run-once", {
                "command": cmd, "approval_action_id": action.action_id,
            })
            assert denied_replay["status"] == "DENIED", denied_replay
        finally:
            controller.terminate_all()


def test_recovery_uses_verified_authority_and_denies_replay(tmp_path):
    """An existing command grant must survive recovery without broker access."""
    boundary = IndependentOperatorApprovalBoundary(
        db_path=tmp_path / "approval.db", operator_verifier=_fixture_verifier,
    )
    authority = VerifiedOperatorApprovalAuthority(boundary)
    with TeamStore(tmp_path / "state.db") as store:
        service = OrcaTeamService(store=store)
        team = service.create_team(lead_session_id="lead-recovery-verified", title="Verified recovery")
        worker = service.register_worker(WorkerConfig(
            worker_id="worker-recovery-verified", team_id=team.team_id,
            role="worker", harness="native", working_dir=str(tmp_path),
        ))
        item = service.dispatch_task(
            from_session_id=team.lead_session_id,
            to_session_id=worker.session_id,
            task_id="verified-resume",
            payload={"steps": [{
                "name": "step-1",
                "command": [sys.executable, "-c", "print('VERIFIED_RECOVERED')"],
            }]},
        )
        controller = WorkerProcessController(store=store, approval_authority=authority)
        try:
            first = resume_task_from_checkpoint(
                item.dispatch_id, store=store, controller=controller,
                approval_authority=authority,
            )
            assert first["status"] == "AWAITING_APPROVAL", first
            action_id = first["action_id"]
            assert authority.get_action(action_id) is not None
            boundary.resolve_by_operator(
                action_id, decision=OperatorDecision.ALLOW_ONCE, operator=_identity(),
            )
            second = resume_task_from_checkpoint(
                item.dispatch_id, store=store, controller=controller,
                approval_authority=authority,
            )
            assert second["status"] == "COMPLETED", second
            assert authority.is_action_consumed(action_id)
        finally:
            controller.terminate_all()


def test_authority_neutral_lookup_rejects_mismatched_or_consumed_actions(tmp_path):
    boundary = IndependentOperatorApprovalBoundary(operator_verifier=_fixture_verifier)
    authority = VerifiedOperatorApprovalAuthority(boundary)
    cmd = ["echo", "safe"]
    ws = str(tmp_path)
    req = authority.request_command_approval("worker-1", "task-1", cmd, ws)
    action = authority.get_action(req.action_id)
    assert action is not None
    assert authority.is_action_for_context(action, "worker-1", "task-1", cmd, ws)
    assert not authority.is_action_for_context(action, "worker-2", "task-1", cmd, ws)
    assert not authority.is_action_for_context(action, "worker-1", "task-1", ["echo", "bad"], ws)
    boundary.resolve_by_operator(req.action_id, decision=OperatorDecision.ALLOW_ONCE, operator=_identity())
    ok, _, _ = authority.issue_execution_ticket(
        req.action_id, "worker-1", "task-1", cmd, ws, "s" * 64,
    )
    assert ok
    assert authority.get_action(req.action_id).state.value == "CONSUMED"
