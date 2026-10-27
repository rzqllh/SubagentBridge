"""PR-03b test-only wiring: NO production runner, executor, or independent QA claim."""
import tempfile
import unittest
from pathlib import Path
from subagentbridge.domain.contracts import Task, Role, TaskState
from subagentbridge.domain.engine import TaskAggregate, InvalidTransition
from subagentbridge.domain.registry import IdentityRegistry, ReceiptIssuerRegistry
from subagentbridge.policy.classification import OperationRequest, classify


class TestOnlyFakeDeveloper:
    def write_patch(self, sandbox: Path):
        p = sandbox / 'change.txt'
        p.write_text('proposed', encoding='utf-8')
        return p


class FakeQaVerifierHelper:
    def __init__(self, registry, principal):
        self.registry, self.principal = registry, principal

    def verify_receipts(self, evidence, task_id, dispatch_id, tree_sha):
        return self.registry.create_qa_verdict(self.principal, evidence=(evidence,),
            task_id=task_id, dispatch_id=dispatch_id, tree_sha=tree_sha, accepted=True)


class SkeletonTests(unittest.TestCase):
    def setUp(self):
        self.identities=IdentityRegistry()
        self.pm=self.identities.register('pm',Role.PM)
        self.dev=self.identities.register('dev',Role.DEVELOPER)
        self.qa=self.identities.register('qa',Role.QA)
        self.executor=self.identities.register('executor',Role.EXECUTOR)
        self.receipts=ReceiptIssuerRegistry(self.identities)
        self.task=Task('task','run',('verify proposed file',),'tree-abc','policy-1')
        self.aggregate=TaskAggregate(self.task,self.identities,self.receipts)
        self.aggregate.freeze(self.pm)
        self.dispatch=self.aggregate.dispatch(self.pm,idempotency_key='once')

    def evidence(self):
        r=self.receipts.issue(self.executor,task_id='task',dispatch_id=self.dispatch.dispatch_id,
                              tree_sha='tree-abc',exit_code=0)
        return self.receipts.create_evidence(r.receipt_id,task_id='task',
                   dispatch_id=self.dispatch.dispatch_id,tree_sha='tree-abc')

    def test_positive_frozen_ac_fake_patch_executor_and_qa(self):
        with tempfile.TemporaryDirectory() as root:
            p=TestOnlyFakeDeveloper().write_patch(Path(root))
            self.assertEqual(p.read_text(),'proposed')
        self.aggregate.process_succeeded(self.dispatch.dispatch_id,'tree-abc')
        v=FakeQaVerifierHelper(self.receipts,self.qa).verify_receipts(
            self.evidence(),'task',self.dispatch.dispatch_id,'tree-abc')
        self.aggregate.qa_verified(self.qa,v)
        self.aggregate.mark_verified(self.qa)
        self.assertEqual(self.aggregate.state,TaskState.VERIFIED)

    def test_dev_and_pm_cannot_finalize_qa(self):
        self.aggregate.process_succeeded(self.dispatch.dispatch_id,'tree-abc')
        evidence=self.evidence()
        for actor in (self.dev,self.pm):
            with self.assertRaises(PermissionError):
                self.receipts.create_qa_verdict(actor,evidence=(evidence,),task_id='task',
                    dispatch_id=self.dispatch.dispatch_id,tree_sha='tree-abc',accepted=True)
        with self.assertRaises((PermissionError,InvalidTransition)):
            self.aggregate.mark_verified(self.dev)

    def test_qa_without_executor_receipt_is_denied(self):
        with self.assertRaises(PermissionError):
            self.receipts.create_qa_verdict(self.qa,evidence=(),task_id='task',
                dispatch_id=self.dispatch.dispatch_id,tree_sha='tree-abc',accepted=True)

    def test_unanswered_gate_is_not_authorized(self):
        d=classify(OperationRequest('task',self.dispatch.dispatch_id,'policy-1',
                   'ci.modify',('edit','workflow.yml'),'workflow.yml'))
        self.assertTrue(d.human_gate_required)
        self.assertFalse(d.execution_authorized)
        self.aggregate.block()
        self.assertEqual(self.aggregate.state,TaskState.BLOCKED)

    def test_tree_change_revokes_verification(self):
        self.aggregate.process_succeeded(self.dispatch.dispatch_id,'tree-abc')
        v=FakeQaVerifierHelper(self.receipts,self.qa).verify_receipts(
            self.evidence(),'task',self.dispatch.dispatch_id,'tree-abc')
        self.aggregate.qa_verified(self.qa,v)
        self.aggregate.mark_verified(self.qa)
        self.aggregate.change_tree('tree-new')
        self.assertNotEqual(self.aggregate.state,TaskState.VERIFIED)
        self.assertIsNone(self.aggregate.qa_verdict)

    def test_no_fake_principals_in_production_composition(self):
        prod=Path(__file__).resolve().parents[2] / 'subagentbridge'
        if not (prod/'composition.py').exists():
            self.skipTest('production composition root absent; INV-12 is UNVERIFIED')
        text=(prod/'composition.py').read_text(encoding='utf-8')
        self.assertNotIn('TestOnlyFake',text)

if __name__=='__main__':
    unittest.main()
