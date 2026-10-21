"""Developer-owned resource-control checks; supervised executor is NOT isolated."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subagentbridge.execution.tool_executor.supervised import (
    MAX_READ_TEXT_BYTES, SupervisedReadOnlyExecutor,
)

class ReadOnlyBoundsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.ex=SupervisedReadOnlyExecutor(self.root)

    def test_exact_size_accepted_and_overlimit_rejected(self):
        p=self.root/'big.txt'
        p.write_bytes(b'a' * MAX_READ_TEXT_BYTES)
        self.assertEqual(len(self.ex.read_text('big.txt')), MAX_READ_TEXT_BYTES)
        p.write_bytes(b'a' * (MAX_READ_TEXT_BYTES + 1))
        with self.assertRaises(PermissionError):
            self.ex.read_text('big.txt')

    def test_invalid_utf8_is_denied(self):
        (self.root/'bytes.txt').write_bytes(b'\xff\xfe')
        with self.assertRaises(PermissionError):
            self.ex.read_text('bytes.txt')

    def test_timeout_boolean_cannot_bypass_validated_integer(self):
        with self.assertRaises(ValueError):
            self.ex.run_inspection(task_id='t',dispatch_id='d',
                argv=('git','status','--porcelain'),human_supervised=True,timeout_seconds=True)

    @patch('subagentbridge.execution.tool_executor.supervised.subprocess.run')
    def test_empty_or_wrong_identity_type_never_launches(self, runner):
        for task_id,dispatch_id in ((True,'d'), ('t',False), ('','d'), ('t','')):
            with self.subTest(task_id=task_id,dispatch_id=dispatch_id),self.assertRaises(PermissionError):
                self.ex.run_inspection(task_id=task_id,dispatch_id=dispatch_id,
                    argv=('git','status','--porcelain'),human_supervised=True)
        runner.assert_not_called()

if __name__=='__main__':unittest.main()
