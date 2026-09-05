# API Reference — SubagentBridge MCP Tools

Tool names match the reviewed upstream design where behavior is unchanged, so existing
orchestrator skills mostly work without edits. New/changed tools are marked.

| Tool | Purpose | Returns | Change from upstream |
|---|---|---|---|
| `spawn_agent(session_id, workspace_path, model, agent_type, reasoning_effort, skip_permissions, mode, runner)` | Create a background session | Confirmation string | `runner` now also accepts `gpt-sol`, `gpt-luna`, `deepseek-v4-flash` |
| `send_message(session_id, message)` | Queue a prompt | Queue status | unchanged |
| `send_message_with_schema(session_id, message, json_schema)` | Queue a prompt with forced JSON output | Queue status | unchanged |
| `check_inbox(session_id, mode)` | Read session log since cursor | JSON payload | unchanged |
| `wait_for_idle(session_id, timeout_seconds)` | Block until idle/timeout | JSON payload | **on timeout, now kills the subprocess before returning** (W1) |
| `get_agent_status(session_id)` | Session diagnostics | JSON object | now includes `retry_count` and `pending_action_id` (if any) |
| `kill_agent(session_id)` | Force-terminate | Status string | unchanged |
| `list_agents()` | List all sessions | JSON array | unchanged |
| `get_model_usage()` | Aggregate token usage | JSON report | unchanged |
| `apply_code_fix(filepath, target, replacement)` | Surgical find/replace | Result string | **hard-rejects when zero workspaces registered** (W3) |
| `approve_action(action_id)` | **New.** Approve a pending gated action | Status string | new (W4) |
| `reject_action(action_id, reason)` | **New.** Reject a pending gated action | Status string | new (W4) |
| `list_pending_actions()` | **New.** List all actions awaiting approval | JSON array | new (W4) |

## Resources

| Resource URI | Purpose | Change |
|---|---|---|
| `agy://logs/{session_id}` | Raw log stream | unchanged |
| `agy://inbox/{session_id}` | Full message history | unchanged |
| `agy://pending/{session_id}` | **New.** Actions from this session awaiting approval | new (W4) |

## New Runner Values for `spawn_agent(runner=...)`

| Value | Backend | Requires |
|---|---|---|
| `agy` (default) | Google Antigravity CLI | `agy` binary installed + authenticated |
| `claude` | Claude Code CLI | `claude` binary installed + authenticated |
| `gpt-sol` / `gpt-luna` | GPT-5.6 via API, wrapped | `OPENAI_API_KEY` env var |
| `deepseek-v4-flash` | DeepSeek V4 Flash via API, wrapped | `DEEPSEEK_API_KEY` env var |
