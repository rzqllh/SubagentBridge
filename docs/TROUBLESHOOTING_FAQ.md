# SubagentBridge: Troubleshooting and FAQ

Common issues, diagnostic steps, and resolutions for SubagentBridge on Windows and Linux.

---

## 1. Windows SQLite Error 32 (`PermissionError: [WinError 32] The process cannot access the file because it is being used by another process`)

### Cause
On Windows, open SQLite database connections maintain an exclusive file lock on the database and WAL/SHM companion files. If a temporary directory is deleted or the database file is removed before calling `.close()`, Windows raises `WinError 32`.

### Solution
Always ensure database connections and ledger instances are closed explicitly before cleaning up workspaces:
```python
ledger = DurableBudgetLedger(db_path=path, ...)
try:
    ledger.reserve(...)
finally:
    ledger.close()
```

---

## 2. 9Router Connection Refused (`ConnectionRefusedError: [WinError 10061]`)

### Cause
SubagentBridge connects to local 9Router on loopback (`http://127.0.0.1:8080/v1`). If the router process is not running or listening on a different port, connections will be refused.

### Solution
- Ensure local 9Router is active: `curl http://127.0.0.1:8080/v1/models`.
- Update `SUBAGENTBRIDGE_ROUTER_URL` to match your local port if different.
- Verify that the target address is loopback (`127.0.0.1` or `localhost`). Non-loopback addresses fail closed by security policy (Decision D-02).

---

## 3. Human Approval Replay Error (`PermissionError: action already resolved`)

### Cause
An approval action was already approved or denied, and an agent or script re-submitted the same action token.

### Solution
By design, all approvals in SubagentBridge are single-use (`one-time approvals`). Once resolved, the action cannot be reused. Create a new dispatch request for any subsequent operations.

---

## 4. Unmet Invariants or Expected Failures

### Cause
Earlier roadmap versions marked incomplete security features as `expectedFailure`.

### Solution
In Roadmap v4 / v1.0.0-rc1, all 12 core invariants (INV-01 through INV-12) have been realized with production implementations. Run `python -m unittest discover -s tests -p "test_*.py"` to verify that zero tests are failing.
