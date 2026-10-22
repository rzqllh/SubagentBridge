# Simpul — Compatibility and limitations

Public name: **Simpul**. Repository and technical identifiers remain `rzqllh/SubagentBridge`, `subagentbridge` and `SUBAGENTBRIDGE_*`.

## Candidate compatibility (as of 23 October 2026)

| Area | Evidence-supported statement |
| --- | --- |
| Windows | Intended primary platform; 21 October candidate report cites Windows CI on Python 3.11 and 3.13 |
| Linux | Candidate report cites Ubuntu CI on Python 3.11 and 3.13 |
| Python 3.12 | Declared supported in `pyproject.toml`; no separate 3.12 CI evidence cited in current release report |
| Antigravity IDE | Target MCP host; an end-to-end live IDE workflow is **not independently verified** |
| 9Router | Loopback-only Python adapter and offline tests; prior live authenticated completion returned HTTP 401 |
| Orca | Optional adapter seam, disabled by default; no external runner needed for native modules |
| Production release | **Not published**; PR #2 / PR #3 unmerged |

## Runtime limitations

1. `AUTONOMY: OFF`: this candidate is not a general-purpose unattended coding agent.
2. `submit_goal` records `SUBMITTED` / `PENDING` state in process memory; it does not run a full worker pipeline in that handler.
3. D-01 `RISK_ACCEPTED_SAME_IDENTITY` does **not** isolate untrusted workers or test code from user-owned secrets.
4. D-03 `CHAT_APPROVAL` and broker token unit tests do **not** prove authenticated human intent against malicious same-user workers.
5. D-02 client loopback restrictions do not control any upstream proxy's own egress.
6. E18 red-team, E22 checkout-root containment, and E23 pinned remote checkout require stronger independent proof. Historical E01–E21 test names do not close these gates.
7. SQLite audit/event persistence is not identical to recovery of the MCP server's in-memory run/task registry.
8. Runtime configuration described in older `SUBAGENTBRIDGE_ROUTER_*` examples is not wired through the present server composition call.

See [Project status](SIMPUL_STATUS.md), [API](API_REFERENCE.md) and [Configuration](CONFIGURATION.md).
