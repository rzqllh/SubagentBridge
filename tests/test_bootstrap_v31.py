"""Pinned v3.1 bootstrap document integrity. No dependency installation."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "bootstrap" / "v3_1" / "candidate"
HASHES = {
    "Xyeena_Harness_PATCH_GOAL_v3_1.md": "514288779859d21dba9c3c80b61695522ba533f0da81cd0523faffa1f70c149a",
    "Xyeena_RUNBOOK_v3_1.md": "67e9f24be1cac819808502c8b3bf1bdf9bc73683a9b84d1a15691b4a102e0c92",
    "Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v3_1.md": "acb578d34e7021b13a6bc9e5f320adf26ef0d609f51bac25588abf0f31222646",
    "Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md": "2b840256eb488cbaf1a404bf33ca28a2686b7b34cf062a4c26bb5c0fe7c39f0a",
    "Xyeena_SubagentBridge_TEAM_RULES.md": "aa9e843bb2c13a369c5a26f4932f48418cf4b407e0e3a6659aaab5659f86272b",
    "Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md": "578d860137d0ec8ef3b810c78823fcd5864188961c18372057c66334597c24e0",
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
