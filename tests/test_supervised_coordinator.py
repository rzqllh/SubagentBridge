"""Deterministic fake receipt wiring; NOT independently verified QA or OS isolation."""
import unittest
from subagentbridge.domain import Run, Task, Role, TaskState
from subagentbridge.domain.registry import IdentityRegistry, ReceiptIssuerRegistry
from subagentbridge.planner.budget import BudgetLedger, BudgetExceeded
from subagentbridge.domain.engine import InvalidTransition
from subagentbridge.team.coordinator import SupervisedCoordinator

TREE = 'a' * 40
TREE2 = 'b' * 40
HASHES = {'tests/qa_owned.py': 'c' * 64}


def make_coordinator(*, tokens=100, deps=None):
    ids = IdentityRegistry()
    pm = ids.register('pm', Role.PM)
    dev = ids.register('dev', Role.DEVELOPER)
    qa = ids.register('qa', Role.QA)
    executor = ids.register('fake-executor-test-only', Role.EXECUTOR)
    receipts = ReceiptIssuerRegistry(ids)
    tasks = {'build': Task('build', 'run', ('code works',), TREE, 'v1'),
             'review': Task('review', 'run', ('test works',), TREE, 'v1')}
    obj = SupervisedCoordinator(run=Run('run', 'project', 'v1'), tasks=tasks,
        dependencies=deps if deps is not None else {'build': (), 'review': ('build',)},
        identities=ids, receipts=receipts,
        budget=BudgetLedger(tokens=tokens, cost_microunits=100, max_workers=1),
        qa_test_hashes=HASHES)
    return obj, pm, dev, qa, executor, receipts


def verify(coordinator, pm, dev, qa, executor, registry, task_id):
    coordinator.freeze(task_id, pm)
    d = coordinator.begin(task_id, pm=pm, idempotency_key=task_id,
                          token_allowance=5, cost_microunits=2)
    assert not d.runtime_authorized
    coordinator.report_process_succeeded(developer=dev, task_id=task_id,
                                         dispatch_id=d.dispatch_id, tree_sha=TREE)
    receipt = registry.issue(executor, task_id=task_id,
                             dispatch_id=d.dispatch_id, tree_sha=TREE, exit_code=0)
    evidence = registry.create_evidence(receipt.receipt_id,
        task_id=task_id, dispatch_id=d.dispatch_id, tree_sha=TREE)
    return coordinator.qa_review(qa=qa, task_id=task_id, evidence=(evidence,),
        covered_criteria=('code works',) if task_id == 'build' else ('test works',),
        actual_test_hashes=HASHES, actual_tree_sha=TREE, clean=True, fix_round=0)


class SupervisedCoordinatorTests(unittest.TestCase):
    def test_two_task_dag_fake_qa_journey(self):
        c, pm, dev, qa, exe, reg = make_coordinator()
        self.assertEqual(verify(c, pm, dev, qa, exe, reg, 'build').status, 'QA_VERIFIED')
        self.assertEqual(verify(c, pm, dev, qa, exe, reg, 'review').status, 'QA_VERIFIED')
        self.assertEqual(c.state('review'), TaskState.VERIFIED)
        self.assertFalse(c.snapshot()['autonomy'])
        self.assertEqual(c.snapshot()['budget']['tokens_available'], 90)

    def test_cannot_dispatch_before_dependency_verified(self):
        c, pm, dev, qa, exe, reg = make_coordinator()
        c.freeze('review', pm)
        with self.assertRaises(InvalidTransition):
            c.begin('review', pm=pm, idempotency_key='early', token_allowance=1,
                    cost_microunits=1)
        self.assertEqual(c.snapshot()['budget']['tokens_available'], 100)

    def test_developer_cannot_qa_review(self):
        c, pm, dev, qa, exe, reg = make_coordinator()
        c.freeze('build', pm)
        d = c.begin('build', pm=pm, idempotency_key='one', token_allowance=1,
                    cost_microunits=1)
        c.report_process_succeeded(developer=dev, task_id='build',
                                   dispatch_id=d.dispatch_id, tree_sha=TREE)
        with self.assertRaises(PermissionError):
            c.qa_review(qa=dev, task_id='build', evidence=(), covered_criteria=('code works',),
                actual_test_hashes=HASHES, actual_tree_sha=TREE, clean=True, fix_round=0)

    def test_tree_change_revokes_both_verified_dependencies(self):
        c, pm, dev, qa, exe, reg = make_coordinator()
        verify(c, pm, dev, qa, exe, reg, 'build')
        verify(c, pm, dev, qa, exe, reg, 'review')
        c.update_tree(TREE2)
        self.assertEqual(c.state('build'), TaskState.FROZEN)
        self.assertEqual(c.state('review'), TaskState.FROZEN)

    def test_active_dispatch_requires_recovery_when_tree_changes(self):
        c, pm, dev, qa, exe, reg = make_coordinator()
        c.freeze('build', pm)
        c.begin('build', pm=pm, idempotency_key='live', token_allowance=5,
                cost_microunits=1)
        c.update_tree(TREE2)
        self.assertEqual(c.state('build'), TaskState.RECOVERY_REQUIRED)
        self.assertEqual(c.snapshot()['budget']['active'], 1)

    def test_budget_denies_without_consuming_dispatch(self):
        c, pm, dev, qa, exe, reg = make_coordinator(tokens=2)
        c.freeze('build', pm)
        with self.assertRaises(BudgetExceeded):
            c.begin('build', pm=pm, idempotency_key='b', token_allowance=5,
                    cost_microunits=1)
        self.assertEqual(c.state('build'), TaskState.FROZEN)
        self.assertEqual(c.snapshot()['budget']['tokens_available'], 2)

    def test_unverified_test_hash_or_waiver_does_not_release_budget(self):
        c, pm, dev, qa, exe, reg = make_coordinator()
        c.freeze('build', pm)
        d = c.begin('build', pm=pm, idempotency_key='b', token_allowance=5,
                    cost_microunits=1)
        c.report_process_succeeded(developer=dev, task_id='build',
                                   dispatch_id=d.dispatch_id, tree_sha=TREE)
        receipt = reg.issue(exe, task_id='build', dispatch_id=d.dispatch_id, tree_sha=TREE, exit_code=0)
        ev = reg.create_evidence(receipt.receipt_id, task_id='build', dispatch_id=d.dispatch_id, tree_sha=TREE)
        decision = c.qa_review(qa=qa, task_id='build', evidence=(ev,),
              covered_criteria=('code works',), actual_test_hashes={'tests/qa_owned.py':'d'*64},
              actual_tree_sha=TREE, clean=True, fix_round=0)
        self.assertEqual(decision.status, 'UNVERIFIED')
        self.assertEqual(c.state('build'), TaskState.PROCESS_SUCCEEDED)
        self.assertEqual(c.snapshot()['budget']['active'], 1)

    def test_missing_ac_blocks_constructor(self):
        with self.assertRaises(ValueError):
            SupervisedCoordinator(run=Run('r','p','v'), tasks={}, dependencies={},
                identities=IdentityRegistry(), receipts=ReceiptIssuerRegistry(IdentityRegistry()),
                budget=BudgetLedger(tokens=1,cost_microunits=1,max_workers=1),qa_test_hashes=HASHES)

if __name__ == '__main__': unittest.main()
