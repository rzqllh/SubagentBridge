"""Developer-owned regression; cannot replace independent QA adjudication."""
import hashlib
import tempfile
from pathlib import Path
import unittest

from subagentbridge.qa.test_pins import (
    QaTestIntegrityError, validate_qa_test_path, verify_local_test_pins,
)
from subagentbridge.qa.adjudication import QaEvidenceGate
from subagentbridge.domain.registry import IdentityRegistry, ReceiptIssuerRegistry


class QaTestPinTests(unittest.TestCase):
    def test_valid_local_hash_and_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'tests').mkdir()
            file = root/'tests'/'owner_test.py'
            file.write_bytes(b'pass\n')
            pinned = {'tests/owner_test.py':hashlib.sha256(file.read_bytes()).hexdigest()}
            self.assertEqual(verify_local_test_pins(root,pinned), pinned)
            file.write_bytes(b'changed\n')
            with self.assertRaises(QaTestIntegrityError):
                verify_local_test_pins(root,pinned)

    def test_traversal_windows_drive_empty_parts_and_alias_denied(self):
        for path in ('tests/../outside','tests\\one.py','/tests/file.py',
                     'tests//one.py','tests/./one.py', 'tests/C:/one.py',
                     'tests/one.py/../two.py','other/x.py','tests/'):
            with self.subTest(path=path),self.assertRaises(QaTestIntegrityError):
                validate_qa_test_path(path)
        with self.assertRaises(ValueError):
            QaEvidenceGate(ReceiptIssuerRegistry(IdentityRegistry()),
                frozen_criteria=('one',),qa_test_hashes={'tests/../outside':'a'*64})

    def test_symlink_to_external_test_fails_even_when_hash_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'tests').mkdir()
            outside = root/'outside.py'
            outside.write_text('pass')
            link = root/'tests'/'alias.py'
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest('test symlink creation unavailable')
            with self.assertRaises(QaTestIntegrityError):
                verify_local_test_pins(root,{'tests/alias.py':hashlib.sha256(b'pass').hexdigest()})

    def test_oversized_file_rejected_before_digest_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'tests').mkdir()
            (root/'tests'/'big.py').write_bytes(b'0'*(8*1024*1024+1))
            with self.assertRaises(QaTestIntegrityError):
                verify_local_test_pins(root,{'tests/big.py':'0'*64})

    def test_qa_gate_rejects_unauthenticated_boolean_and_negative_fix_counter(self):
        gate = QaEvidenceGate(ReceiptIssuerRegistry(IdentityRegistry()),
                              frozen_criteria=('ac',),qa_test_hashes={'tests/a.py':'a'*64})
        common = dict(qa=None,evidence=(),covered_criteria=('ac',),
                      actual_test_hashes={'tests/a.py':'a'*64}, task_id='t',
                      dispatch_id='d',expected_tree='tree',actual_tree='tree',
                      checkout_clean=True,fix_round=0)
        for kw in ({'checkout_clean':1},{'fix_round':-1},{'fix_round':True}):
            with self.subTest(kw=kw):
                verdict, record = gate.check(**dict(common,**kw))
                self.assertEqual(verdict.status,'UNVERIFIED')
                self.assertIsNone(record)

if __name__ == '__main__':
    unittest.main()
