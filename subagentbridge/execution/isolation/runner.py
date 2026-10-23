"""subagentbridge/execution/isolation/runner.py — Isolated execution runner (INV-07, D-01).

Runs commands in an isolated execution directory with sanitized environment variables,
preventing leaking of approval tokens or cross-dispatch state.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import signal
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


def _is_sensitive_key(k: str) -> bool:
    upper = k.upper()
    return (
        k in _SENSITIVE_ENV_KEYS
        or upper in _SENSITIVE_ENV_KEYS
        or upper.startswith("SECRET_")
        or "BROKER_SECRET" in upper
        or "API_KEY" in upper
        or "GITHUB_TOKEN" in upper
    )


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

    def _terminate_process_tree(self, proc: subprocess.Popen) -> None:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            else:
                killpg = getattr(os, "killpg", None)
                getpgid = getattr(os, "getpgid", None)
                sig = getattr(signal, "SIGKILL", getattr(signal, "SIGTERM", 15))
                if callable(killpg) and callable(getpgid):
                    killpg(getpgid(proc.pid), sig)
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass

    def run_isolated(
        self,
        argv: Sequence[str],
        *,
        timeout_seconds: int = 30,
        extra_env: Mapping[str, str] | None = None,
    ) -> ExecutionResult:
        if not argv:
            raise ValueError("empty argv cannot be executed")

        # Sanitize environment: strip sensitive keys from base env and extra_env
        clean_env = {
            k: v for k, v in os.environ.items()
            if not _is_sensitive_key(k)
        }
        if extra_env:
            for k, v in extra_env.items():
                if not _is_sensitive_key(k):
                    clean_env[k] = v

        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        else:
            kwargs["start_new_session"] = True

        proc = subprocess.Popen(
            list(argv),
            cwd=str(self.workspace_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=clean_env,
            shell=False,
            **kwargs,
        )

        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            self._terminate_process_tree(proc)
            proc.communicate()
            raise

        stdout_sha = sha256(stdout_bytes).hexdigest()
        stderr_sha = sha256(stderr_bytes).hexdigest()
        out_text = stdout_bytes.decode("utf-8", errors="replace")

        return ExecutionResult(
            argv=tuple(argv),
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout_sha256=stdout_sha,
            stderr_sha256=stderr_sha,
            output_text=out_text,
            confinement=self.confinement,
        )
