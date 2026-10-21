# SubagentBridge: Persistence, Recovery, and Durable Ledgers

This document explains the SQLite-backed durability layer, crash recovery, and budget ledger mechanisms in SubagentBridge.

---

## 1. Durable Budget Ledger (`DurableBudgetLedger`)

In distributed or restarted agent workflows, in-memory budgets are vulnerable to race conditions and restart amnesia. SubagentBridge persists budgets in SQLite:

- **Tables:** `budget_ledger` (global run caps) and `budget_reservations` (per-dispatch allocations).
- **Concurrency Serialization:** Uses `BEGIN IMMEDIATE` transactions to prevent over-allocation races among concurrent workers.
- **Worker Limit Enforcement:** Tracks active worker count; dispatches exceeding `max_workers` raise `BudgetExceeded`.
- **Atomic Commits:** When dispatches complete, actual token and microunit consumption is committed atomically, and unconsumed reserves are returned to the pool.

---

## 2. Audit Ledger and Crash Recovery (`AuditLedger`)

To guarantee auditability across restarts:
- Every state transition is appended to the audit ledger in SQLite.
- If an unexpected termination occurs (e.g. power failure or process kill):
  1. The session is recorded with `note_unreconciled(stream, session_id, cause)`.
  2. The session transitions to `RECOVERY_REQUIRED`.
  3. No subsequent actions can be executed on that stream until atomic reconciliation occurs via `reconcile_closed(stream, session_id, evidence_key)`.
- Verified under Scenario E12 in `tests/test_acceptance_matrix_e01_e21.py`.

---

## 3. Windows Handle Management and Database Backups

- SQLite connections are managed explicitly. Test cases and runtime sessions call `.close()` to ensure all WAL file locks are released cleanly on Windows.
- Backup and restore procedures use standard SQLite `.backup()` or file copy after database closing.
