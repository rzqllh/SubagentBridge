"""Stdlib-only deterministic *fake* PM/Developer/QA control-plane smoke.

No real LLM/provider calls, execution, broker, Antigravity integration, or
security attestations. All principals/receipts are simulated in-process; the
output MUST NEVER be presented as production QA VERIFIED.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from subagentbridge.domain import Role, Run, Task, TaskState
from subagentbridge.domain.registry import IdentityRegistry, ReceiptIssuerRegistry
from subagentbridge.domain.engine import InvalidTransition
from subagentbridge.messaging.bus import DurableMessageBus
from subagentbridge.domain.contracts import Message
from subagentbridge.planner.budget import BudgetLedger
from subagentbridge.release.readiness import ReleaseGate
from subagentbridge.storage.audit_ledger import AuditLedger
from subagentbridge.team.coordinator import SupervisedCoordinator

TREE = 'f' * 40  # fake tree; NOT a real Git checkout or signed receipt
TESTS = {'tests/fake_qa.py': '1' * 64}


def run_supervised_fake_smoke() -> dict:
    """Run one complete in-process fake flow and test fail-closed edges."""
    ids = IdentityRegistry()
    pm = ids.register('fake-pm', Role.PM)
    developer = ids.register('fake-dev', Role.DEVELOPER)
    qa = ids.register('fake-qa', Role.QA)
    executor = ids.register('fake-executor', Role.EXECUTOR)
    receipts = ReceiptIssuerRegistry(ids)
    coordinator = SupervisedCoordinator(
        run=Run('fake-run', 'fake-project', 'test-policy'),
        tasks={
            'implement': Task('implement','fake-run',('fake patch',),TREE,'test-policy'),
            'verify': Task('verify','fake-run',('fake review',),TREE,'test-policy'),
        },
        dependencies={'implement': (), 'verify': ('implement',)},
        identities=ids, receipts=receipts,
        budget=BudgetLedger(tokens=10,cost_microunits=10,max_workers=1),
        qa_test_hashes=TESTS,
    )
    with TemporaryDirectory() as directory:
        ledger = AuditLedger(Path(directory) / 'events.db')
        try:
            message_bus = DurableMessageBus(ledger,stream='fake-run')
            coordinator.freeze('verify', pm)
            dependency_denied = False
            try:
                coordinator.begin('verify', pm=pm, idempotency_key='premature',
                                  token_allowance=1, cost_microunits=1)
            except InvalidTransition:
                dependency_denied = True
            if not dependency_denied:
                raise AssertionError('dependency gate bypassed')
            result = []
            for task_id, ac in (('implement','fake patch'),('verify','fake review')):
                if task_id == 'implement':
                    coordinator.freeze(task_id, pm)
                dispatch = coordinator.begin(task_id, pm=pm,
                    idempotency_key=f'fake-{task_id}',token_allowance=2,
                    cost_microunits=2)
                if dispatch.runtime_authorized:
                    raise AssertionError('fake dispatch must never authorize runtime')
                message = Message(f'msg-{task_id}', developer.principal_id,
                    qa.principal_id,task_id,dispatch.dispatch_id,'fake review request')
                if not message_bus.enqueue(message,active_task_id=task_id,
                    active_dispatch_id=dispatch.dispatch_id):
                    raise AssertionError('message not queued')
                if message_bus.enqueue(message,active_task_id=task_id,
                    active_dispatch_id=dispatch.dispatch_id):
                    raise AssertionError('duplicate message accepted as new')
                if not message_bus.ack(message.message_id,recipient_id=qa.principal_id):
                    raise AssertionError('message acknowledgement not stored')
                coordinator.report_process_succeeded(developer=developer,
                    task_id=task_id,dispatch_id=dispatch.dispatch_id,tree_sha=TREE)
                receipt = receipts.issue(executor,task_id=task_id,
                    dispatch_id=dispatch.dispatch_id,tree_sha=TREE,exit_code=0)
                evidence = receipts.create_evidence(receipt.receipt_id,
                    task_id=task_id,dispatch_id=dispatch.dispatch_id,tree_sha=TREE)
                decision = coordinator.qa_review(qa=qa, task_id=task_id,
                    evidence=(evidence,),covered_criteria=(ac,),
                    actual_test_hashes=TESTS,actual_tree_sha=TREE,clean=True,fix_round=0)
                if decision.status != 'QA_VERIFIED' or coordinator.state(task_id) is not TaskState.VERIFIED:
                    raise AssertionError('fake QA wiring failed')
                result.append(task_id)
            initial_states = dict(coordinator.snapshot()['tasks'])
            coordinator.update_tree('e' * 40)
            revoked = all(v != 'VERIFIED' for v in coordinator.snapshot()['tasks'].values())
            if not revoked:
                raise AssertionError('changed tree failed to revoke fake verified states')
            audit_events = ledger.read(stream='fake-run',reader_stream='fake-run')
            ledger.verify(stream='fake-run')
            release = ReleaseGate.evaluate({})
            if release.status != 'UNVERIFIED':
                raise AssertionError('missing release evidence mistakenly accepted')
            return {
                'status':'FAKE_ONLY_PASS', 'autonomy':False,
                'tasks_fake_verified_before_tree_change':initial_states,
                'tasks_after_tree_change':dict(coordinator.snapshot()['tasks']),
                'audit_event_count':len(audit_events),
                'dependency_denial':dependency_denied,
                'duplicate_messages_denied':True,
                'release_status':release.status,
                'provider_calls':0,
                'real_executor_calls':0,
                'security_certified':False,
            }
        finally:
            ledger.close()


if __name__ == '__main__':
    print(json.dumps(run_supervised_fake_smoke(),sort_keys=True,indent=2))
