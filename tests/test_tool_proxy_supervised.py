import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subagentbridge.execution.tool_executor import SupervisedReadOnlyExecutor

class ReadOnlyToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'safe.txt').write_text('hello')
        self.ex=SupervisedReadOnlyExecutor(self.root)

    def test_read_scoped(self):
        self.assertEqual(self.ex.read_text('safe.txt'),'hello')
        with self.assertRaises(PermissionError): self.ex.read_text('../other')

    def test_symlink_escape_rejected(self):
        outside=Path(self.tmp.name).parent/'sandbox-escape-probe.txt'
        p=self.root/'link'
        try: p.symlink_to(outside)
        except (NotImplementedError,OSError): self.skipTest('symlink privilege unavailable')
        with self.assertRaises(PermissionError): self.ex.read_text('link')

    def test_no_shell_or_unauthorized_command_even_supervised(self):
        for argv in (('python','-c','print(1)'),('git','push'),('git','status','--porcelain','--untracked-files=no')):
            with self.assertRaises(PermissionError):
                self.ex.run_inspection(task_id='t',dispatch_id='d',argv=argv,human_supervised=True)

    def test_never_autonomous_or_unsupervised(self):
        for auto,sup in ((True,True),(False,False),(True,False)):
            with self.assertRaises(PermissionError):
                self.ex.run_inspection(task_id='t',dispatch_id='d',argv=('git','status','--porcelain'),
                                       human_supervised=sup,autonomous=auto)

    @patch('subagentbridge.execution.tool_executor.supervised.subprocess.run')
    def test_scrubbed_environment_and_claim_limits(self,run):
        run.return_value.returncode=0
        run.return_value.stdout=b'out'
        run.return_value.stderr=b''
        with patch.dict(os.environ,{'OPENAI_API_KEY':'SENTINEL-SECRET'}):
            receipt=self.ex.run_inspection(task_id='t',dispatch_id='d',argv=('git','status','--porcelain'),
                                           human_supervised=True)
        self.assertEqual(receipt.isolation,'none')
        self.assertEqual(receipt.exit_code,0)
        self.assertEqual(len(receipt.stdout_sha256),64)
        env=run.call_args.kwargs['env']
        self.assertNotIn('OPENAI_API_KEY',env)
        self.assertNotIn('SENTINEL-SECRET',str(env))
        self.assertFalse(run.call_args.kwargs['shell'] if 'shell' in run.call_args.kwargs else False)

if __name__=='__main__': unittest.main()
