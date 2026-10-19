# Test Plan — SubagentBridge (legacy scenarios plus v3.1 contract)

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

## PR-00 v3.1 baseline verification (no production safety claim)

Run `python -B -m unittest discover -s tests -p 'test_*.py' -v` (stdlib, no package installation). `test_bootstrap_documents.py` retains original Team Rules/v2 provenance. `test_bootstrap_v31.py` validates v3.1 pinned artifact bytes independently. `test_legacy_security_gaps.py` and `test_invariants_contract.py` include explicitly labeled `expectedFailure` probes; their unresolved count must be reported as **UNVERIFIED** even when unittest returns exit 0. The test runner is not a production receipt issuer.

An independent verifier must establish SHA/tree identity and clean checkout, construct scenarios from frozen criteria first, capture logs/exit status with the pinned BVE helper, then review the PR diff. External CI results count only after the verifier reads the actual run for that SHA. Linux-only helper tests do not establish Windows behavior. Current package has no verified runner or approval broker; tests of unrelated existing code are not an AG-1 pass.

### Release gates (later PRs, not PR-00)

Use E01–E21 in Plan v3.1: native/no-Orca full journey, negative same-user approval attacks, skills and tool injection, process-tree cleanup, dynamic worker cancellation, idempotent recovery, exact-tree executor receipts, independent QA verdict, budgets and model capability checks. Do not infer `VERIFIED` from a clean unittest/CI exit. T11's legacy `working→idle` expectation is **unsafe**: later recovery must reconcile process ownership and mark uncertainty `RECOVERY_REQUIRED`, not report idle.

**Workflow context:** the exact approved CI file runs only stdlib baseline tests on Ubuntu and Windows (Python 3.11 and 3.13). It does not install `mcp`, execute arbitrary agent workers, or test the finished product.
