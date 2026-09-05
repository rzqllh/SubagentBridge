"""
manager.py — AgentManager, Session, RetryPolicy, PendingActionQueue.

Own implementation. Architecture and fix rationale: docs/ARCHITECTURE.md,
docs/WEAKNESS_TRACKER.md, docs/SECURITY.md.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import json as _json

from .runners.base import AgentRunner, ParsedEvent


def _json_dumps(obj) -> str:
    return _json.dumps(obj, default=str)

MAX_LOG_ENTRIES = 5000
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = (5, 20)  # per retry attempt, indexed by attempt number
DEFAULT_TIMEOUT_SECONDS = 600

DEFAULT_GATED_PATTERNS = (
    "rm -rf",
    "git push --force",
    "git reset --hard",
    "sudo ",
)


class WorkspaceBoundaryError(Exception):
    """Raised when a path falls outside every registered workspace (W3)."""


class SessionNotFoundError(Exception):
    pass


class _ActionRejected(Exception):
    """
    A gated action was explicitly rejected (or timed out awaiting approval).
    Deliberately NOT a subclass of _SubprocessFailure: a human rejection must
    never trigger the automatic retry policy — retrying would mean redoing
    the exact action a human just said no to, which defeats HITL entirely.
    """


@dataclass
class PendingAction:
    action_id: str
    session_id: str
    description: str
    raw_tool_call: dict
    created_at: float = field(default_factory=time.time)
    resolved: bool = False
    approved: Optional[bool] = None
    reason: Optional[str] = None


class PendingActionQueue:
    """
    Real HITL gate (fixes W4 — upstream's `skip_permissions` was a boolean
    with no actual approval mechanism behind it).
    """

    def __init__(self, store=None) -> None:
        self._actions: dict[str, PendingAction] = {}
        self._resolved_events: dict[str, asyncio.Event] = {}
        self.store = store  # optional SQLiteStore-like object (duck-typed)

    def _persist(self, action: PendingAction) -> None:
        if self.store is None:
            return
        self.store.upsert_pending_action({
            "action_id": action.action_id,
            "session_id": action.session_id,
            "description": action.description,
            "raw_tool_call_json": _json_dumps(action.raw_tool_call),
            "created_at": action.created_at,
            "resolved": int(action.resolved),
            "approved": None if action.approved is None else int(action.approved),
            "reason": action.reason,
        })

    def is_gated(self, tool_call: dict) -> bool:
        text = str(tool_call.get("command", "")) + " " + str(tool_call.get("path", ""))
        text_lower = text.lower()
        if any(p in text_lower for p in DEFAULT_GATED_PATTERNS):
            return True
        return bool(tool_call.get("_force_gate"))

    def enqueue(self, session_id: str, tool_call: dict) -> PendingAction:
        action_id = str(uuid.uuid4())
        action = PendingAction(
            action_id=action_id,
            session_id=session_id,
            description=tool_call.get("command") or tool_call.get("path") or "unknown action",
            raw_tool_call=tool_call,
        )
        self._actions[action_id] = action
        self._resolved_events[action_id] = asyncio.Event()
        self._persist(action)
        return action

    async def wait_for_resolution(self, action_id: str, timeout: float) -> PendingAction:
        event = self._resolved_events.get(action_id)
        if event is None:
            raise KeyError(f"no such pending action: {action_id}")
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass  # caller decides what "still pending" means for its flow
        return self._actions[action_id]

    def resolve(self, action_id: str, *, approved: bool, reason: Optional[str] = None) -> PendingAction:
        action = self._actions.get(action_id)
        if action is None:
            raise KeyError(f"no such pending action: {action_id}")
        action.resolved = True
        action.approved = approved
        action.reason = reason
        self._resolved_events[action_id].set()
        self._persist(action)
        return action

    def list_pending(self, session_id: Optional[str] = None) -> list[PendingAction]:
        return [
            a for a in self._actions.values()
            if not a.resolved and (session_id is None or a.session_id == session_id)
        ]


@dataclass
class Session:
    session_id: str
    workspace_path: str
    runner: AgentRunner
    model: Optional[str] = None
    agent_type: Optional[str] = None
    reasoning_effort: Optional[str] = None
    skip_permissions: bool = True
    hitl_enabled: bool = True

    status: str = "idle"          # idle | working | done | error | timeout | killed
    retry_count: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    last_error: Optional[str] = None
    log: list[dict] = field(default_factory=list)
    cursor: int = 0
    pending_action_id: Optional[str] = None
    token_usage: dict = field(default_factory=lambda: {"input": 0, "output": 0})

    _process: Optional[asyncio.subprocess.Process] = field(default=None, repr=False)
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def append_log(self, entry: dict) -> None:
        self.log.append(entry)
        if len(self.log) > MAX_LOG_ENTRIES:
            # Drop the oldest 25% rather than trimming one at a time.
            cutoff = MAX_LOG_ENTRIES // 4
            del self.log[:cutoff]
            self.cursor = max(0, self.cursor - cutoff)

    async def kill(self, reason: str = "killed") -> None:
        """
        Guarantee the OS process is gone. This is the fix for W1: every path
        that ends a wait (timeout, explicit kill, shutdown) must call this —
        never just stop watching the process and leave it running.
        """
        if self._process is not None and self._process.returncode is None:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass  # already dead, fine
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self.status = reason


class AgentManager:
    def __init__(
        self,
        pending_actions: Optional[PendingActionQueue] = None,
        store=None,
    ) -> None:
        self.sessions: dict[str, Session] = {}
        self.store = store  # optional SQLiteStore-like object (duck-typed)
        self.pending_actions = pending_actions or PendingActionQueue(store=store)

    def _persist_session(self, session: Session) -> None:
        if self.store is None:
            return
        self.store.upsert_session({
            "session_id": session.session_id,
            "workspace_path": session.workspace_path,
            "runner_name": session.runner.name,
            "model": session.model,
            "agent_type": session.agent_type,
            "reasoning_effort": session.reasoning_effort,
            "skip_permissions": int(session.skip_permissions),
            "hitl_enabled": int(session.hitl_enabled),
            "status": session.status,
            "retry_count": session.retry_count,
            "max_retries": session.max_retries,
            "last_error": session.last_error,
            "cursor": session.cursor,
            "pending_action_id": session.pending_action_id,
            "token_usage_json": _json_dumps(session.token_usage),
        })

    def rehydrate(self, runner_registry) -> int:
        """
        T11: reload sessions from the store after a restart. Any session
        still 'working' at crash time is reset to 'idle' by the store layer
        (the subprocess it pointed to is gone — see sqlite_store.py). The
        live `runner` object is looked up by name via the registry, never
        deserialized directly.
        """
        if self.store is None:
            return 0
        self.store.reset_stale_working_sessions()
        rows = self.store.load_all_sessions()
        for row in rows:
            runner = runner_registry.get_runner(row["runner_name"])
            session = Session(
                session_id=row["session_id"],
                workspace_path=row["workspace_path"],
                runner=runner,
                model=row["model"],
                agent_type=row["agent_type"],
                reasoning_effort=row["reasoning_effort"],
                skip_permissions=bool(row["skip_permissions"]),
                hitl_enabled=bool(row["hitl_enabled"]),
                status=row["status"],
                retry_count=row["retry_count"],
                max_retries=row["max_retries"],
                last_error=row["last_error"],
                cursor=row["cursor"],
                pending_action_id=row["pending_action_id"],
                token_usage=_json.loads(row["token_usage_json"]),
            )
            self.sessions[session.session_id] = session
        return len(rows)

    # ---- Workspace boundary enforcement (fix for W3) ------------------

    def get_all_workspaces(self) -> list[str]:
        return [s.workspace_path for s in self.sessions.values()]

    def check_path_in_workspace(self, filepath: str) -> None:
        """
        Raises WorkspaceBoundaryError unless filepath resolves inside at
        least one registered workspace. Deliberately has NO fallthrough for
        the zero-workspaces case — that was the upstream gap (W3). An empty
        workspace set means "reject everything," not "allow everything."
        """
        workspaces = self.get_all_workspaces()
        if not workspaces:
            raise WorkspaceBoundaryError(
                "no workspaces registered — refusing apply_code_fix "
                "(spawn_agent must be called first)"
            )
        target = Path(filepath).resolve()
        for ws in workspaces:
            try:
                target.relative_to(Path(ws).resolve())
                return
            except ValueError:
                continue
        raise WorkspaceBoundaryError(
            f"{filepath!r} is outside all registered workspaces: {workspaces}"
        )

    # ---- Session lifecycle ---------------------------------------------

    def get_session(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def spawn(
        self,
        session_id: str,
        workspace_path: str,
        runner: AgentRunner,
        **kwargs,
    ) -> Session:
        if session_id in self.sessions:
            raise ValueError(f"session {session_id!r} already exists")
        session = Session(
            session_id=session_id,
            workspace_path=workspace_path,
            runner=runner,
            **kwargs,
        )
        self.sessions[session_id] = session
        self._persist_session(session)
        return session

    async def send_message(self, session_id: str, message: str) -> None:
        session = self.get_session(session_id)
        if session.status == "working":
            raise RuntimeError(f"session {session_id!r} is already working")
        session.status = "working"
        self._persist_session(session)
        session._task = asyncio.create_task(self._run_with_retries(session, message))

    async def _run_with_retries(self, session: Session, message: str) -> None:
        """
        Fix for W2: retries a failed run up to `max_retries` times with
        backoff, and (per SECURITY.md §4) tells the subagent in-prompt that
        this is a retry so it doesn't redo work that already partially
        landed.
        """
        attempt = 0
        current_message = message
        while True:
            is_retry = attempt > 0
            try:
                await self._run_once(session, current_message, is_retry=is_retry)
                self._persist_session(session)  # success — status set to "done" in _run_once
                return
            except _ActionRejected as exc:
                # Never retry a human rejection — respect the decision and
                # stop immediately (fixes a bug found in testing: this used
                # to fall through to the generic retry path below).
                session.last_error = str(exc)
                session.status = "error"
                self._persist_session(session)
                return
            except _SubprocessFailure as exc:
                session.last_error = str(exc)
                if attempt >= session.max_retries:
                    session.status = "error"
                    self._persist_session(session)
                    return
                backoff = DEFAULT_BACKOFF_SECONDS[min(attempt, len(DEFAULT_BACKOFF_SECONDS) - 1)]
                await asyncio.sleep(backoff)
                attempt += 1
                session.retry_count = attempt
                self._persist_session(session)
                last_state = session.log[-1] if session.log else {}
                current_message = (
                    f"{message}\n\n"
                    f"[retry {attempt}/{session.max_retries}] Previous attempt failed: "
                    f"{exc}. Last known state: {last_state}. Do not redo work that "
                    f"already succeeded — check current file state before re-editing."
                )

    async def _run_once(self, session: Session, message: str, *, is_retry: bool) -> None:
        cmd = session.runner.build_command(
            message,
            workspace_path=session.workspace_path,
            model=session.model,
            agent_type=session.agent_type,
            reasoning_effort=session.reasoning_effort,
            skip_permissions=session.skip_permissions,
            is_retry=is_retry,
        )
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=session.workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=session.runner.env() or None,
        )
        session._process = process
        assert process.stdout is not None

        async for raw_line in process.stdout:
            line = raw_line.decode(errors="replace").rstrip("\n")
            if not line:
                continue
            event = session.runner.parse_event(line)
            if event is None:
                continue
            await self._handle_event(session, event)

        returncode = await process.wait()
        if returncode != 0:
            stderr = b""
            if process.stderr is not None:
                stderr = await process.stderr.read()
            raise _SubprocessFailure(
                f"exit code {returncode}: {stderr.decode(errors='replace')[:500]}"
            )
        session.status = "done"

    async def _handle_event(self, session: Session, event: ParsedEvent) -> None:
        payload = dict(event.payload)
        payload["kind"] = event.kind
        session.append_log(payload)
        if self.store is not None:
            self.store.append_log_entry(session.session_id, len(session.log) - 1, payload)

        if event.kind == "result":
            usage = payload.get("usage") or {}
            session.token_usage["input"] += usage.get("input_tokens", 0)
            session.token_usage["output"] += usage.get("output_tokens", 0)
            return

        if event.kind == "tool_call" and session.hitl_enabled:
            if self.pending_actions.is_gated(payload):
                action = self.pending_actions.enqueue(session.session_id, payload)
                session.pending_action_id = action.action_id
                resolved = await self.pending_actions.wait_for_resolution(
                    action.action_id, timeout=DEFAULT_TIMEOUT_SECONDS
                )
                session.pending_action_id = None
                if not resolved.resolved or not resolved.approved:
                    raise _ActionRejected(
                        f"gated action {action.action_id} was rejected or timed out "
                        f"waiting for approval: {resolved.reason}"
                    )

    # ---- wait_for_idle (fix for W1) ------------------------------------

    async def wait_for_idle(self, session_id: str, timeout_seconds: float) -> dict:
        session = self.get_session(session_id)
        deadline = time.monotonic() + timeout_seconds
        while session.status == "working":
            if time.monotonic() >= deadline:
                # THE FIX: guarantee process death before reporting timeout.
                # Upstream returned {"status": "timeout"} here and left the
                # subprocess running — see docs/WEAKNESS_TRACKER.md W1.
                await session.kill(reason="timeout")
                self._persist_session(session)
                return {"status": "timeout", "session_id": session_id}
            await asyncio.sleep(0.25)
        return {"status": session.status, "session_id": session_id}

    async def kill_agent(self, session_id: str) -> str:
        session = self.get_session(session_id)
        await session.kill(reason="killed")
        self._persist_session(session)
        return f"session {session_id!r} killed"

    # ---- apply_code_fix (fix for W3) -----------------------------------

    def apply_code_fix(self, filepath: str, target: str, replacement: str) -> str:
        self.check_path_in_workspace(filepath)  # raises, no fallthrough
        path = Path(filepath)
        content = path.read_text()
        if target not in content:
            raise ValueError(f"target text not found in {filepath}")
        path.write_text(content.replace(target, replacement, 1))
        return f"patched {filepath} (first occurrence of target replaced)"

    # ---- introspection ---------------------------------------------------

    def get_status(self, session_id: str) -> dict:
        s = self.get_session(session_id)
        return {
            "session_id": s.session_id,
            "status": s.status,
            "retry_count": s.retry_count,
            "pending_action_id": s.pending_action_id,
            "last_error": s.last_error,
            "token_usage": s.token_usage,
        }

    def list_agents(self) -> list[dict]:
        return [self.get_status(sid) for sid in self.sessions]

    def get_model_usage(self) -> dict:
        totals = {"input": 0, "output": 0}
        for s in self.sessions.values():
            totals["input"] += s.token_usage["input"]
            totals["output"] += s.token_usage["output"]
        return {"per_session": {sid: s.token_usage for sid, s in self.sessions.items()}, "total": totals}


class _SubprocessFailure(Exception):
    """Internal signal for _run_with_retries — not exposed outside manager.py."""
