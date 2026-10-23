"""PR-00 integrity contract. Uses only the Python standard library."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TEAM_HASH = "aa9e843bb2c13a369c5a26f4932f48418cf4b407e0e3a6659aaab5659f86272b"
PLAN_HASH = "03650c37da206dcfbc31505a6e2e0e0723d3203ac9157070b3c3bb9c2957dab6"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BootstrapDocumentIntegrityTests(unittest.TestCase):
    def test_team_rules_exact_hash(self):
        self.assertEqual(digest(ROOT / "docs/TEAM_RULES.md"), TEAM_HASH)

    def test_staged_original_team_rules_exact_hash(self):
        self.assertEqual(digest(ROOT / "artifacts/bootstrap/Xyeena_SubagentBridge_TEAM_RULES.md"), TEAM_HASH)

    def test_plan_v2_exact_hash(self):
        self.assertEqual(digest(ROOT / "artifacts/bootstrap/Xyeena_SubagentBridge_Production_PR_Plan_v2.md"), PLAN_HASH)

    def test_goal_and_verifier_present(self):
        for name in ("Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v2.md", "Xyeena_SubagentBridge_VERIFIER_PROMPT.md"):
            path = ROOT / "artifacts/bootstrap" / name
            with self.subTest(name=name):
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 100)

    def test_binding_governing_contract_is_not_mutated(self):
        self.assertEqual(
            (ROOT / "docs/TEAM_RULES.md").read_bytes(),
            (ROOT / "artifacts/bootstrap/Xyeena_SubagentBridge_TEAM_RULES.md").read_bytes(),
        )

    def test_security_qualifications_are_not_silently_removed(self):
        plan = (ROOT / "artifacts/bootstrap/Xyeena_SubagentBridge_Production_PR_Plan_v2.md").read_text(encoding="utf-8")
        for phrase in ("ToolExecutor", "fail-closed", "UNSUPPORTED_ENFORCEMENT", "RECEIPT_AUTHORITY"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, plan)


if __name__ == "__main__":
    unittest.main()
