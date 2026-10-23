"""Pinned v3.1 bootstrap document integrity. No dependency installation."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "bootstrap" / "v3_1" / "candidate"
HASHES = {
    "Xyeena_Harness_PATCH_GOAL_v3_1.md": "f3070787272c2182c4f085acce6703ee2e50247154cdaa321f7ddeb266df9374",
    "Xyeena_RUNBOOK_v3_1.md": "4b2dd713efeaad71ea81ae39973fb658359e94c3e81a06925fd7a37b9c7695e7",
    "Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v3_1.md": "9069fcd9fa56bdc7fce8c61bf51d34c3d4b01274ca1f2ba1f3379dcc46dba65c",
    "Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md": "2b840256eb488cbaf1a404bf33ca28a2686b7b34cf062a4c26bb5c0fe7c39f0a",
    "Xyeena_SubagentBridge_TEAM_RULES.md": "aa9e843bb2c13a369c5a26f4932f48418cf4b407e0e3a6659aaab5659f86272b",
    "Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md": "2aa3b60d29ae971619fb1984fbef3c1455bf543351356dd07d715b5c20b44dfe",
    "bve_tool.py": "21f1ab40820b94c74daf8921ec9683fc18e3a38c5f4d2d67d27571b790cbfece",
    "bve_tool_original.py": "1528b20cbc17cf7fa3eafc2293c9d478868f766b47dca349f4eeb8b23162f0c6",
}


class BootstrapV31IntegrityTests(unittest.TestCase):
    def test_all_v31_pins_exact(self):
        for name, expected in HASHES.items():
            with self.subTest(name=name):
                path = SOURCE / name
                self.assertTrue(path.is_file(), str(path))
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)

    def test_governing_team_rules_unchanged(self):
        self.assertEqual(
            (ROOT / "docs/TEAM_RULES.md").read_bytes(),
            (SOURCE / "Xyeena_SubagentBridge_TEAM_RULES.md").read_bytes(),
        )

    def test_plan_explicitly_blocks_autonomy(self):
        plan = (SOURCE / "Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md").read_text(encoding="utf-8")
        self.assertIn("AUTONOMY: OFF", plan)
        self.assertIn("AG-1", plan)

    def test_versioned_pointer_exists(self):
        self.assertTrue((ROOT / "artifacts/bootstrap/v3_1/ACTIVE_BASELINE.md").is_file())


if __name__ == "__main__":
    unittest.main()
