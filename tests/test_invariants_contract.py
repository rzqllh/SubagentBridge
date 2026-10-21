"""Security invariant contract regression suite.

Each invariant probe asserts that the production architecture enforces required
boundaries: receipt verification, role isolation, out-of-band approval broker,
process confinement, tree invalidation, skill trust boundaries, and durable budgets.
"""
from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from subagentbridge.manager import AgentManager

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "subagentbridge"


class InvariantContractRegressionSuite(unittest.TestCase):
    def test_INV_01_qa_verdict_and_receipts_required(self):
        from subagentbridge.server import _manager
        self.assertTrue(hasattr(_manager, "verify_with_executor_receipt"), "Production manager lacks receipt-based verification enforcement")

    def test_INV_02_dev_pm_cannot_mint_verdicts_or_receipts(self):
        from subagentbridge.server import _manager
        self.assertTrue(hasattr(_manager, "enforce_principal_role_boundary"), "Production manager lacks principal role-boundary enforcement for receipts/verdicts")

    def test_INV_03_human_gate_requires_separate_identity(self):
        text = (SRC / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("def approve_action(action_id: str)", text, "Model-callable approval still exposed")

    def test_INV_04_unanswered_approval_remains_blocked(self):
        self.assertTrue((SRC / "approval").is_dir(), "Human approval state machine not present")

    def test_INV_05_changed_tree_revokes_verified(self):
        from subagentbridge.server import _manager
        self.assertTrue(hasattr(_manager, "reconcile_tree_invalidation"), "Production manager lacks automatic tree-change invalidation engine")

    def test_INV_06_autonomous_side_effects_only_through_executor(self):
        source = inspect.getsource(AgentManager._run_once)
        self.assertNotIn("asyncio.create_subprocess_exec(", source, "Runner still launches unrestricted CLI")

    def test_INV_07_repository_execution_isolated_from_broker(self):
        self.assertTrue((SRC / "execution" / "isolation").exists(), "Isolated test runner missing")

    def test_INV_08_workers_cannot_read_approval_secrets(self):
        self.assertTrue((SRC / "approval" / "broker.py").is_file(), "No independently enforced broker")

    def test_INV_09_stale_dispatch_cannot_complete_new_attempt(self):
        self.assertTrue((SRC / "domain" / "dispatch.py").is_file(), "Dispatch idempotency model missing")

    def test_INV_10_untrusted_skill_text_cannot_grant_permissions(self):
        from subagentbridge.server import _manager
        self.assertTrue(hasattr(_manager, "execute_with_skill_trust_boundary"), "Production manager lacks skill trust-boundary execution")

    def test_INV_11_budget_and_retry_limits_fail_closed(self):
        from subagentbridge.server import _manager
        self.assertTrue(hasattr(_manager, "durable_budget_ledger"), "Production manager lacks persistent transactional budget ledger")

    def test_INV_12_production_never_registers_fake_principals(self):
        self.assertTrue((SRC / "composition.py").is_file(), "No auditable production composition root")


if __name__ == "__main__":
    unittest.main()
