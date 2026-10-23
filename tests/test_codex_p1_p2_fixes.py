"""Targeted regression tests for PR #3 Codex P1/P2 review findings (SIM-101..SIM-204)."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from subagentbridge.approval.broker import ApprovalBroker, ApprovalState
from subagentbridge.domain.contracts import Role, Run, Task, TaskState, Message
from subagentbridge.domain.engine import InvalidTransition
from subagentbridge.domain.registry import IdentityRegistry, ReceiptIssuerRegistry
from subagentbridge.execution.isolation.runner import IsolatedExecutionRunner
from subagentbridge.manager import AgentManager
from subagentbridge.messaging.bus import DurableMessageBus
from subagentbridge.planner.budget import BudgetLedger, DurableBudgetLedger, BudgetExceeded
from subagentbridge.server import (
    get_production_system,
    close_production_system,
    submit_goal,
    _runs,
    _tasks,
)
from subagentbridge.storage.audit_ledger import AuditLedger
from subagentbridge.team.coordinator import SupervisedCoordinator

TREE_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
TREE_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
TREE_C = "cccccccccccccccccccccccccccccccccccccccc"
DUMMY_HASH = "1111111111111111111111111111111111111111111111111111111111111111"


class CodexP1P2RegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)

    def tearDown(self):
        close_production_system()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -------------------------------------------------------------------------
    # SIM-108: Approval rejection finality and replay resistance
    # -------------------------------------------------------------------------
    def test_SIM_108_approval_rejection_finality(self):
        broker = ApprovalBroker(broker_secret="test-secret-123")
        action = broker.create_action(session_id="s1", operation="git.push", resource="origin/main")

        # Typecheck: approved must be an explicit boolean
        with self.assertRaises(TypeError):
            broker.resolve_by_human(action.action_id, approved="yes", auth_token="test-secret-123")  # type: ignore

        # Reject action
        rejected = broker.resolve_by_human(
            action.action_id, approved=False, auth_token="test-secret-123", reason="denied by security"
        )
        self.assertEqual(rejected.state, ApprovalState.REJECTED)

        # Attempt to replay/approve the rejected action is rejected
        with self.assertRaises(PermissionError):
            broker.resolve_by_human(action.action_id, approved=True, auth_token="test-secret-123")

    # -------------------------------------------------------------------------
    # SIM-105: Manager receipt authority
    # -------------------------------------------------------------------------
    def test_SIM_105_manager_receipt_authority(self):
        identities = IdentityRegistry()
        exe = identities.register("exe-1", Role.EXECUTOR)
        reg = ReceiptIssuerRegistry(identities)

        manager = AgentManager(receipts=reg)

        # Arbitrary / unregistered receipt fails
        with self.assertRaises(PermissionError) as ctx:
            manager.verify_with_executor_receipt(
                task_id="t1", dispatch_id="d1", tree_sha=TREE_A, receipt_id="forged-receipt"
            )
        self.assertIn("unregistered or forged", str(ctx.exception))

        # Real receipt with non-zero exit code fails
        failed_receipt = reg.issue(exe, task_id="t1", dispatch_id="d1", tree_sha=TREE_A, exit_code=1)
        with self.assertRaises(PermissionError) as ctx:
            manager.verify_with_executor_receipt(
                task_id="t1", dispatch_id="d1", tree_sha=TREE_A, receipt_id=failed_receipt.receipt_id
            )
        self.assertIn("failure", str(ctx.exception))

        # Real receipt with mismatched tree fails
        valid_receipt = reg.issue(exe, task_id="t1", dispatch_id="d1", tree_sha=TREE_A, exit_code=0)
        with self.assertRaises(PermissionError) as ctx:
            manager.verify_with_executor_receipt(
                task_id="t1", dispatch_id="d1", tree_sha=TREE_B, receipt_id=valid_receipt.receipt_id
            )
        self.assertIn("receipt does not match", str(ctx.exception))

        # Real valid receipt succeeds
        ok = manager.verify_with_executor_receipt(
            task_id="t1", dispatch_id="d1", tree_sha=TREE_A, receipt_id=valid_receipt.receipt_id
        )
        self.assertTrue(ok)
        self.assertEqual(manager._verified_trees.get("t1"), TREE_A)

    # -------------------------------------------------------------------------
    # SIM-101: Sticky recovery state
    # -------------------------------------------------------------------------
    def test_SIM_101_sticky_recovery_state(self):
        identities = IdentityRegistry()
        pm = identities.register("pm-1", Role.PM)
        reg = ReceiptIssuerRegistry(identities)
        budget = BudgetLedger(tokens=100, cost_microunits=100, max_workers=2)

        run = Run("r1", "proj1", "p1")
        task = Task("t1", "r1", ("acceptance criterion",), TREE_A, "p1")
        coordinator = SupervisedCoordinator(
            run=run,
            tasks={"t1": task},
            dependencies={"t1": ()},
            identities=identities,
            receipts=reg,
            budget=budget,
            qa_test_hashes={"tests/qa/test_core.py": DUMMY_HASH},
        )

        coordinator.freeze("t1", pm)
        coordinator.begin("t1", pm=pm, idempotency_key="disp-1", token_allowance=10, cost_microunits=5)
        self.assertEqual(coordinator.state("t1"), TaskState.DISPATCHED)

        # Tree update invalidates running dispatch into RECOVERY_REQUIRED
        coordinator.update_tree(TREE_B)
        self.assertEqual(coordinator.state("t1"), TaskState.RECOVERY_REQUIRED)

        # Repeated tree update does NOT clear RECOVERY_REQUIRED
        coordinator.update_tree(TREE_C)
        self.assertEqual(coordinator.state("t1"), TaskState.RECOVERY_REQUIRED)

        # Cannot begin dispatch while in RECOVERY_REQUIRED
        with self.assertRaises(InvalidTransition):
            coordinator.begin("t1", pm=pm, idempotency_key="disp-2", token_allowance=10, cost_microunits=5)

        # Reconciliation restores task to FROZEN
        coordinator.reconcile_recovery("t1", pm=pm, new_tree_sha=TREE_C)
        self.assertEqual(coordinator.state("t1"), TaskState.FROZEN)

    # -------------------------------------------------------------------------
    # SIM-107: Three-fix-round bypass cap
    # -------------------------------------------------------------------------
    def test_SIM_107_fix_round_cap_enforcement(self):
        identities = IdentityRegistry()
        pm = identities.register("pm-1", Role.PM)
        dev = identities.register("dev-1", Role.DEVELOPER)
        qa = identities.register("qa-1", Role.QA)
        reg = ReceiptIssuerRegistry(identities)
        budget = BudgetLedger(tokens=100, cost_microunits=100, max_workers=2)

        run = Run("r1", "proj1", "p1")
        task = Task("t1", "r1", ("criterion 1",), TREE_A, "p1")
        coordinator = SupervisedCoordinator(
            run=run,
            tasks={"t1": task},
            dependencies={"t1": ()},
            identities=identities,
            receipts=reg,
            budget=budget,
            qa_test_hashes={"tests/qa/test_core.py": DUMMY_HASH},
        )

        coordinator.freeze("t1", pm)
        d = coordinator.begin("t1", pm=pm, idempotency_key="disp-1", token_allowance=10, cost_microunits=5)
        coordinator.report_process_succeeded(developer=dev, task_id="t1", dispatch_id=d.dispatch_id, tree_sha=TREE_A)

        # 3 failed reviews with empty evidence (round 0, round 1, round 2)
        dec1 = coordinator.qa_review(
            qa=qa, task_id="t1", evidence=(), covered_criteria=(),
            actual_test_hashes={"tests/qa/test_core.py": DUMMY_HASH},
            actual_tree_sha=TREE_A, clean=True, fix_round=0,
        )
        self.assertEqual(dec1.status, "UNVERIFIED")

        dec2 = coordinator.qa_review(
            qa=qa, task_id="t1", evidence=(), covered_criteria=(),
            actual_test_hashes={"tests/qa/test_core.py": DUMMY_HASH},
            actual_tree_sha=TREE_A, clean=True, fix_round=0,  # Caller passes fix_round=0 to attempt bypass
        )
        self.assertEqual(dec2.status, "UNVERIFIED")

        dec3 = coordinator.qa_review(
            qa=qa, task_id="t1", evidence=(), covered_criteria=(),
            actual_test_hashes={"tests/qa/test_core.py": DUMMY_HASH},
            actual_tree_sha=TREE_A, clean=True, fix_round=0,
        )
        self.assertEqual(dec3.status, "BLOCKED")
        self.assertEqual(coordinator.state("t1"), TaskState.BLOCKED)

    # -------------------------------------------------------------------------
    # SIM-106: Ledger-scope reservations
    # -------------------------------------------------------------------------
    def test_SIM_106_ledger_scope_reservations(self):
        db_path = self.root / "shared_budget.db"
        ledger_a = DurableBudgetLedger(
            db_path=db_path, tokens=1000, cost_microunits=1000, max_workers=1, ledger_id="ledger_a"
        )
        ledger_b = DurableBudgetLedger(
            db_path=db_path, tokens=1000, cost_microunits=1000, max_workers=1, ledger_id="ledger_b"
        )

        # Ledger A reserves 1 worker (reaches max_workers=1 for ledger A)
        ledger_a.reserve(dispatch_id="disp-1", token_allowance=100, cost_microunits=50)
        self.assertEqual(ledger_a.snapshot()["active"], 1)

        # Ledger B is not blocked by Ledger A's reservation
        ledger_b.reserve(dispatch_id="disp-1", token_allowance=200, cost_microunits=100)
        self.assertEqual(ledger_b.snapshot()["active"], 1)

        # Second reservation on Ledger A exceeds max_workers=1
        with self.assertRaises(BudgetExceeded):
            ledger_a.reserve(dispatch_id="disp-2", token_allowance=50, cost_microunits=20)

        # Release disp-1 on Ledger A does not release Ledger B's disp-1
        ledger_a.release("disp-1")
        self.assertEqual(ledger_a.snapshot()["active"], 0)
        self.assertEqual(ledger_b.snapshot()["active"], 1)

        ledger_b.release("disp-1")
        self.assertEqual(ledger_b.snapshot()["active"], 0)

        ledger_a.close()
        ledger_b.close()

    # -------------------------------------------------------------------------
    # SIM-201: Messaging bus ack collision
    # -------------------------------------------------------------------------
    def test_SIM_201_messaging_ack_collision(self):
        ledger = AuditLedger(self.root / "bus_audit.db")
        bus = DurableMessageBus(ledger, stream="test-stream")

        msg1 = Message("a:b", "alice", "c", "t1", "d1", "hello 1")
        msg2 = Message("a", "alice", "b:c", "t1", "d1", "hello 2")

        bus.enqueue(msg1, active_task_id="t1", active_dispatch_id="d1")
        bus.enqueue(msg2, active_task_id="t1", active_dispatch_id="d1")

        # ('a:b', 'c') vs ('a', 'b:c')
        created1 = bus.ack("a:b", recipient_id="c")
        self.assertTrue(created1)

        created2 = bus.ack("a", recipient_id="b:c")
        self.assertTrue(created2)

        ledger.close()

    # -------------------------------------------------------------------------
    # SIM-202: Audit ledger recovery collision
    # -------------------------------------------------------------------------
    def test_SIM_202_recovery_reconciliation_collision(self):
        ledger = AuditLedger(self.root / "recovery_audit.db")
        stream = "recovery-stream"

        ledger.note_unreconciled(stream=stream, session_id="s:1", cause="c1")
        ledger.note_unreconciled(stream=stream, session_id="s", cause="c2")

        # Ambiguous colon pair: ("s:1", "ev") vs ("s", "1:ev")
        ledger.reconcile_closed(stream=stream, session_id="s:1", evidence_key="ev")
        # Second reconciliation must NOT collide or raise ReplayConflict
        ledger.reconcile_closed(stream=stream, session_id="s", evidence_key="1:ev")

        self.assertEqual(ledger.recovery_state(stream=stream, session_id="s:1"), "RECONCILED_CLOSED")
        self.assertEqual(ledger.recovery_state(stream=stream, session_id="s"), "RECONCILED_CLOSED")
        ledger.close()

    # -------------------------------------------------------------------------
    # SIM-203: Server per-workspace production system
    # -------------------------------------------------------------------------
    def test_SIM_203_per_workspace_production_system(self):
        ws1 = self.root / "ws1"
        ws2 = self.root / "ws2"
        ws1.mkdir()
        ws2.mkdir()

        sys1 = get_production_system(ws1)
        sys2 = get_production_system(ws2)

        self.assertIsNot(sys1, sys2)
        self.assertEqual(sys1.workspace_root, ws1.resolve())
        self.assertEqual(sys2.workspace_root, ws2.resolve())

        close_production_system(ws1)
        close_production_system(ws2)

    # -------------------------------------------------------------------------
    # SIM-204: Runner extra_env redaction bypass
    # -------------------------------------------------------------------------
    def test_SIM_204_runner_extra_env_redaction_bypass(self):
        runner = IsolatedExecutionRunner(self.root)
        malicious_env = {
            "OPENAI_API_KEY": "sk-leaked-key",
            "SUBAGENTBRIDGE_BROKER_SECRET": "stolen-secret",
            "SAFE_VAR": "legit-value",
        }

        # Run python snippet inspecting os.environ
        code = (
            "import os, sys\n"
            "assert 'OPENAI_API_KEY' not in os.environ, 'OPENAI_API_KEY leaked!'\n"
            "assert 'SUBAGENTBRIDGE_BROKER_SECRET' not in os.environ, 'BROKER_SECRET leaked!'\n"
            "assert os.environ.get('SAFE_VAR') == 'legit-value', 'SAFE_VAR missing!'\n"
            "print('SUCCESS')\n"
        )
        res = runner.run_isolated(
            ["python", "-c", code],
            extra_env=malicious_env,
            timeout_seconds=10,
        )
        self.assertEqual(res.exit_code, 0)
        self.assertIn("SUCCESS", res.output_text)

    # -------------------------------------------------------------------------
    # SIM-103: Server audit failure handling
    # -------------------------------------------------------------------------
    def test_SIM_103_submit_goal_audit_failure_handling(self):
        ws = self.root / "ws_fail"
        ws.mkdir()

        with patch.object(AuditLedger, "append_once", side_effect=OSError("disk read-only")):
            res = submit_goal("Build features", workspace_path=str(ws))

        self.assertEqual(res["status"], "ERROR")
        self.assertIn("audit ledger write failed", res["error"])

        # No orphan SUBMITTED run or task left in state
        self.assertNotIn(res.get("run_id"), _runs)


if __name__ == "__main__":
    unittest.main()
