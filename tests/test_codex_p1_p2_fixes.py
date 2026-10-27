"""Targeted regression tests for PR #3 Codex P1/P2 review findings (SIM-101..SIM-204)."""
from __future__ import annotations

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
from subagentbridge.execution.native_runtime import (
    check_clean_checkout,
    SupervisedNativeLifecycle,
    TaskDecomposer,
    resolve_tree_sha,
)
from subagentbridge.manager import AgentManager
from subagentbridge.messaging.bus import DurableMessageBus
from subagentbridge.planner.budget import BudgetLedger, DurableBudgetLedger, BudgetExceeded
from subagentbridge.server import (
    get_production_system,
    close_production_system,
    submit_goal,
    execute_run,
    get_pending_approvals,
    reject_approval,
    approve_command,
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

    # -------------------------------------------------------------------------
    # PR #9 Codex Reviews: Regression Tests
    # -------------------------------------------------------------------------
    def test_PR9_P1_release_dispatch_reservation_on_missing_or_failed_command(self):
        """Thread #4: Missing or failed commands must not leak budget worker reservations."""
        import sys
        ws = self.root / "ws_budget_leak"
        ws.mkdir()
        prod_sys = get_production_system(ws)
        self.assertEqual(prod_sys.budget.snapshot()["active"], 0)

        goal = "Test budget leak protection"
        tree_sha = resolve_tree_sha(ws)
        lifecycle = SupervisedNativeLifecycle(sys=prod_sys, workspace_path=ws)

        # Execute 3 runs with missing commands on max_workers = 3 system
        for i in range(3):
            cur_run_id = f"run_leak_{i}"
            tasks_contracts, dependencies, task_records = TaskDecomposer.decompose_goal(goal, cur_run_id, tree_sha)
            coord, principals = lifecycle.create_coordinator_for_run(
                run_id=cur_run_id,
                tasks=tasks_contracts,
                dependencies=dependencies,
            )
            res = lifecycle.execute_lifecycle(
                run_id=cur_run_id,
                coordinator=coord,
                principals=principals,
                task_records=[dict(r) for r in task_records],
                command_map={},  # Missing command!
            )
            self.assertEqual(res["status"], "FAILED")
            # Reservation must NOT leak
            self.assertEqual(
                prod_sys.budget.snapshot()["active"],
                0,
                f"Budget worker reservation leaked on run {i}",
            )

        # 4th run with valid command should succeed without BudgetExceeded
        run_id_4 = "run_leak_4"
        tasks_contracts_4, dependencies_4, task_records_4 = TaskDecomposer.decompose_goal(goal, run_id_4, tree_sha)
        coord4, principals4 = lifecycle.create_coordinator_for_run(
            run_id=run_id_4,
            tasks=tasks_contracts_4,
            dependencies=dependencies_4,
        )
        _ = lifecycle.execute_lifecycle(
            run_id=run_id_4,
            coordinator=coord4,
            principals=principals4,
            task_records=[dict(r) for r in task_records_4],
            command_map={"default": [sys.executable, "-c", "print('ok')"]},
        )
        self.assertEqual(prod_sys.budget.snapshot()["active"], 0)

    def test_PR9_P1_mcp_command_authorization_and_confinement_gating(self):
        """Thread #7: Model-supplied commands attempting out-of-workspace writes or gated operations are blocked."""
        import sys
        ws = self.root / "ws_mcp_gate"
        ws.mkdir()
        outside_file = self.root / "forbidden_outside.txt"

        sub_res = submit_goal(
            goal="Test command gating",
            workspace_path=str(ws),
            execute=False,
        )
        run_id = sub_res["run_id"]

        # Attempt out-of-workspace write
        exec_res = execute_run(
            run_id=run_id,
            commands={"default": [sys.executable, "-c", f"with open({repr(outside_file.as_posix())}, 'w') as f: f.write('pwn')"]},
        )
        self.assertEqual(exec_res.get("status"), "BLOCKED")
        self.assertIn("requires human approval", exec_res.get("reason", ""))
        self.assertFalse(outside_file.exists(), "File outside workspace was improperly written!")

        # Pending approvals must not be empty
        pending = get_pending_approvals()
        matched = [a for a in pending if a["action_id"] == exec_res.get("action_id")]
        self.assertEqual(len(matched), 1)

        # Rejection should finalize the gate
        rej_res = reject_approval(matched[0]["action_id"], reason="Security rejected out-of-workspace write")
        self.assertEqual(rej_res["status"], "REJECTED")

    def test_PR9_P2_restrict_checkout_exclusions_exact_artifact_paths(self):
        """Thread #5: Cleanliness check must only exclude exact runtime artifact paths, not substrings like restore.db.py."""
        import subprocess
        ws = self.root / "ws_exact_git"
        ws.mkdir()

        # Initialize clean git repo
        subprocess.run(["git", "init"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=str(ws), capture_output=True, check=True)
        (ws / "file.txt").write_text("clean\n")
        subprocess.run(["git", "add", "file.txt"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(ws), capture_output=True, check=True)

        self.assertTrue(check_clean_checkout(ws))

        # Modifying a file whose name contains 'store.db' as substring
        restore_file = ws / "restore.db.py"
        restore_file.write_text("# tracked source\n")
        subprocess.run(["git", "add", "restore.db.py"], cwd=str(ws), capture_output=True, check=True)

        # Must be detected as DIRTY!
        self.assertFalse(check_clean_checkout(ws), "Substring 'store.db' in restore.db.py improperly ignored!")

        # Remove restore.db.py and add exact store.db
        subprocess.run(["git", "rm", "-f", "restore.db.py"], cwd=str(ws), capture_output=True, check=True)
        (ws / "store.db").write_text("sqlite format\n")
        # Exact store.db must be ignored
        self.assertTrue(check_clean_checkout(ws))

    def test_PR9_P2_revalidate_checkout_integrity_post_qa(self):
        """Thread #6: Revalidate cleanliness and tree integrity AFTER QA run finishes."""
        import subprocess
        import sys
        ws = self.root / "ws_qa_dirty"
        ws.mkdir()

        subprocess.run(["git", "init"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=str(ws), capture_output=True, check=True)
        (ws / "tracked.txt").write_text("initial\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(ws), capture_output=True, check=True)

        # Create QA test that writes to tracked.txt
        qa_dir = ws / "tests"
        qa_dir.mkdir()
        dirtying_qa = (
            "import unittest\n"
            "from pathlib import Path\n"
            "class DirtyTest(unittest.TestCase):\n"
            "    def test_write_tracked(self):\n"
            "        p = Path(__file__).resolve().parent.parent / 'tracked.txt'\n"
            "        p.write_text('mutated by qa')\n"
            "        self.assertTrue(True)\n"
        )
        qa_file = qa_dir / "test_dirty.py"
        qa_file.write_text(dirtying_qa)
        subprocess.run(["git", "add", "tests/test_dirty.py"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add qa"], cwd=str(ws), capture_output=True, check=True)

        from hashlib import sha256
        from subagentbridge.composition import build_production_system
        qa_hash = sha256(qa_file.read_bytes()).hexdigest()
        prod_sys = build_production_system(
            workspace_root=ws,
            custom_qa_hashes={"tests/test_dirty.py": qa_hash},
        )

        tree_sha = resolve_tree_sha(ws)
        tasks_contracts, dependencies, task_records = TaskDecomposer.decompose_goal("QA mutates checkout", "run_dirty_qa", tree_sha)
        lifecycle = SupervisedNativeLifecycle(sys=prod_sys, workspace_path=ws)
        coord, principals = lifecycle.create_coordinator_for_run("run_dirty_qa", tasks_contracts, dependencies)

        res = lifecycle.execute_lifecycle(
            run_id="run_dirty_qa",
            coordinator=coord,
            principals=principals,
            task_records=[dict(r) for r in task_records],
            command_map={"default": [sys.executable, "-c", "print('dev pass')"]},
        )
        # Because QA test dirtied tracked.txt, post-QA checkout revalidation must catch it and reject verification
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("dirty checkout", res.get("reason", ""))

    def test_PR9_P2_reject_skipped_qualifying_tests_for_coverage(self):
        """Thread #8: Skipped qualifying QA tests must not grant criteria coverage (Gate E20)."""
        import subprocess
        import sys
        ws = self.root / "ws_qa_skip"
        ws.mkdir()

        subprocess.run(["git", "init"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=str(ws), capture_output=True, check=True)
        (ws / "tracked.txt").write_text("clean\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(ws), capture_output=True, check=True)

        # Create QA test with @unittest.skip
        qa_dir = ws / "tests"
        qa_dir.mkdir()
        skipped_qa = (
            "import unittest\n"
            "class SkippedTest(unittest.TestCase):\n"
            "    @unittest.skip('Intentional skip in qualifying test')\n"
            "    def test_skipped_check(self):\n"
            "        self.assertTrue(True)\n"
        )
        qa_file = qa_dir / "test_skip.py"
        qa_file.write_text(skipped_qa)
        subprocess.run(["git", "add", "tests/test_skip.py"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add skipped qa"], cwd=str(ws), capture_output=True, check=True)

        from hashlib import sha256
        from subagentbridge.composition import build_production_system
        qa_hash = sha256(qa_file.read_bytes()).hexdigest()
        prod_sys = build_production_system(
            workspace_root=ws,
            custom_qa_hashes={"tests/test_skip.py": qa_hash},
        )

        tree_sha = resolve_tree_sha(ws)
        tasks_contracts, dependencies, task_records = TaskDecomposer.decompose_goal("QA skipped test", "run_skipped_qa", tree_sha)
        lifecycle = SupervisedNativeLifecycle(sys=prod_sys, workspace_path=ws)
        coord, principals = lifecycle.create_coordinator_for_run("run_skipped_qa", tasks_contracts, dependencies)

        res = lifecycle.execute_lifecycle(
            run_id="run_skipped_qa",
            coordinator=coord,
            principals=principals,
            task_records=[dict(r) for r in task_records],
            command_map={"default": [sys.executable, "-c", "print('dev pass')"]},
        )
        # QA test was skipped; must NOT receive verification
        self.assertEqual(res["status"], "FAILED")
        self.assertIn("acceptance criteria", res.get("reason", ""))


    def test_PR9_P1_command_authorization_bypass_attempts_and_default_deny(self):
        """Focus 1: Test bypass via dynamic script, subprocess, shell, out-of-bounds, default DENY, and approval token."""
        import sys
        ws = self.root / "ws_p1_bypass"
        ws.mkdir()

        sub_res = submit_goal(
            goal="Test bypass resilience",
            workspace_path=str(ws),
            execute=False,
        )
        run_id = sub_res["run_id"]

        # 1. Dynamic script bypass attempt
        res_dyn = execute_run(
            run_id=run_id,
            commands={"default": [sys.executable, "-c", "eval('__import__(\"os\").system(\"echo pwn\")')"]},
        )
        self.assertEqual(res_dyn["status"], "BLOCKED")
        self.assertIn("same_user_boundary", res_dyn)
        self.assertIn("Gate E18 BLOCKED", res_dyn["same_user_boundary"])

        # 2. Subprocess bypass attempt
        res_sub = execute_run(
            run_id=run_id,
            commands={"default": [sys.executable, "-c", "import subprocess; subprocess.run(['echo', 'pwn'])"]},
        )
        self.assertEqual(res_sub["status"], "BLOCKED")

        # 3. Shell indirection bypass attempt
        res_shell = execute_run(
            run_id=run_id,
            commands={"default": ["bash", "-c", "echo pwn"]},
        )
        self.assertEqual(res_shell["status"], "BLOCKED")

        # 4. Seemingly harmless command (default DENY)
        res_echo = execute_run(
            run_id=run_id,
            commands={"default": ["echo", "harmless hello"]},
        )
        self.assertEqual(res_echo["status"], "BLOCKED")
        self.assertIn("default-deny", res_echo.get("reason", "").lower())
        action_id = res_echo.get("action_id")
        self.assertIsNotNone(action_id)

        # 5. Pending approval does NOT grant authority (re-run still BLOCKED)
        res_pending_recheck = execute_run(
            run_id=run_id,
            commands={"default": ["echo", "harmless hello"]},
        )
        self.assertEqual(res_pending_recheck["status"], "BLOCKED")

        # 6. A model-callable "human" string or supplied token is never proof
        # of independently authenticated human approval.
        app_res = approve_command(action_id, approver="security_officer")
        self.assertEqual(app_res["status"], "BLOCKED")
        self.assertEqual(
            approve_command(action_id, approver="human", auth_token="attacker-chosen")["status"],
            "BLOCKED",
        )

        # 7. No caller can use legacy approval to move past the gate, even once.
        res_still_blocked = execute_run(
            run_id=run_id,
            commands={"default": ["echo", "harmless hello"]},
        )
        self.assertEqual(res_still_blocked["status"], "BLOCKED")
        res_replay = execute_run(
            run_id=run_id,
            commands={"default": ["echo", "harmless hello"]},
        )
        self.assertEqual(res_replay["status"], "BLOCKED")

    def test_PR9_P2_qa_skip_detection_structured_and_collection(self):
        """Focus 2: Test 0 tests collected and stdout spoofing rejection."""
        import subprocess
        import sys
        ws = self.root / "ws_qa_structured"
        ws.mkdir()

        subprocess.run(["git", "init"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=str(ws), capture_output=True, check=True)
        (ws / "tracked.txt").write_text("clean\n")
        subprocess.run(["git", "add", "tracked.txt"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(ws), capture_output=True, check=True)

        # Case A: 0 tests collected (empty suite / helper file without tests)
        qa_dir = ws / "tests"
        qa_dir.mkdir()
        empty_qa = "def helper_function(): pass\n"
        qa_file = qa_dir / "test_empty.py"
        qa_file.write_text(empty_qa)
        subprocess.run(["git", "add", "tests/test_empty.py"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add empty qa"], cwd=str(ws), capture_output=True, check=True)

        from hashlib import sha256
        from subagentbridge.composition import build_production_system
        qa_hash = sha256(qa_file.read_bytes()).hexdigest()
        prod_sys = build_production_system(
            workspace_root=ws,
            custom_qa_hashes={"tests/test_empty.py": qa_hash},
        )

        tree_sha = resolve_tree_sha(ws)
        tasks_contracts, dependencies, task_records = TaskDecomposer.decompose_goal("QA empty test", "run_empty_qa", tree_sha)
        lifecycle = SupervisedNativeLifecycle(sys=prod_sys, workspace_path=ws)
        coord, principals = lifecycle.create_coordinator_for_run("run_empty_qa", tasks_contracts, dependencies)

        res_empty = lifecycle.execute_lifecycle(
            run_id="run_empty_qa",
            coordinator=coord,
            principals=principals,
            task_records=[dict(r) for r in task_records],
            command_map={"default": [sys.executable, "-c", "print('dev pass')"]},
        )
        self.assertEqual(res_empty["status"], "FAILED")

        # Case B: Stdout spoofing (prints "OK" and "Ran 5 tests" but test is skipped)
        spoofed_qa = (
            "import unittest\n"
            "class SpoofedTest(unittest.TestCase):\n"
            "    @unittest.skip('Skipped despite fake stdout')\n"
            "    def test_fake_success(self):\n"
            "        print('Ran 5 tests in 0.001s\\nOK')\n"
            "        self.assertTrue(True)\n"
        )
        qa_file_spoof = qa_dir / "test_spoof.py"
        qa_file_spoof.write_text(spoofed_qa)
        subprocess.run(["git", "add", "tests/test_spoof.py"], cwd=str(ws), capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add spoofed qa"], cwd=str(ws), capture_output=True, check=True)

        qa_hash_spoof = sha256(qa_file_spoof.read_bytes()).hexdigest()
        prod_sys2 = build_production_system(
            workspace_root=ws,
            custom_qa_hashes={"tests/test_spoof.py": qa_hash_spoof},
        )
        tree_sha2 = resolve_tree_sha(ws)
        tasks_contracts2, dependencies2, task_records2 = TaskDecomposer.decompose_goal("QA spoofed test", "run_spoofed_qa", tree_sha2)
        lifecycle2 = SupervisedNativeLifecycle(sys=prod_sys2, workspace_path=ws)
        coord2, principals2 = lifecycle2.create_coordinator_for_run("run_spoofed_qa", tasks_contracts2, dependencies2)

        res_spoof = lifecycle2.execute_lifecycle(
            run_id="run_spoofed_qa",
            coordinator=coord2,
            principals=principals2,
            task_records=[dict(r) for r in task_records2],
            command_map={"default": [sys.executable, "-c", "print('dev pass')"]},
        )
        self.assertEqual(res_spoof["status"], "FAILED")

    def test_PR9_P2_checkout_integrity_porcelain_parsing(self):
        """Focus 3: Verify porcelain parsing handles paths with spaces, renames, and Windows paths."""
        from subagentbridge.execution.native_runtime import _is_ignored_checkout_status_line
        # Space in path: untracked store.db in subfolder with space is ignored
        self.assertTrue(_is_ignored_checkout_status_line('?? "folder with spaces/store.db"'))
        self.assertTrue(_is_ignored_checkout_status_line('?? folder with spaces/store.db'))
        # Space in path: untracked source file in subfolder with space is DIRTY
        self.assertFalse(_is_ignored_checkout_status_line('?? "folder with spaces/source.py"'))
        # Rename is DIRTY
        self.assertFalse(_is_ignored_checkout_status_line('R  "old name.txt" -> "new name.txt"'))
        # Substring with similar name (restore.db.py) is DIRTY
        self.assertFalse(_is_ignored_checkout_status_line(' M restore.db.py'))
        self.assertFalse(_is_ignored_checkout_status_line('?? store.db.bak'))
        # Windows backslash path
        self.assertTrue(_is_ignored_checkout_status_line('?? .subagentbridge\\audit.db'))
        self.assertFalse(_is_ignored_checkout_status_line('?? src\\subagentbridge\\server.py'))

    def test_P1_worker_reservation_exact_once_concurrent_and_cancellation(self):
        """Focus 4: Worker reservation release is thread-safe and exact-once under concurrency and cancel_run."""
        import threading
        identities = IdentityRegistry()
        pm = identities.register("pm-concurrent", Role.PM)
        reg = ReceiptIssuerRegistry(identities)
        budget = BudgetLedger(tokens=1000, cost_microunits=1000, max_workers=5)

        run = Run("r_conc", "proj1", "p1")
        tasks = {f"t_{i}": Task(f"t_{i}", "r_conc", ("crit",), TREE_A, "p1") for i in range(5)}
        coordinator = SupervisedCoordinator(
            run=run,
            tasks=tasks,
            dependencies={f"t_{i}": () for i in range(5)},
            identities=identities,
            receipts=reg,
            budget=budget,
            qa_test_hashes={"tests/qa/test_core.py": DUMMY_HASH},
        )

        for t_id in tasks:
            coordinator.freeze(t_id, pm)
            coordinator.begin(t_id, pm=pm, idempotency_key=f"disp-{t_id}", token_allowance=10, cost_microunits=5)

        self.assertEqual(budget.snapshot()["active"], 5)

        # Concurrently release dispatches across multiple threads (including duplicate calls)
        def release_worker(t_id: str):
            coordinator.release_dispatch(t_id)
            # Repeated release must be a no-op (exact-once)
            coordinator.release_dispatch(t_id)

        threads = [threading.Thread(target=release_worker, args=(t_id,)) for t_id in tasks]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        # All reservations must be released exactly once (0 active, budget intact)
        self.assertEqual(budget.snapshot()["active"], 0)


if __name__ == "__main__":
    unittest.main()
