# Architecture — SubagentBridge

## 1. Component Overview

```
MCP Client (Antigravity IDE / Claude Desktop)
        |  MCP protocol (stdio)
        v
server.py  (FastMCP entry point — tool + resource definitions)
        v
manager.py (AgentManager, Session, RetryPolicy, PendingActionQueue)
        |            |                |
        v            v                v
runners/       storage/          hitl/
(AgentRunner   (SQLiteStore)     (approval gate)
 subclasses)
        v
Local subprocess (agy | claude | gpt_runner wrapper | deepseek_runner wrapper)
```

## 2. What Carries Over From the Reviewed Design (reimplemented, not copied)

- `AgentRunner` abstract interface: `name`, `build_command(message, session, json_schema)`,
  `parse_event(data) -> (kind, payload)`. This contract is the reason new backends don't
  touch `manager.py`.
- Canonical event kinds: `init`, `text`, `tool_call`, `thought`, `result`, `unknown`.
- SQLite-backed session/log persistence (WAL mode), so a server restart doesn't lose state.
- Async subprocess model: each `Session` owns its own `asyncio.subprocess.Process`; multiple
  sessions run genuinely concurrently (this already works well upstream — no change needed).

## 3. Fixes vs. the Reviewed Implementation

| # | Issue | Fix |
|---|---|---|
| 1 | `wait_for_idle` timeout doesn't kill the subprocess | On timeout, call `session.kill()` before returning `{"status":"timeout"}` |
| 2 | No retry on non-zero exit | `RetryPolicy` (max_retries, backoff_seconds) wraps `Session._run`; retries are logged and counted in `get_agent_status` |
| 3 | `apply_code_fix` falls through when no workspace registered | Fallthrough removed — zero registered workspaces = hard rejection |
| 4 | "HITL" was just a boolean (`skip_permissions`) | Real `PendingActionQueue`: a runner can flag an action as pending; primary LLM must call `approve_action`/`reject_action` before it proceeds (see `SECURITY.md`) |

## 4. Design Decision: API-based Runners (GPT-5.6, DeepSeek)

`agy` and `claude` are real local CLIs that speak stream-json natively. GPT-5.6 (Sol/Luna)
and DeepSeek V4 Flash are HTTP APIs with no equivalent local headless CLI shipped by their
vendors.

**Decision:** rather than changing `manager.py`'s subprocess-only execution model, ship a thin
**wrapper CLI** per API backend (`wrappers/gpt_wrapper.py`, `wrappers/deepseek_wrapper.py`).
Each wrapper:

1. Accepts the same argv shape as `agy`/`claude` (`-p <message>`, `--output-format
   stream-json`, `--model <slug>`, etc.).
2. Calls the vendor's streaming chat completion API internally.
3. Emits synthetic stream-json lines on stdout matching the canonical event shapes the
   corresponding `AgentRunner.parse_event` expects.

This keeps `manager.py` and the subprocess model completely untouched — a wrapper is just
another local executable from the supervisor's point of view. The runner classes
(`GptRunner`, `DeepSeekRunner`) only need to build the correct argv for their wrapper and
parse whatever JSON shape the wrapper emits (which we control, so we make it match the
existing canonical kinds exactly).

Trade-off: API keys for GPT-5.6 / DeepSeek must be available to the wrapper's environment
(see `SECURITY.md` for handling).

## 5. Non-Goals Reflected in the Design

- No distributed execution — `asyncio.create_subprocess_exec` stays local-machine only.
- No dashboard — status is queryable via `get_agent_status` / `list_agents` / `get_model_usage`.
