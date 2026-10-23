"""Independent-to-P0 preparation: deterministic domain contract tests.

No subprocesses, network, third-party packages, credentials, or filesystem
changes outside unittest's own runtime. This does NOT prove QA independence.
"""
from __future__ import annotations

from dataclasses import replace
import random
import unittest

from subagentbridge.domain import (
    Approval, Budget, Capability, Evidence, IdentityRegistry, InvalidTransition,
    Message, ReceiptIssuerRegistry, Role, Run, StaleDispatch, Task,
    TaskAggregate, TaskState,
)
from subagentbridge.domain.registry import Principal, QaVerdict


class DomainScenario(unittest.TestCase):
    def setUp(self):
        self.identities = IdentityRegistry()
        self.pm = self.identities.register("pm", Role.PM)
        self.dev = self.identities.register("dev", Role.DEVELOPER)
        self.qa = self.identities.register("qa", Role.QA)
        self.executor = self.identities.register("bridge-executor", Role.EXECUTOR)
        self.registry = ReceiptIssuerRegistry(self.identities)
        self.run = Run("r-1", "project", "policy-v1")
        self.task = Task("t-1", "r-1", ("tests pass", "no auth bypass"), "git-tree-A", "policy-v1")
        self.aggregate = TaskAggregate(self.task, self.identities, self.registry)

    def freeze_dispatch(self, key="k1"):
        self.aggregate.freeze(self.pm)
        return self.aggregate.dispatch(self.pm, idempotency_key=key)

    def execute(self, dispatch):
        r = self.registry.issue(self.executor, task_id=self.task.task_id,
                                dispatch_id=dispatch.dispatch_id, tree_sha=dispatch.tree_sha, exit_code=0)
        evidence = self.registry.create_evidence(r.receipt_id, task_id=self.task.task_id,
                                                 dispatch_id=dispatch.dispatch_id, tree_sha=dispatch.tree_sha)
        self.aggregate.process_succeeded(dispatch.dispatch_id, dispatch.tree_sha)
        return evidence

    def qa_pass(self, dispatch, evidence):
        verdict = self.registry.create_qa_verdict(self.qa, evidence=(evidence,),
                                                  task_id=self.task.task_id,
                                                  dispatch_id=dispatch.dispatch_id,
                                                  tree_sha=dispatch.tree_sha, accepted=True)
        self.aggregate.qa_verified(self.qa, verdict)
        self.aggregate.mark_verified(self.qa)
        return verdict

    def test_generated_dispatch_ids_never_repeat_for_100_attempts(self):
        self.aggregate.freeze(self.pm)
        seen = set()
        for attempt in range(100):
            d = self.aggregate.dispatch(self.pm, idempotency_key=f"key-{attempt}")
            self.assertNotIn(d.dispatch_id, seen)
            seen.add(d.dispatch_id)
            self.aggregate.change_tree(f"git-tree-{attempt + 1}")
        self.assertEqual(len(seen), 100)

    def test_stale_completion_is_fail_closed_across_100_attempts(self):
        self.aggregate.freeze(self.pm)
        stale_dispatches = []
        for attempt in range(100):
            d = self.aggregate.dispatch(self.pm, idempotency_key=f"run-key-{attempt}")
            stale_dispatches.append(d)
            self.aggregate.change_tree(f"git-tree-{attempt + 1}")
        current = self.aggregate.dispatch(self.pm, idempotency_key="fresh-key")
        rng = random.Random(2026)
        rng.shuffle(stale_dispatches)
        for d in stale_dispatches:
            with self.assertRaises(StaleDispatch):
                self.aggregate.process_succeeded(d.dispatch_id, d.tree_sha)
        self.assertEqual(self.aggregate.state, TaskState.DISPATCHED)
        self.assertEqual(current, self.aggregate.active_dispatch)

    def test_qa_forged_receipt_ids_rejected_in_100_trials(self):
        d = self.freeze_dispatch()
        for i in range(100):
            forged = Evidence(f"evidence-{i}", f"not-issued-{i}", "t-1", d.dispatch_id, d.tree_sha)
            with self.assertRaises(PermissionError):
                self.registry.create_qa_verdict(self.qa, evidence=(forged,), task_id="t-1",
                                                 dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=True)

    def test_e2e_staged_verified(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        self.qa_pass(d, e)
        self.assertIs(self.aggregate.state, TaskState.VERIFIED)
        self.assertEqual(self.aggregate.verified_tree_sha, "git-tree-A")

    def test_pm_must_not_mark_verified(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        self.qa_pass(d, e)
        with self.assertRaises(PermissionError):
            self.aggregate.mark_verified(self.pm)

    def test_developer_cannot_issue_receipt(self):
        d = self.freeze_dispatch()
        with self.assertRaises(PermissionError):
            self.registry.issue(self.dev, task_id="t-1", dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, exit_code=0)

    def test_pm_cannot_issue_qa_verdict(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        with self.assertRaises(PermissionError):
            self.registry.create_qa_verdict(self.pm, evidence=(e,), task_id="t-1",
                                             dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=True)

    def test_forged_receipt_fails(self):
        d = self.freeze_dispatch()
        with self.assertRaises(PermissionError):
            self.registry.create_evidence("fabricated", task_id="t-1", dispatch_id=d.dispatch_id, tree_sha=d.tree_sha)

    def test_forged_evidence_fails(self):
        d = self.freeze_dispatch()
        forged = Evidence("faked-evidence", "fake-receipt", "t-1", d.dispatch_id, d.tree_sha)
        with self.assertRaises(PermissionError):
            self.registry.create_qa_verdict(self.qa, evidence=(forged,), task_id="t-1",
                                             dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=True)

    def test_failed_execution_cannot_support_qa(self):
        d = self.freeze_dispatch()
        receipt = self.registry.issue(self.executor, task_id="t-1", dispatch_id=d.dispatch_id,tree_sha=d.tree_sha,exit_code=1)
        with self.assertRaises(PermissionError):
            self.registry.create_evidence(receipt.receipt_id, task_id="t-1", dispatch_id=d.dispatch_id,tree_sha=d.tree_sha)

    def test_wrong_tree_evidence_fails(self):
        d = self.freeze_dispatch()
        r = self.registry.issue(self.executor, task_id="t-1", dispatch_id=d.dispatch_id,tree_sha=d.tree_sha,exit_code=0)
        with self.assertRaises(PermissionError):
            self.registry.create_evidence(r.receipt_id, task_id="t-1", dispatch_id=d.dispatch_id,tree_sha="git-tree-B")

    def test_unregistered_role_string_cannot_spoof_qa(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        fake = Principal("anonymous", Role.QA)
        with self.assertRaises(PermissionError):
            self.registry.create_qa_verdict(fake, evidence=(e,), task_id="t-1",
                                             dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=True)

    def test_mismatched_registered_role_cannot_spoof_qa(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        fake = Principal(self.dev.principal_id, Role.QA)
        with self.assertRaises(PermissionError):
            self.registry.create_qa_verdict(fake, evidence=(e,), task_id="t-1",
                                             dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=True)

    def test_cannot_assign_verified_state_directly(self):
        with self.assertRaises(AttributeError):
            self.aggregate.state = TaskState.VERIFIED

    def test_cannot_spoof_registered_qa_by_reusing_id(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        forged = Principal(self.qa.principal_id, Role.QA)
        with self.assertRaises(PermissionError):
            self.registry.create_qa_verdict(forged, evidence=(e,), task_id="t-1",
                                             dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=True)

    def test_missing_qa_verdict_stops_verified(self):
        d = self.freeze_dispatch()
        self.execute(d)
        with self.assertRaises(InvalidTransition):
            self.aggregate.mark_verified(self.qa)
        self.assertNotEqual(self.aggregate.state, TaskState.VERIFIED)

    def test_verdict_without_evidence_rejected(self):
        d = self.freeze_dispatch()
        self.aggregate.process_succeeded(d.dispatch_id, d.tree_sha)
        with self.assertRaises(PermissionError):
            self.registry.create_qa_verdict(self.qa, evidence=(), task_id="t-1",
                                             dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=True)

    def test_negative_qa_verdict_cannot_verify(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        bad = self.registry.create_qa_verdict(self.qa, evidence=(e,), task_id="t-1",
                                               dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=False)
        with self.assertRaises(PermissionError):
            self.aggregate.qa_verified(self.qa, bad)

    def test_forged_qa_verdict_fails(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        v = self.registry.create_qa_verdict(self.qa, evidence=(e,), task_id="t-1",
                                             dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=True)
        forged = replace(v, accepted=False)
        with self.assertRaises(PermissionError):
            self.aggregate.qa_verified(self.qa, forged)

    def test_tree_change_revokes_verified(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        self.qa_pass(d, e)
        self.aggregate.change_tree("git-tree-B")
        self.assertIs(self.aggregate.state, TaskState.FROZEN)
        self.assertIsNone(self.aggregate.verified_tree_sha)
        self.assertIsNone(self.aggregate.qa_verdict)

    def test_stale_dispatch_after_tree_change(self):
        d = self.freeze_dispatch()
        self.aggregate.change_tree("git-tree-B")
        with self.assertRaises(StaleDispatch):
            self.aggregate.process_succeeded(d.dispatch_id, d.tree_sha)
        self.assertIs(self.aggregate.state, TaskState.FROZEN)

    def test_duplicate_idempotency_key_rejected(self):
        self.freeze_dispatch()
        self.aggregate.change_tree("git-tree-B")
        with self.assertRaises(InvalidTransition):
            self.aggregate.dispatch(self.pm, idempotency_key="k1")

    def test_stale_dispatch_after_new_attempt(self):
        d = self.freeze_dispatch()
        self.aggregate.change_tree("git-tree-B")
        d2 = self.aggregate.dispatch(self.pm, idempotency_key="k2")
        with self.assertRaises(StaleDispatch):
            self.aggregate.process_succeeded(d.dispatch_id, d.tree_sha)
        self.assertIs(self.aggregate.state, TaskState.DISPATCHED)
        self.assertEqual(self.aggregate.active_dispatch, d2)

    def test_no_double_completion(self):
        d = self.freeze_dispatch()
        self.aggregate.process_succeeded(d.dispatch_id, d.tree_sha)
        with self.assertRaises(InvalidTransition):
            self.aggregate.process_succeeded(d.dispatch_id, d.tree_sha)

    def test_cannot_dispatch_without_freeze(self):
        with self.assertRaises(InvalidTransition):
            self.aggregate.dispatch(self.pm, idempotency_key="k1")

    def test_cannot_change_roles_after_registration(self):
        with self.assertRaises(ValueError):
            self.identities.register("qa", Role.PM)

    def test_policy_revision_mandatory(self):
        with self.assertRaises(ValueError):
            Run("r", "p", "")
        with self.assertRaises(ValueError):
            Task("t", "r", ("criterion",), "tree", "")

    def test_schema_version_reject_unknown(self):
        with self.assertRaises(ValueError):
            Run("r", "p", "rev", schema_version=99)

    def test_message_requires_routing(self):
        with self.assertRaises(ValueError):
            Message("m", "qa", "pm", "", "d", "hello")

    def test_budget_rejects_negative(self):
        with self.assertRaises(ValueError):
            Budget(max_tokens=-1, max_attempts=1, max_cost_microunits=0)

    def test_approval_record_is_not_executable_grant(self):
        approval = Approval("id", "operation-sha", "policy-revision", approved=True)
        self.assertTrue(approval.approved)
        self.assertFalse(hasattr(approval, "authorize_execution"))

    def test_qa_is_bound_to_specific_issuer(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        verdict = self.registry.create_qa_verdict(self.qa, evidence=(e,), task_id="t-1",
                                                   dispatch_id=d.dispatch_id, tree_sha=d.tree_sha, accepted=True)
        alternate = self.identities.register("qa2", Role.QA)
        with self.assertRaises(PermissionError):
            self.aggregate.qa_verified(alternate, verdict)

    def test_missing_dispatch_identity_is_rejected(self):
        with self.assertRaises(StaleDispatch):
            self.aggregate.process_succeeded("unknown", "git-tree-A")

    def test_unknown_state_value_rejected(self):
        with self.assertRaises(ValueError):
            TaskState("INJECTED_VERIFIED")

    def test_block_revokes_verification(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        self.qa_pass(d, e)
        self.aggregate.block()
        self.assertEqual(self.aggregate.state, TaskState.BLOCKED)
        self.assertIsNone(self.aggregate.verified_tree_sha)

    def test_recovery_required_revokes_verification(self):
        d = self.freeze_dispatch()
        e = self.execute(d)
        self.qa_pass(d, e)
        self.aggregate.recover_unknown()
        self.assertEqual(self.aggregate.state, TaskState.RECOVERY_REQUIRED)
        self.assertIsNone(self.aggregate.verified_tree_sha)


if __name__ == "__main__":
    unittest.main()
