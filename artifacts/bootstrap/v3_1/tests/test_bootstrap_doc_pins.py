from __future__ import annotations
import hashlib
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'candidate'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class PinContractTests(unittest.TestCase):
    def test_original_helper_unchanged(self):
        self.assertEqual(digest(PKG/'bve_tool_original.py'), '1528b20cbc17cf7fa3eafc2293c9d478868f766b47dca349f4eeb8b23162f0c6')
    def test_team_rules_unchanged(self):
        self.assertEqual(digest(PKG/'Xyeena_SubagentBridge_TEAM_RULES.md'), 'aa9e843bb2c13a369c5a26f4932f48418cf4b407e0e3a6659aaab5659f86272b')
    def test_new_helper_hash_pinned_everywhere(self):
        h=digest(PKG/'bve_tool.py')
        self.assertNotEqual(h,digest(PKG/'bve_tool_original.py'))
        for name in ['Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v3_1.md','Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md','Xyeena_Harness_PATCH_GOAL_v3_1.md','Xyeena_RUNBOOK_v3_1.md']:
            with self.subTest(name=name):
                self.assertIn(h,(PKG/name).read_text())
    def test_new_plan_hash_pinned_everywhere(self):
        h=digest(PKG/'Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md')
        for name in ['Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v3_1.md','Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md','Xyeena_RUNBOOK_v3_1.md']:
            with self.subTest(name=name):
                self.assertIn(h,(PKG/name).read_text())
    def test_verifier_refuses_moved_remote_branch(self):
        s=(PKG/'Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md').read_text()
        self.assertIn('refs/remotes/origin/{{REMOTE_BRANCH}}',s)
        self.assertIn('BLOCKED',s)
        self.assertIn('checkout --detach {{HEAD_SHA}}',s)
    def test_no_old_pin_in_new_binding_docs(self):
        old='1528b20cbc17cf7fa3eafc2293c9d478868f766b47dca349f4eeb8b23162f0c6'
        for name in ['Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v3_1.md','Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md','Xyeena_Harness_PATCH_GOAL_v3_1.md','Xyeena_RUNBOOK_v3_1.md']:
            with self.subTest(name=name):self.assertNotIn(old,(PKG/name).read_text())
