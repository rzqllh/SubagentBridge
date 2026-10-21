"""PR-04b partial: exact argv, read-only preapproved local inspection commands.

Cannot be used for autonomous execution. No shell, write, build, test, or arbitrary
repository code. Path-swap and same-identity attacks are NOT isolated. Receipts
are evidence of an ordinary local process, not proof of isolation or trusted QA.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import subprocess
from uuid import uuid4
from subagentbridge.workspaces.scope import ScopedWorkspace

@dataclass(frozen=True, slots=True)
class CommandReceipt:
    receipt_id: str
    task_id: str
    dispatch_id: str
    argv: tuple[str, ...]
    exit_code: int
    stdout_sha256: str
    stderr_sha256: str
    isolation: str
    environment: tuple[str, ...]

class SupervisedReadOnlyExecutor:
    """Supervised only, no autonomous mode regardless of requested flags."""
    ALLOWED = frozenset({('git', 'status', '--porcelain'),
                         ('git', 'rev-parse', 'HEAD'),
                         ('git', 'rev-parse', 'HEAD^{tree}')})

    def __init__(self, root: str | Path):
        self.workspace = ScopedWorkspace(root)

    def read_text(self, relative_path: str) -> str:
        path=self.workspace.require_path(relative_path,must_exist=False)
        if not path.is_file():
            raise PermissionError('regular file required')
        return path.read_text(encoding='utf-8')

    def run_inspection(self, *, task_id: str, dispatch_id: str, argv: tuple[str, ...],
                       human_supervised: bool, autonomous: bool = False,
                       timeout_seconds: int = 10) -> CommandReceipt:
        if autonomous or not human_supervised:
            raise PermissionError('no isolated executor; autonomous and unsupervised runs forbidden')
        if not task_id or not dispatch_id or type(argv) is not tuple or argv not in self.ALLOWED:
            raise PermissionError('command/identity not in exact supervised allowlist')
        if not isinstance(timeout_seconds,int) or not 1 <= timeout_seconds <= 30:
            raise ValueError('timeout must be 1..30s')
        # Only environment keys explicitly supplied. Never inherit the full host environment.
        # Python's subprocess on Windows needs SystemRoot; executable resolution still relies
        # on host PATH and may be spoofed; this remains an untrusted same-identity spike.
        systemroot=os.environ.get('SystemRoot','')
        env={'PATH':os.defpath,'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,
             'GIT_TERMINAL_PROMPT':'0','GIT_OPTIONAL_LOCKS':'0'}
        if os.name == 'nt' and systemroot:
            env['SystemRoot']=systemroot
        result=subprocess.run(argv,cwd=self.workspace.root,env=env,capture_output=True,
                              text=False,stdin=subprocess.DEVNULL,timeout=timeout_seconds,check=False)
        return CommandReceipt(str(uuid4()),task_id,dispatch_id,argv,result.returncode,
                sha256(result.stdout).hexdigest(),sha256(result.stderr).hexdigest(),
                'none',tuple(sorted(env)))
