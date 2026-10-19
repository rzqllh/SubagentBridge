"""Pinned v3.1 bootstrap document integrity. No dependency installation."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "bootstrap" / "v3_1" / "candidate"
HASHES = {
    "Xyeena_Harness_PATCH_GOAL_v3_1.md": "abca8a64ba951bfa6014788ef69a5d146bf27940c1b6467eb2ae821a91f21240",
    "Xyeena_RUNBOOK_v3_1.md": "60b23657306fd9e3ce2cb73706e03f5f304f615de7cebe716d0fb6c563100afe",
    "Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v3_1.md": "6a764121a7c0129a5cf8fe83a1409919bb3fa35702a2d4c4c019b743cd70be8a",
    "Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md": "2b840256eb488cbaf1a404bf33ca28a2686b7b34cf062a4c26bb5c0fe7c39f0a",
    "Xyeena_SubagentBridge_TEAM_RULES.md": "aa9e843bb2c13a369c5a26f4932f48418cf4b407e0e3a6659aaab5659f86272b",
    "Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md": "a76a9a7c6a2b93e414343ddff2b05474cbda504b74face4b7a5cfaa7cb767793",
    "bve_tool.py": "30db221b6f665cb61a1054bb972b1155fa66633ea6af4f35681f83d9c3f919c6",
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
