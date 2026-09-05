# PRD — SubagentBridge

**Status:** Draft v0.1
**Date:** 2026-09-04
**License:** MIT

## 1. Background

[antigravity-mcp](https://github.com/Inferno-Aditya/antigravity-mcp) by Inferno-Aditya (MIT
License) proved that a primary LLM inside Antigravity IDE (or Claude Desktop) can delegate
implementation work to headless CLI agents (`agy`, `claude`) running as background
subprocesses, coordinated over MCP. A source-level review of that project surfaced four
concrete gaps (see `WEAKNESS_TRACKER.md`) and one missing capability (multi-model runners
beyond `agy`/`claude`).

**SubagentBridge** is an independent, from-scratch implementation of the same pattern,
written by us, crediting Inferno-Aditya's design in `THIRD_PARTY_NOTICES.md`. No code is
forked or copied.

## 2. Problem Statement

Running a single long-lived agentic session in Antigravity IDE for a multi-file task exhausts
context and blocks on synchronous tool calls. There is no first-party mechanism in Antigravity
to reliably delegate implementation work to isolated background agents, recover from their
failures automatically, or route work to non-Google/non-Anthropic models (GPT-5.6, DeepSeek).

## 3. Goals

- G1: Let a primary agent in Antigravity spawn, message, and monitor background coding
  subagents without polling.
- G2: Recover automatically from a subagent crash or hang (bounded retries, guaranteed
  process cleanup) — `antigravity-mcp` does not do this today.
- G3: Support GPT-5.6 (Sol/Luna) and DeepSeek V4 Flash as first-class runners, not just
  `agy`/`claude`.
- G4: Provide a real Human-in-the-Loop approval gate for destructive actions — not just a
  boolean flag that defaults to "skip everything."
- G5: Keep the MCP tool surface stable enough that existing skills written for
  `antigravity-mcp`'s tool names mostly still work (`spawn_agent`, `wait_for_idle`, etc.).

## 4. Non-Goals (v1)

- Remote/distributed execution (SSH, Docker workers) — local-only, same as upstream.
- A web dashboard — CLI/MCP-tool introspection only for v1.
- Supporting every possible CLI/API backend — only `agy`, `claude`, `gpt-sol`/`gpt-luna`,
  `deepseek-v4-flash` for v1.

## 5. Target User

Just the author, for now. Single-machine, single-user, local dev workflow inside Antigravity
IDE.

## 6. Success Criteria

- A subagent that hangs past its timeout is actually killed (verified in test, not just
  reported as `"status": "timeout"`).
- A subagent that exits non-zero is retried up to N times before being surfaced as a hard
  failure.
- A destructive tool call (file write outside a narrow allowlist, `rm`, force-push, etc.)
  from a subagent is held for explicit approval before executing, with a real
  `approve_action` / `reject_action` tool pair.
- A new runner (GPT-5.6 Sol via API) can be added by implementing exactly two methods
  (`build_command`, `parse_event`) with no changes to `manager.py`.
- `apply_code_fix` rejects any path when zero workspaces are registered, instead of falling
  through unchecked.

## 7. Scope (v1 — Full)

1. Port the core session/runner/storage architecture (own implementation).
2. Fix: timeout no longer leaves an orphaned process (`Session.kill()` called on timeout).
3. Fix: bounded auto-retry with backoff on non-zero exit.
4. Fix: `apply_code_fix` hard-fails (not best-effort fallthrough) when no workspace is
   registered.
5. New: real HITL — `pending_action` queue + `approve_action`/`reject_action` MCP tools,
   gating a configurable set of dangerous operations.
6. New: `gpt_runner.py` (GPT-5.6 Sol/Luna via OpenAI-compatible API) and
   `deepseek_runner.py` (DeepSeek V4 Flash via its API), wrapped as local subprocess-shaped
   CLIs so `manager.py` doesn't need to know the difference (see `ARCHITECTURE.md` §4).

## 8. Open Decisions

- Retry count/backoff defaults (proposed: 2 retries, exponential backoff 5s/20s).
- Exact allowlist of "dangerous" operations that require HITL approval (proposed default in
  `SECURITY.md`).

## 9. References

- `ARCHITECTURE.md`, `WEAKNESS_TRACKER.md`, `API_REFERENCE.md`, `RUNNER_SPEC.md`,
  `SECURITY.md`, `TEST_PLAN.md`, `THIRD_PARTY_NOTICES.md`
