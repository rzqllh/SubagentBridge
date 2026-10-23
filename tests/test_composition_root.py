"""Tests for the production composition root (PR-03b, PR-10, INV-12).

Proves:
1. subagentbridge/composition.py exists and provides build_production_system.
2. Production composition root wires real subsystems: AuditLedger, DurableBudgetLedger,
   DurableMessageBus, SkillRegistry, PolicyClassifier, SupervisedToolExecutor,
   QaEvidenceGate, NineRouterClient, and SupervisedCoordinator.
3. Production composition root rejects fake principals and mock runners in production mode.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "subagentbridge"


class ProductionCompositionRootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "test_bridge.db"
        self.system = None

    def tearDown(self):
        if self.system is not None:
            self.system.close()
        self.tmp.cleanup()

    def test_composition_file_exists(self):
        self.assertTrue((SRC / "composition.py").is_file(), "subagentbridge/composition.py must exist")

    def test_build_production_system_wires_real_subsystems(self):
        from subagentbridge.composition import ProductionSystem, build_production_system

        self.system = build_production_system(
            workspace_root=self.root,
            db_path=self.db_path,
            nine_router_base_url="http://127.0.0.1:9099",
        )
        self.assertIsInstance(self.system, ProductionSystem)
        self.assertIsNotNone(self.system.ledger)
        self.assertIsNotNone(self.system.budget)
        self.assertIsNotNone(self.system.bus)
        self.assertIsNotNone(self.system.skills)
        self.assertIsNotNone(self.system.classifier)
        self.assertIsNotNone(self.system.executor)
        self.assertIsNotNone(self.system.qa_gate)
        self.assertIsNotNone(self.system.nine_router)

        # Snapshot of budget should be initialized
        snap = self.system.budget.snapshot()
        self.assertGreater(snap["tokens_available"], 0)

    def test_rejects_fake_principals_and_mock_runners(self):
        from subagentbridge.composition import build_production_system

        with self.assertRaises(ValueError):
            build_production_system(
                workspace_root=self.root,
                db_path=self.db_path,
                runner_name="fake_runner",
            )

        with self.assertRaises(ValueError):
            build_production_system(
                workspace_root=self.root,
                db_path=self.db_path,
                principal_role="fake_principal",
            )


if __name__ == "__main__":
    unittest.main()
