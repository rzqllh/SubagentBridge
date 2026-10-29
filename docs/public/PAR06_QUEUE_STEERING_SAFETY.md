# PAR-06 — Supervised queue steering and priority controls

Status: **CODE_PRESENT / CI_PENDING / HOST_E2E_BLOCKED**. Scope: protected-main candidate, not an enterprise authorization proof.

The trusted in-process `TeamManager.steer_task(lead_session_id, dispatch_id, guidance)` appends guidance to the durable queue. The new `reprioritize_task(..., priority)` permits integer priorities from -100 to 100 **only while PENDING**. Both run through `TeamStore.steer_queue_item_once` using SQLite `BEGIN IMMEDIATE`, validating the recorded lead session, team ownership and nonterminal state within the transaction. No in-flight command, execution ticket, workspace or approval payload is rewritten. Concurrent steering is append-only and cancellation cannot be resurrected by stale writes through this path.

Limitations and governance:
- These are **trusted Python APIs**, not independently authenticated human approval endpoints. A caller-supplied lead ID does not prove human identity, and exposing this method directly as model-callable MCP would be unsafe.
- The historical generic `save_queue_item` and `update_queue_status` paths have **not yet** been converted into universal transition guards. This slice does not guarantee linearizability for every legacy queue writer. Full PAR-06 remains OPEN pending end-to-end host integration and broader status-transition audit.
- Steering text is task context, not permission to execute commands. `AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`; E18 #21 and authenticated human gate #22 remain BLOCKED.
- PR CI covers Ubuntu/Windows Python 3.11/3.13, SQLite multi-connection races, cancellation and role denial; no real Antigravity host acceptance is claimed here.

Tracking: [#49](https://github.com/rzqllh/SubagentBridge/issues/49), [epic #43](https://github.com/rzqllh/SubagentBridge/issues/43).
