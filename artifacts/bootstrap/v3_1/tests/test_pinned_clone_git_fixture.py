"""Local-Git fixture only: no network, no push to user's repository.

This does NOT prove GitHub availability, Windows behavior, or verifier independence.
"""
from __future__ import annotations
import pathlib
import subprocess
import tempfile
import unittest


def git(*args, cwd=None):
    p=subprocess.run(['git', *map(str,args)],cwd=cwd,text=True,capture_output=True, timeout=15)
    if p.returncode:raise RuntimeError(f'git {args} failed: {p.stderr.strip()}')
    return p.stdout.strip()

class PinnedGitBranchFixture(unittest.TestCase):
    def test_clone_branch_pin_and_changed_branch_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            base=pathlib.Path(td)
            src=base/'origin-repo';src.mkdir()
            git('init','-q',cwd=src)
            git('config','user.name','Xyeena Fixture',cwd=src)
            git('config','user.email','fixture@example.invalid',cwd=src)
            git('checkout','-b','feat/00-baseline-and-contracts',cwd=src)
            (src/'README.md').write_text('one\n')
            git('add','README.md',cwd=src)
            git('commit','-q','-m','initial',cwd=src)
            pinned=git('rev-parse','HEAD',cwd=src)
            c1=base/'clone1'
            git('clone','-q','--no-checkout','--single-branch','--branch','feat/00-baseline-and-contracts',src,c1)
            remote=git('rev-parse','refs/remotes/origin/feat/00-baseline-and-contracts',cwd=c1)
            self.assertEqual(remote,pinned)
            git('checkout','--detach',pinned,cwd=c1)
            self.assertEqual(git('rev-parse','HEAD',cwd=c1),pinned)
            self.assertEqual(git('status','--porcelain',cwd=c1),'')
            (src/'README.md').write_text('two\n')
            git('add','README.md',cwd=src)
            git('commit','-q','-m','moved',cwd=src)
            c2=base/'clone2'
            git('clone','-q','--no-checkout','--single-branch','--branch','feat/00-baseline-and-contracts',src,c2)
            newer=git('rev-parse','refs/remotes/origin/feat/00-baseline-and-contracts',cwd=c2)
            self.assertNotEqual(newer,pinned)
            # A verifier MUST report BLOCKED here rather than checking out the new tip.
