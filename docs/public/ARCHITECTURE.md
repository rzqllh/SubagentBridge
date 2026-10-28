# Simpul architecture

> **v1.1.4 primary target:** Google Antigravity IDE via MCP stdio. Cindy/Orca architectural parallels are documented in the [current parity roadmap](PARITY_AND_ROADMAP.md); this diagram represents the **native supervisor**, not an IDE-native UI or full upstream parity.


Simpul is organized as a local MCP stdio transport, supervised orchestration domain, native worker subprocess controller, and a SQLite durable team store.

```text
IDE / MCP client (untrusted tool caller)
             |
       MCP stdio server
             |
    command admission / policy gate
             |
    supervised orchestration lead
        /                 \
  Worker A              Worker B
  native process        native process
  IPC and own PID       IPC and own PID
        \                 /
     durable SQLite team store
     queue / handoffs / checkpoints
             |
     inspected artifacts / QA
```

## Realized components

- `subagentbridge/server.py`: MCP server and bounded supervised operations.
- `subagentbridge/team/team_manager.py`: lead/worker lifecycle, queue, communication and handoff coordination.
- `subagentbridge/storage/team_store.py`: SQLite WAL-backed team, session, dispatch and checkpoint persistence; versioned compatibility migration.
- `subagentbridge/execution/worker_process.py`: OS subprocess worker ownership, IPC readers, deadlines, interruption and process-tree management.
- `subagentbridge/recovery/crash_recovery.py`: reconciliation, checkpoint binding and task continuation.
- `subagentbridge/workspaces/worktree_manager.py`: per-worker Git worktree lifecycle with fail-closed cleanup.
- `subagentbridge/runners/harness_adapters.py`: host capability declarations and routing; **adapter registration alone is not live external host acceptance**.

## Integrity properties and limits

Handoffs require physical artifacts, SHA-256 comparison, execution receipt checks and atomic SQLite finalization for verified completion. Dispatch idempotency is serialized across SQLite writers. Successful checkpoints are bound to task/dispatch identity and repository commit; ambiguous crash windows are conservatively labeled *at least once*, not exactly once.

A distinct worker PID is not a distinct operating-system security identity. Workers under the same user can potentially access that user's files and processes. The architecture does **not** provide container, hypervisor or sandbox guarantees; E18 remains blocked.

Cindy's orchestration architecture informed design research. Simpul is implemented independently in Python; see [attribution](../../THIRD_PARTY_NOTICES.md).
