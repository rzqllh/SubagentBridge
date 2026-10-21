import unittest
from subagentbridge.domain.contracts import Role, Evidence
from subagentbridge.domain.registry import IdentityRegistry, ReceiptIssuerRegistry
from subagentbridge.qa import QaEvidenceGate

class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.ids=IdentityRegistry()
        self.qa=self.ids.register('qa',Role.QA)
        self.dev=self.ids.register('dev',Role.DEVELOPER)
        self.exec=self.ids.register('exec',Role.EXECUTOR)
        self.registry=ReceiptIssuerRegistry(self.ids)
        self.pinned={'tests/qa_owned.py':'a'*64}
        self.gate=QaEvidenceGate(self.registry,frozen_criteria=('AC1','AC2'),qa_test_hashes=self.pinned)
        receipt=self.registry.issue(self.exec,task_id='t',dispatch_id='d',tree_sha='tree',exit_code=0)
        self.evidence=(self.registry.create_evidence(receipt.receipt_id,task_id='t',dispatch_id='d',tree_sha='tree'),)
    def check(self,**kwargs):
        p=dict(qa=self.qa,evidence=self.evidence,covered_criteria=('AC1','AC2'),
          actual_test_hashes=self.pinned,task_id='t',dispatch_id='d',expected_tree='tree',
          actual_tree='tree',checkout_clean=True,fix_round=0)
        p.update(kwargs)
        return self.gate.check(**p)
    def test_registered_receipts_and_full_coverage(self):
        status,verdict=self.check()
        self.assertEqual(status.status,'QA_VERIFIED')
        self.assertIsNotNone(verdict)
    def test_fake_receipt_is_denied(self):
        forged=Evidence('unissued','unissued','t','d','tree')
        status,verdict=self.check(evidence=(forged,))
        self.assertEqual(status.status,'UNVERIFIED')
        self.assertIsNone(verdict)
    def test_developer_cannot_issue_qa_verdict(self):
        status,_=self.check(qa=self.dev)
        self.assertEqual(status.status,'UNVERIFIED')
    def test_wrong_tree_or_dirty_checkout(self):
        for update in ({'actual_tree':'other'}, {'checkout_clean':False}):
            with self.subTest(update=update):
                status,_=self.check(**update)
                self.assertEqual(status.status,'UNVERIFIED')
    def test_criteria_gap_or_modified_qa_test(self):
        for update in ({'covered_criteria':('AC1',)}, {'actual_test_hashes':{'tests/qa_owned.py':'b'*64}}):
            status,_=self.check(**update)
            self.assertEqual(status.status,'UNVERIFIED')
    def test_waiver_is_not_verification(self):
        status,_=self.check(human_waiver=True)
        self.assertEqual(status.status,'UNVERIFIED')
    def test_three_rounds_blocked(self):
        status,_=self.check(fix_round=3)
        self.assertEqual(status.status,'BLOCKED')

if __name__=='__main__': unittest.main()
