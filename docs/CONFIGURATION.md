# SubagentBridge: Configuration and Environment Variables

This document details the configuration parameters, environment variables, and defaults for SubagentBridge.

---

## Environment Variables

| Variable | Type | Default | Description |
|---|---|---|---|
| `SUBAGENTBRIDGE_DB_PATH` | String (Path) | `subagentbridge.db` | Path to the SQLite storage file for audit events, task states, and durable budget ledgers. |
| `SUBAGENTBRIDGE_BROKER_SECRET` | String (Secret) | Auto-generated 32-byte hex | Pre-shared secret required to validate out-of-band human approvals. |
| `SUBAGENTBRIDGE_ROUTER_URL` | String (URL) | `http://127.0.0.1:8080/v1` | URL for local 9Router loopback proxy. Must be a loopback address (`127.0.0.1` or `localhost`). |
| `SUBAGENTBRIDGE_ROUTER_KEY` | String (Secret) | `""` | Bearer authentication key passed to local 9Router. |
| `SUBAGENTBRIDGE_WORKSPACE_ROOT` | String (Path) | Current Working Directory | Base directory within which worker file operations and dispatch workspaces are confined. |
| `SUBAGENTBRIDGE_GATE_MODE` | String | `CHAT_APPROVAL` | Human-in-the-loop approval gate mode (default: `CHAT_APPROVAL`). |
| `SUBAGENTBRIDGE_CONFINEMENT` | String | `RISK_ACCEPTED_SAME_IDENTITY` | Execution confinement tier under decision D-01. |

---

## Local 9Router Transport Boundaries (Decision D-02)

By design and policy:
- Upstream external network access from SubagentBridge is blocked by default.
- Only loopback network interfaces (`127.0.0.1`) are permitted for model routing.
- Any attempt to configure non-loopback network addresses fails closed unless explicitly permitted by an authorized human gate.

---

## SQLite Storage Configuration

SubagentBridge relies on SQLite with Write-Ahead Logging (WAL) and synchronous transactions:
- `PRAGMA journal_mode = WAL;`
- `PRAGMA synchronous = NORMAL;`
- `PRAGMA foreign_keys = ON;`
- `BEGIN IMMEDIATE` transaction serialization for durable budget allocations.

On Windows platforms, file handle cleanup is handled explicitly upon closing sessions or database ledgers to prevent file lock errors (`WinError 32`).
