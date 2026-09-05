"""
runners/base.py — AgentRunner interface.

Every backend (agy, claude, gpt_sol, deepseek) implements this contract.
manager.py only ever talks to this interface — adding a new backend never
requires touching manager.py. See docs/RUNNER_SPEC.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# Canonical event kinds every runner must normalize its output into.
EVENT_KINDS = frozenset({"init", "text", "tool_call", "thought", "result", "unknown"})


@dataclass
class ParsedEvent:
    """Normalized event yielded by AgentRunner.parse_event()."""
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            # Unknown backend-specific event kinds are coerced rather than
            # raising, so one noisy backend can't crash the session loop.
            self.payload["_raw_kind"] = self.kind
            self.kind = "unknown"


class AgentRunner(ABC):
    """
    Base class for all subagent backends.

    Implementations must be stateless w.r.t. individual sessions — all
    per-session state (cwd, history, retry count) lives on the Session object
    in manager.py, not on the runner instance. A single runner instance is
    shared across every session that uses that backend.
    """

    #: Short slug used in spawn_agent(runner=...) and in logs/DB rows.
    name: str = "base"

    #: Whether this backend requires a locally installed + authenticated CLI
    #: (agy, claude) vs. being a pure API wrapper (gpt_sol, deepseek).
    requires_local_cli: bool = True

    @abstractmethod
    def build_command(
        self,
        message: str,
        *,
        workspace_path: str,
        model: Optional[str] = None,
        agent_type: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        skip_permissions: bool = True,
        json_schema: Optional[dict] = None,
        is_retry: bool = False,
        retry_context: Optional[str] = None,
    ) -> list[str]:
        """
        Return the full argv (as a list, never a shell string — no shell=True
        anywhere in this codebase) to launch this backend for one turn.

        `is_retry` / `retry_context` implement SECURITY.md §4: a retried
        prompt must tell the subagent it's a retry and what the last known
        state was, so it doesn't blindly redo work that already partially
        succeeded.
        """
        raise NotImplementedError

    @abstractmethod
    def parse_event(self, raw_line: str) -> Optional[ParsedEvent]:
        """
        Parse one line of the subprocess's stdout into a ParsedEvent.

        Return None for lines that carry no meaningful event (blank lines,
        partial/incomplete JSON that should be buffered by the caller, etc.).
        Must never raise on malformed input — return an `unknown` event
        instead, so one bad line can't kill the session's read loop.
        """
        raise NotImplementedError

    def env(self) -> dict[str, str]:
        """
        Extra environment variables this backend's subprocess needs (e.g. API
        keys for wrapper-based runners). Base implementation returns {}.
        Per SECURITY.md §3: never derive these from tool parameters, only
        from the server's own environment.
        """
        return {}

    def redact(self, text: str) -> str:
        """
        Redact secret material before it's persisted to logs/SQLite. Runners
        that hold no secrets (agy, claude) can use the no-op base version;
        API-key-backed runners must override this.
        """
        return text
