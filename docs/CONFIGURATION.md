# Simpul v1.1.4 : Configuration reference

**Released:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4). Product: Simpul; Python module/MCP server: `subagentbridge`. For **Antigravity IDE** connection use [Getting Started](public/GETTING_STARTED.md) and the IDE's `mcp_config.json`.

The following variables are read in the v1.1.4 `subagentbridge/server.py` source. This is a **source wiring description**, not a claim of independently verified deployment against all external hosts.

| Variable | Runtime meaning | Default when omitted |
|---|---|---|
| `SUBAGENTBRIDGE_DB_PATH` | SQLite store for server/session/run/task data | `~/.subagentbridge/sessions.db` |
| `SUBAGENTBRIDGE_MAX_RETRIES` | Legacy runner retry limit | `2` |
| `SUBAGENTBRIDGE_DEFAULT_TIMEOUT_S` | Legacy wait default | `600` seconds |
| `SUBAGENTBRIDGE_PRODUCTION_DB` | Audit database path for the workspace's lazily built production composition root | `<workspace>/.subagentbridge/production_audit.db` |
| `NINE_ROUTER_BASE_URL` | Local router origin, preferred over `SUBAGENTBRIDGE_ROUTER_URL` | `http://127.0.0.1:9099` |
| `SUBAGENTBRIDGE_ROUTER_URL` | Fallback local router origin | `http://127.0.0.1:9099` |
| `NINE_ROUTER_API_KEY` | Router credential, preferred over `SUBAGENTBRIDGE_ROUTER_KEY` | Local placeholder in composition; not evidence of a valid router login |
| `SUBAGENTBRIDGE_ROUTER_KEY` | Fallback router credential | Local placeholder in composition |

**Never paste real router/approval credentials into public documentation or commit them to the repository.** Bind router only to a trusted local loopback endpoint; the Python bridge does not control the security or egress of any upstream proxy.

## Default operating safety

- `AUTONOMY: OFF`: privileged autonomous coding actions are not available by assumption.
- `GATE_MODE: CHAT_APPROVAL`: model/chat content is not independently authenticated operator identity. An unsafe command remains `BLOCKED` absent real authorization.
- E18 remains **BLOCKED**. Separate worker PIDs and Git worktrees are **not** isolation from the same account's files or secrets.
- The optional `VerifiedOperatorApprovalAuthority` is a Python component, **not** a switch enabling production WebAuthn/OIDC. It requires external verifier wiring and a trusted decision surface.

For more details see [install](INSTALLATION_QUICKSTART.md), [MCP tools](API_REFERENCE.md), [9Router](NINE_ROUTER_SETUP.md), and [security](public/SECURITY.md).
