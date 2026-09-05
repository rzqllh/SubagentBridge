# SubagentBridge

An MCP server that lets a primary agent inside **Antigravity IDE** delegate
coding tasks to background subagents across multiple model backends — with
automatic crash recovery, guaranteed process cleanup, and a real
Human-in-the-Loop approval gate for destructive actions.

Architecturally inspired by [antigravity-mcp](https://github.com/Inferno-Aditya/antigravity-mcp)
by Inferno-Aditya (MIT License). No code from that project is reused directly —
see `THIRD_PARTY_NOTICES.md` for full attribution.

## Why

A review of antigravity-mcp's source found it didn't fully deliver on its own
docs: timed-out subagents were left running, failed runs weren't retried, a
workspace-boundary check could silently fall through, and the advertised
"Human-in-the-Loop" safety gate didn't actually exist in code. SubagentBridge
fixes all four and adds first-class support for GPT-5.6 (Sol/Luna) and
DeepSeek V4 Flash as additional runners. Full rationale in `docs/PRD.md`.

## Status

🚧 Planning stage — see `docs/` for PRD, architecture, weakness tracker, API
reference, runner spec, security notes, and test plan. Implementation not yet
started.

## Planned Tools

| Tool | Purpose |
|---|---|
| `spawn_agent` | Start a new background subagent session |
| `send_message` | Send a follow-up instruction to a session |
| `wait_for_idle` | Block until a session finishes or times out (kills the process on timeout) |
| `get_agent_status` / `list_agents` | Inspect running/finished sessions |
| `get_model_usage` | Token/cost accounting per session |
| `apply_code_fix` | Direct surgical find-replace patch, workspace-bounded |
| `kill_agent` | Force-stop a session |
| `approve_action` / `reject_action` | Resolve a pending HITL approval request |

See `docs/API_REFERENCE.md` for full signatures.

## Supported Runners

- `agy` — Antigravity IDE's own agent
- `claude` — Claude Code
- `gpt_sol` — GPT-5.6 Sol/Luna *(planned)*
- `deepseek` — DeepSeek V4 Flash *(planned)*

## Setup (planned)

```bash
pip install -r requirements.txt
```

Add to Antigravity's `mcp_config.json` — see `mcp_config.example.json`.

## License

MIT — see `LICENSE`. Third-party attribution in `THIRD_PARTY_NOTICES.md`.
