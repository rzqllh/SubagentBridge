# Test Plan — SubagentBridge

| Test ID | Target | Scenario | Expected Result |
|---|---|---|---|
| T1 | W1 fix | Spawn agent, send a message that never returns, call `wait_for_idle` with a short timeout | Returns `{"status":"timeout"}` AND the OS process is confirmed dead (no zombie/orphan) |
| T2 | W2 fix | Force a runner to exit non-zero (mock) | Session retries up to configured max, each attempt logged, final status only `error` after retries exhausted |
| T3 | W2 fix | Retry after partial success | Retry prompt includes prior partial state; no duplicate destructive action |
| T4 | W3 fix | Call `apply_code_fix` with zero sessions ever spawned | Hard rejection, not a silent pass-through write |
| T5 | W3 fix | Call `apply_code_fix` with a path outside any registered workspace | Rejected with clear message listing valid workspaces |
| T6 | W4 (HITL) | Subagent issues a gated command (e.g. `rm -rf`) | Action appears in `list_pending_actions()`; does NOT execute until `approve_action` |
| T7 | W4 (HITL) | `reject_action` called | Action is discarded, subagent is informed via inbox |
| T8 | W6 (GPT runner) | `spawn_agent(runner="gpt-sol")` + `send_message` | Wrapper streams valid canonical events; `get_agent_status` shows real token usage |
| T9 | W6 (DeepSeek runner) | Same as T8 for `deepseek-v4-flash` | Same |
| T10 | Concurrency (regression) | Spawn 3 sessions, message all 3, `wait_for_idle` each | All 3 run genuinely concurrently (verified via timestamps), no cross-session interference |
| T11 | Persistence (regression) | Kill server mid-run, restart | Sessions rehydrate from SQLite; any session marked `working` at crash time resets to `idle` |
| T12 | W8 fix | Send `send_message_with_schema` on the claude runner with a message containing the literal substring `-p` | Schema instruction still appended to the correct argv position |
| T13 | W1 × W2 interaction (found during implementation) | Caller's `wait_for_idle(timeout_seconds=N)` is shorter than the total retry backoff window (`sum(DEFAULT_BACKOFF_SECONDS)`) | `wait_for_idle` correctly times out and kills the in-progress retry cycle rather than hanging — but document this clearly: a short caller timeout can cut off retries before they exhaust, surfacing `"timeout"` instead of `"error"`/`"done"`. Callers that want retries to fully play out must pass a timeout ≥ worst-case retry time. |

## Out of Scope for v1 Test Plan

- Load testing with >10 concurrent sessions
- Cross-platform (Windows) subprocess signal handling — Linux/macOS only for v1
