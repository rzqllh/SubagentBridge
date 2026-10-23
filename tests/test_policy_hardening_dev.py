"""Developer-owned negative tests; not QA invariant tests."""
from __future__ import annotations
from dataclasses import replace
import unittest
from subagentbridge.policy.classification import OperationRequest, GateCategory, classify, fingerprint


class HardenedClassification(unittest.TestCase):
    def op(self, operation, argv=()):
        return OperationRequest('t', 'd', 'p', operation, argv, 'repo')

    def test_file_read_cannot_smuggle_git_push(self):
        d = classify(self.op('file.read', ('git', 'push')))
        self.assertIs(d.category, GateCategory.UNKNOWN)
        self.assertTrue(d.human_gate_required)
        self.assertFalse(d.execution_authorized)

    def test_read_cannot_launch_shell_or_interpreter(self):
        for argv in (('sh','-c','git push'), ('python','-c','print(1)'),
                     ('git','status','--porcelain','--bad'), ('cmd','/c','del','a')):
            for operation in ('task.inspect', 'file.read'):
                with self.subTest(operation=operation, argv=argv):
                    d=classify(self.op(operation,argv))
                    self.assertTrue(d.human_gate_required)
                    self.assertFalse(d.execution_authorized)

    def test_inspect_allows_only_exact_known_read_shape(self):
        for argv in ((), ('git','status','--porcelain'),
                     ('git','rev-parse','HEAD'), ('git','rev-parse','HEAD^{tree}')):
            d = classify(self.op('task.inspect', argv))
            self.assertIs(d.category, GateCategory.READ)
            self.assertFalse(d.human_gate_required)
            self.assertFalse(d.execution_authorized)
        self.assertFalse(classify(self.op('file.read')).human_gate_required)

    def test_rejected_intent_is_bound_in_fingerprint(self):
        read=self.op('file.read')
        suspicious=replace(read,argv=('git','push'))
        self.assertNotEqual(fingerprint(read), fingerprint(suspicious))

    def test_control_character_and_malformed_ids_denied(self):
        for kw in ({'task_id':'\n'}, {'dispatch_id': 1}, {'policy_revision':'bad\x00rev'},
                   {'operation':'file.read\r'}, {'resource':'x'*4097},
                   {'argv': ('git','push\n')}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                replace(self.op('file.read'), **kw)
