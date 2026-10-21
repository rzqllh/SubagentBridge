"""Negative regression vectors against receipt identity and frozen domain contracts.
These are not a security boundary against a malicious process with registry access.
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from subagentbridge.domain import (Capability, Evidence, IdentityRegistry, ReceiptIssuerRegistry,
                                   Role, Task)


class AdversarialContractTests(unittest.TestCase):
    def setUp(self):
        self.identities = IdentityRegistry()
        self.executor = self.identities.register('executor', Role.EXECUTOR)
        self.qa = self.identities.register('qa', Role.QA)
        self.receipts = ReceiptIssuerRegistry(self.identities)

    def receipt(self):
        return self.receipts.issue(self.executor, task_id='t', dispatch_id='d', tree_sha='tree', exit_code=0)

    def test_unregistered_evidence_with_valid_receipt_must_be_rejected(self):
        receipt = self.receipt()
        forged = Evidence('fabricated-evidence-id', receipt.receipt_id, 't', 'd', 'tree')
        with self.assertRaises(PermissionError):
            self.receipts.create_qa_verdict(self.qa, evidence=(forged,), task_id='t', dispatch_id='d', tree_sha='tree', accepted=True)

    def test_tampered_evidence_with_registered_id_is_rejected(self):
        receipt = self.receipt()
        legitimate = self.receipts.create_evidence(receipt.receipt_id, task_id='t', dispatch_id='d', tree_sha='tree')
        altered = replace(legitimate, tree_sha='tree-B')
        with self.assertRaises(PermissionError):
            self.receipts.create_qa_verdict(self.qa, evidence=(altered,), task_id='t', dispatch_id='d', tree_sha='tree', accepted=True)

    def test_false_boolean_exit_code_is_not_a_successful_zero(self):
        with self.assertRaises(ValueError):
            self.receipts.issue(self.executor, task_id='t', dispatch_id='d', tree_sha='tree', exit_code=False)

    def test_string_false_verdict_cannot_become_true(self):
        receipt = self.receipt()
        e = self.receipts.create_evidence(receipt.receipt_id, task_id='t', dispatch_id='d', tree_sha='tree')
        with self.assertRaises(ValueError):
            self.receipts.create_qa_verdict(self.qa, evidence=(e,), task_id='t', dispatch_id='d', tree_sha='tree', accepted='false')

    def test_duplicate_evidence_reuse_in_single_verdict_is_rejected(self):
        receipt = self.receipt()
        e = self.receipts.create_evidence(receipt.receipt_id, task_id='t', dispatch_id='d', tree_sha='tree')
        with self.assertRaises(PermissionError):
            self.receipts.create_qa_verdict(self.qa, evidence=(e, e), task_id='t', dispatch_id='d', tree_sha='tree', accepted=True)

    def test_criteria_list_is_copied_into_immutable_tuple(self):
        criteria = ['original acceptance']
        task = Task('t', 'r', criteria, 'tree', 'policy')
        criteria[0] = 'weakened acceptance'
        self.assertEqual(task.acceptance_criteria, ('original acceptance',))
        self.assertIsInstance(task.acceptance_criteria, tuple)

    def test_capability_role_set_is_defensively_frozen(self):
        roles = {Role.DEVELOPER}
        cap = Capability('write', roles)
        roles.add(Role.PM)
        self.assertEqual(cap.allowed_roles, frozenset({Role.DEVELOPER}))


if __name__ == '__main__':
    unittest.main()
