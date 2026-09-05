"""
server.py — FastMCP entry point for SubagentBridge.

Own implementation. Tool contract: docs/API_REFERENCE.md.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import runners as runner_registry
from .manager import (
    AgentManager,
    PendingActionQueue,
    SessionNotFoundError,
    WorkspaceBoundaryError,
)
from .storage.sqlite_store import SQLiteStore

DB_PATH = os.environ.get(
    "SUBAGENTBRIDGE_DB_PATH", str(Path.home() / ".subagentbridge" / "sessions.db")
)
DEFAULT_MAX_RETRIES = int(os.environ.get("SUBAGENTBRIDGE_MAX_RETRIES", "2"))
DEFAULT_TIMEOUT_S = float(os.environ.get("SUBAGENTBRIDGE_DEFAULT_TIMEOUT_S", "600"))

mcp = FastMCP("subagentbridge")

_store = SQLiteStore(DB_PATH)
_pending = PendingActionQueue(store=_store)
_manager = AgentManager(pending_actions=_pending, store=_store)

# NOTE: real backends (agy, claude, gpt_sol, deepseek) register themselves
# into `runner_registry` in M3 — see docs/PRD.md. Rehydration below will only
# find sessions whose runner_name is already registered by that point.
_rehydrated_count = _manager.rehydrate(runner_registry)


@mcp.tool()
def spawn_agent(
    session_id: str,
    workspace_path: str,
    runner: str = "agy",
    model: str | None = None,
    agent_type: str | None = None,
    reasoning_effort: str | None = None,
    skip_permissions: bool = True,
    hitl_enabled: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """Create a new background subagent session on the given backend runner."""
    try:
        runner_obj = runner_registry.get_runner(runner)
    except KeyError as exc:
        return f"error: {exc}"
    try:
        _manager.spawn(
            session_id,
            workspace_path,
            runner_obj,
            model=model,
            agent_type=agent_type,
            reasoning_effort=reasoning_effort,
            skip_permissions=skip_permissions,
            hitl_enabled=hitl_enabled,
            max_retries=max_retries,
        )
    except ValueError as exc:
        return f"error: {exc}"
    return f"spawned session {session_id!r} on runner {runner!r}"


@mcp.tool()
async def send_message(session_id: str, message: str) -> str:
    """Queue a prompt for a session. Fails if the session is already working."""
    try:
        await _manager.send_message(session_id, message)
    except (SessionNotFoundError, RuntimeError) as exc:
        return f"error: {exc}"
    return f"message queued for session {session_id!r}"


@mcp.tool()
async def wait_for_idle(session_id: str, timeout_seconds: float = DEFAULT_TIMEOUT_S) -> dict:
    """
    Block until the session is idle/done/error, or the timeout elapses.
    On timeout, the underlying subprocess is guaranteed killed (fix for W1)
    before this returns — no orphaned process is ever left running.
    """
    try:
        return await _manager.wait_for_idle(session_id, timeout_seconds)
    except SessionNotFoundError as exc:
        return {"status": "error", "error": str(exc)}


@mcp.tool()
def get_agent_status(session_id: str) -> dict:
    """Session diagnostics, including retry_count and pending_action_id (W2/W4)."""
    try:
        return _manager.get_status(session_id)
    except SessionNotFoundError as exc:
        return {"error": str(exc)}


@mcp.tool()
def list_agents() -> list[dict]:
    """List diagnostics for every known session."""
    return _manager.list_agents()


@mcp.tool()
def get_model_usage() -> dict:
    """Aggregate token usage across all sessions."""
    return _manager.get_model_usage()


@mcp.tool()
async def kill_agent(session_id: str) -> str:
    """Force-terminate a session's subprocess immediately."""
    try:
        return await _manager.kill_agent(session_id)
    except SessionNotFoundError as exc:
        return f"error: {exc}"


@mcp.tool()
def apply_code_fix(filepath: str, target: str, replacement: str) -> str:
    """
    Surgical find/replace on a file. Hard-rejects if no workspace has ever
    been registered, or if filepath falls outside every registered
    workspace (fix for W3 — no silent fallthrough).
    """
    try:
        return _manager.apply_code_fix(filepath, target, replacement)
    except (WorkspaceBoundaryError, ValueError, FileNotFoundError) as exc:
        return f"error: {exc}"


@mcp.tool()
def approve_action(action_id: str) -> str:
    """Approve a pending gated action so the waiting subagent can proceed (W4)."""
    try:
        _pending.resolve(action_id, approved=True)
    except KeyError as exc:
        return f"error: {exc}"
    return f"action {action_id!r} approved"


@mcp.tool()
def reject_action(action_id: str, reason: str = "") -> str:
    """
    Reject a pending gated action. The session is stopped with status
    'error' and is NOT retried automatically — see manager.py _ActionRejected
    (a bug caught in testing: rejections used to fall into the generic retry
    path and could re-attempt the exact action a human just vetoed).
    """
    try:
        _pending.resolve(action_id, approved=False, reason=reason)
    except KeyError as exc:
        return f"error: {exc}"
    return f"action {action_id!r} rejected"


@mcp.tool()
def list_pending_actions(session_id: str | None = None) -> list[dict]:
    """List all actions currently awaiting human approval (optionally filtered by session)."""
    return [
        {
            "action_id": a.action_id,
            "session_id": a.session_id,
            "description": a.description,
            "created_at": a.created_at,
        }
        for a in _pending.list_pending(session_id)
    ]


@mcp.resource("agy://logs/{session_id}")
def get_logs(session_id: str) -> str:
    """Raw log stream for a session."""
    session = _manager.get_session(session_id)
    return json.dumps(session.log, default=str)


@mcp.resource("agy://pending/{session_id}")
def get_pending_for_session(session_id: str) -> str:
    """Actions from this session currently awaiting approval (new, W4)."""
    actions = _pending.list_pending(session_id)
    return json.dumps([a.__dict__ for a in actions], default=str)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
