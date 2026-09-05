# Security Notes — SubagentBridge

## 1. Human-in-the-Loop (real implementation, addressing W4)

`skip_permissions=True` by default is kept for convenience, but is no longer the only gate.
A configurable **dangerous-operation allowlist** determines which `tool_call` events from a
subagent get queued in `PendingActionQueue` instead of executing immediately:

**Default gated operations (proposed):**
- Shell commands matching `rm -rf`, `git push --force`, `git reset --hard`, `sudo`
- Any file write outside the session's own `workspace_path`
- Any network call to a domain not in an explicit allowlist

The primary LLM must call `approve_action(action_id)` or `reject_action(action_id, reason)`
before a gated action proceeds. `list_pending_actions()` lets it (or the human) see what's
waiting.

This is opt-out per session (`hitl_enabled: bool`, default `True`), not opt-in — the
upstream design effectively defaulted to "off" via `skip_permissions=True` with no real gate
underneath; this fixes that gap (W4).

## 2. Workspace Boundary Enforcement (W3)

`apply_code_fix` must resolve the target path against the set of registered workspaces
(`manager.get_all_workspaces()`). If that set is **empty**, the call is rejected — no
fallthrough. Rationale: an empty workspace set almost certainly means the caller skipped
`spawn_agent`, and silently allowing writes anywhere is a bigger risk than a slightly
stricter error message.

## 3. Secrets Handling for API-backed Runners

- `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` are read from environment variables only — never
  accepted as a tool parameter, never logged, never written into `TEAM_MEMORY.md` or session
  logs.
- Wrapper scripts (`wrappers/*.py`) must redact any key material before printing anything to
  stdout (which is captured verbatim into session logs and SQLite).

## 4. Retry Policy Safety (W2)

Retries must not resend a prompt that already partially succeeded (e.g. already wrote files)
without the subagent knowing — each retry attempt is told in-prompt that this is a retry and
what the previous attempt's last known state was (from `full_log`), to avoid duplicate/
conflicting edits.

## 5. Process Cleanup (W1)

Every path that ends a session's wait (`timeout`, `kill_agent`, server shutdown) must
guarantee the underlying OS process is terminated. No code path should return control to the
caller while a subprocess is still alive but untracked.
