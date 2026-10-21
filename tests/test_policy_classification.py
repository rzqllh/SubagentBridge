from __future__ import annotations

from dataclasses import replace
import unittest

from subagentbridge.policy.classification import OperationRequest, GateCategory, classify, fingerprint


class ClassificationTests(unittest.TestCase):
    def op(self, action='git.push'):
        return OperationRequest('task1', 'dispatch1', 'policy-v1', action, ('git', 'push'), 'repo-a')

    def test_all_gated_cases_default_denied(self):
        for name in ('auth.change','secret.read','credential.write','dependency.install','dependency.change','ci.modify','deploy','file.delete','branch.delete','data.migrate','git.push','git.force_push','git.rewrite','network.new_host','file.write_outside_workspace','qa.tests.modify','qa.criteria.modify','qa.waive','budget.override','retry.limit_exceeded','tradeoff.material'):
            with self.subTest(action=name):
                decision=classify(self.op(name))
                self.assertTrue(decision.human_gate_required)
                self.assertFalse(decision.execution_authorized)
                self.assertIsNot(decision.category, GateCategory.UNKNOWN)

    def test_unknown_never_becomes_allow(self):
        d=classify(self.op('file.run_as_admin'))
        self.assertEqual(d.category, GateCategory.UNKNOWN)
        self.assertTrue(d.human_gate_required)
        self.assertFalse(d.execution_authorized)

    def test_read_does_not_imply_permission(self):
        d=classify(self.op('file.read'))
        self.assertEqual(d.category, GateCategory.READ)
        self.assertFalse(d.human_gate_required)
        self.assertFalse(d.execution_authorized)

    def test_fingerprint_changes_with_every_bound_dimension(self):
        r=self.op()
        baseline=fingerprint(r)
        for field, value in [('task_id','task2'),('dispatch_id','dispatch2'),('policy_revision','policy-v2'),('operation','git.force_push'),('argv',('git','push','--force')),('resource','repo-b')]:
            with self.subTest(field=field):
                self.assertNotEqual(fingerprint(replace(r,**{field:value})),baseline)

    def test_fingerprint_stable(self):
        self.assertEqual(fingerprint(self.op()),fingerprint(self.op()))
        self.assertEqual(len(fingerprint(self.op())),64)

    def test_no_worker_supplied_approval_argument(self):
        self.assertNotIn('approved', OperationRequest.__dataclass_fields__)
        self.assertNotIn('human_token', OperationRequest.__dataclass_fields__)

    def test_bad_request_fail_closed(self):
        with self.assertRaises(ValueError):
            replace(self.op(),task_id='')
        with self.assertRaises(ValueError):
            replace(self.op(),argv=('git',42))


if __name__=='__main__': unittest.main()
