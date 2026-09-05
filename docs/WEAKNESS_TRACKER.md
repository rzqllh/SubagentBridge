# Weakness Tracker

Source: source-level review of `antigravity-mcp` (Inferno-Aditya, MIT) on 2026-09-04.
Status values: `todo` / `in-progress` / `done` / `wontfix`.

| ID | Weakness | Evidence | Severity | Fix | Status |
|----|----------|----------|----------|-----|--------|
| W1 | `wait_for_idle` timeout does not kill the subprocess | `server.py` timeout branch returns without calling `session.kill()` | High (resource leak, silent cost) | Call `kill()` on timeout before returning | todo |
| W2 | No automated retry on subagent failure | `manager.py Session._run` sets `status="error"` on non-zero exit, no retry path | High | `RetryPolicy` wrapper, bounded retries + backoff | todo |
| W3 | `apply_code_fix` boundary check falls through when zero workspaces registered | Code comment: "If no workspaces are registered yet, fall through (best-effort)" | Medium (security) | Hard-reject instead of fallthrough | todo |
| W4 | "Human-in-the-Loop safety intercepts" advertised but not implemented | No approve/reject tool exists anywhere in `server.py`; `skip_permissions` defaults to `True` | Medium (trust/expectation gap) | Real `PendingActionQueue` + `approve_action`/`reject_action` tools | todo |
| W5 | Token usage silently reports 0 for sessions that crash before a `result` event | `get_usage()` docstring/comment acknowledges this | Low | Estimate from partial `tool_call`/`text` events, or flag as `"incomplete"` instead of `0` | todo |
| W6 | Only `agy` and `claude` runners exist; no GPT-5.6 or DeepSeek support | `runners/__init__.py` registry | Feature gap, not a bug | New `gpt_runner.py` / `deepseek_runner.py` + wrapper CLIs | todo |
| W7 | No remote/distributed execution | `asyncio.create_subprocess_exec` is always local | Known, accepted for v1 | Out of scope — documented in PRD non-goals | wontfix (v1) |
| W8 | Claude runner's schema-injection uses fragile `cmd.index("-p")` lookup | `runners/claude_runner.py` | Low (code smell) | Track the message arg index explicitly instead of searching for it | todo |

## Priority Order for v1

1. W1 (timeout-kill) — smallest change, highest silent-cost impact
2. W2 (retry)
3. W3 (boundary check)
4. W4 (real HITL)
5. W6 (new runners)
6. W5, W8 — nice-to-have cleanups
