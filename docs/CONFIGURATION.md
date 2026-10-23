# Simpul — Configuration truth table

Brand: **Simpul**. Technical compatibility: `subagentbridge` and `SUBAGENTBRIDGE_*` remain unchanged.

This is based on the candidate source examined 23 October 2026. **Do not treat design-only settings as wired runtime controls.**

| Setting | Observed use in candidate | Default / note |
| --- | --- | --- |
| `SUBAGENTBRIDGE_DB_PATH` | Read by `subagentbridge.server` for legacy session SQLite store | `~/.subagentbridge/sessions.db` |
| `SUBAGENTBRIDGE_MAX_RETRIES` | Read at import for legacy `spawn_agent` default | `2` |
| `SUBAGENTBRIDGE_DEFAULT_TIMEOUT_S` | Read at import for legacy wait default | `600` seconds |
| `SUBAGENTBRIDGE_PRODUCTION_DB` | Read when `get_production_system()` lazily builds the composition root | `<workspace>/.subagentbridge/production_audit.db` |
| `SUBAGENTBRIDGE_ROUTER_URL` | Mentioned in older docs; **not wired in this server's `get_production_system()` call** | Do not rely on this variable to change the client endpoint |
| `SUBAGENTBRIDGE_ROUTER_KEY` / `SUBAGENTBRIDGE_BROKER_SECRET` / `SUBAGENTBRIDGE_GATE_MODE` | Described by policy/older docs; **not validated as active server configuration by this audit** | Do not rely on them as enforced controls without a source-and-integration check |

`build_production_system(workspace_root, ..., nine_router_base_url="http://127.0.0.1:9099", nine_router_api_key=...)` accepts explicit Python arguments. The MCP server's current composition call does not forward runtime router environment variables into those parameters. This is a configuration gap, not a reason to hardcode real API credentials in public files.

## Operating policy

- `AUTONOMY: OFF`: no unattended privileged operations.
- D-01 `RISK_ACCEPTED_SAME_IDENTITY`: not a sandbox or separate security principal.
- D-03 `CHAT_APPROVAL`: policy mode, not evidence of user-authentication isolation.
- D-02: the `LocalRouterConfig` client accepts a literal HTTP loopback IP and explicit port, no `/v1` path in the base origin. API paths are appended by the client.

## Persistence boundaries

SQLite audit and budget layers use transaction controls, but `submit_goal`'s current `_runs` and `_tasks` maps are in-memory. A persisted event alone does not rehydrate an active MCP run on restart.

Refer to [Status](SIMPUL_STATUS.md) and [9Router guide](NINE_ROUTER_SETUP.md) before a live deployment.
