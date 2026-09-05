---
name: subagentbridge
description: Delegate bounded coding work to isolated background subagents through the SubagentBridge MCP server. Use when a task benefits from parallel implementation, an independent coding pass, long-running delegated work, or explicit subagent lifecycle and usage tracking. On Antigravity, bootstrap the global MCP runtime once and then reuse it from any workspace.
license: MIT
compatibility: Antigravity IDE/CLI; Python 3.10+; agy CLI 1.1.10+ for the agy runner
metadata:
  author: rzqllh
  repository: https://github.com/rzqllh/SubagentBridge
---

# SubagentBridge

Use SubagentBridge as the orchestration layer for delegated coding work. The skill is the portable agent-facing layer; the Python MCP server is the machine-level runtime.

## First use on Antigravity

1. Check whether MCP tools prefixed with `subagentbridge/` are already available.
2. If they are unavailable, run `python scripts/bootstrap.py` from this skill directory.
3. Tell the user to refresh MCP servers in Antigravity after bootstrap completes.
4. Verify with `subagentbridge/list_agents` before delegating work.

The bootstrap installs an isolated runtime under the user's home directory and adds the server to Antigravity's global `~/.gemini/config/mcp_config.json`, so the MCP server is shared across workspaces. Do not create a per-project Python virtual environment for SubagentBridge.

## Before delegation

- Confirm the requested runner exists and is available locally.
- Use the current workspace root as `workspace_path` unless the user specifies another bounded directory.
- Keep delegated tasks scoped and testable.
- Do not claim a subagent completed work until its terminal status and resulting workspace changes are verified.

## Core flow

1. `spawn_agent` with a unique session id, workspace path, and runner.
2. `send_message` with the bounded implementation or investigation task.
3. `wait_for_idle` rather than repeatedly polling status.
4. Inspect status/logs and verify changed files/tests in the workspace.
5. Use follow-up messages only when the existing session context is useful; otherwise spawn a fresh isolated session.

## Safety

Treat SubagentBridge's HITL controls as security-sensitive. Never bypass a pending action merely to make a task finish faster. If the runtime reports an error, timeout, rejected action, or unavailable runner, surface that state rather than pretending the delegated work succeeded.

The current project may mark experimental runtime behavior explicitly. Prefer verified runner/runtime capabilities over README claims when they differ.
