"""subagentbridge/execution/isolation/runner.py — Isolated execution runner (INV-07, D-01).

Runs commands in an isolated execution directory with sanitized environment variables,
preventing leaking of approval tokens or cross-dispatch state.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import subprocess
from typing import Mapping, Sequence

_SENSITIVE_ENV_KEYS = frozenset({
    "SUBAGENTBRIDGE_BROKER_SECRET",
    "SUBAGENTBRIDGE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "NINE_ROUTER_API_KEY",
})


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout_sha256: str
    stderr_sha256: str
    output_text: str
    confinement: str


class IsolatedExecutionRunner:
    """Executes commands inside an isolated directory with sanitized environment."""

    def __init__(self, workspace_path: str | Path, *, confinement: str = "RISK_ACCEPTED_SAME_IDENTITY"):
        self.workspace_path = Path(workspace_path).resolve()
        if not self.workspace_path.exists():
            raise FileNotFoundError(f"workspace path does not exist: {self.workspace_path}")
        self.confinement = confinement

    def run_isolated(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: int = 30,
        extra_env: Mapping[str, str] | None = None,
    ) -> ExecutionResult:
        if not argv:
            raise ValueError("empty argv cannot be executed")

        # Sanitize environment
        clean_env = {
            k: v for k, v in os.environ.items()
            if k not in _SENSITIVE_ENV_KEYS and not k.startswith("SECRET_")
        }
        if extra_env:
            clean_env.update(extra_env)

        proc = subprocess.run(
            list(argv),
            cwd=str(self.workspace_path),
            capture_output=True,
            timeout=timeout_seconds,
            env=clean_env,
            shell=False,
        )

        stdout_sha = sha256(proc.stdout).hexdigest()
        stderr_sha = sha256(proc.stderr).hexdigest()
        out_text = proc.stdout.decode("utf-8", errors="replace")

        return ExecutionResult(
            argv=tuple(argv),
            exit_code=proc.returncode,
            stdout_sha256=stdout_sha,
            stderr_sha256=stderr_sha,
            output_text=out_text,
            confinement=self.confinement,
        )
