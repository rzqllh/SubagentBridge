# Operational Incident Runbook & Enterprise Resilience Guide

**Target System:** Simpul Native Architecture (`SubagentBridge`)  
**Scope:** P1 Operational Resilience, Crash Recovery, Release CI Gates, SQLite WAL Procedures, and Incident Response Playbooks.  
**Classification:** Enterprise Operating Procedure  

---

## 1. Exact-Main Release CI Gate & Provenance Policy

### Invariant
No release package, tag, or publication shall ever be triggered from an unverified, unreviewed, or divergent commit. Publication gates strictly assert that `GITHUB_SHA` matches `origin/main` exact `HEAD` and that all four matrix validation jobs have completed with `status: success`.

### CI Pipeline Verification Matrix
Every PR and candidate release must pass all matrix jobs:
1. `ubuntu-latest` / Python 3.11
2. `ubuntu-latest` / Python 3.13
3. `windows-latest` / Python 3.11
4. `windows-latest` / Python 3.13

### Release Workflow Provenance Gate
In `.github/workflows/release.yml`, release packaging must execute the exact-main check:
```bash
# Verify current checked-out commit is identical to remote origin/main HEAD
REMOTE_MAIN_SHA=$(git ls-remote origin refs/heads/main | awk '{print $1}')
LOCAL_HEAD_SHA=$(git rev-parse HEAD)

if [ "$REMOTE_MAIN_SHA" != "$LOCAL_HEAD_SHA" ]; then
  echo "FATAL: Exact-main gate failure: HEAD $LOCAL_HEAD_SHA != origin/main $REMOTE_MAIN_SHA"
  exit 1
fi
```

---

## 2. Protected Branch & Independent Review Policy

**NOT YET ENFORCED:** GitHub currently reports `main.protected=false`; the following are intended requirements, not automatically enforced repository settings. Independent review and signed-commit enforcement remain outstanding.

1. **Direct Pushes Prohibited:** Pushing directly to `main` is disallowed.
2. **Review Gates:** Every PR requires at least one independent review approval from an authorized security architect / principal maintainer.
3. **Commit Signatures:** Commits must be cryptographically signed (GPG/SSH).
4. **Clean Tree Requirement:** Working tree must have zero uncommitted changes, untracked files, or temporary artifacts prior to merge.

---

## 3. SQLite WAL Backup, Restore & Migration Drills

Simpul uses SQLite in Write-Ahead Logging (`WAL`) mode with strict application-level referential integrity and zero-data-loss migrations.

### Standard Backup Procedure
Online backups must use `TeamStore.backup_database()`, which truncates WAL journals and performs a non-blocking online page backup followed by `PRAGMA integrity_check`:
```python
from subagentbridge.storage.team_store import TeamStore

store = TeamStore("/var/lib/simpul/simpul.db")
# 1. Truncate WAL and perform online atomic backup
store.backup_database("/var/backups/simpul/simpul_backup_20261027.db")
```

### Point-in-Time Restore Procedure
Restoring from a backup validates structural integrity, removes stale `-wal` / `-shm` sidecar files, and instantiates a verified `TeamStore`:
```python
# 2. Restore to target location
restored_store = TeamStore.restore_from_backup(
    backup_path="/var/backups/simpul/simpul_backup_20261027.db",
    target_path="/var/lib/simpul/simpul.db",
)
```

### Emergency CLI WAL Checkpoint
If SQLite `-wal` files grow unexpectedly large during heavy queue traffic:
```bash
sqlite3 /var/lib/simpul/simpul.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 /var/lib/simpul/simpul.db "PRAGMA integrity_check;"
```

---

## 4. Crash Recovery & Ambiguous Side-Effect Reconciliation

### Background
When a worker process crashes, terminates abruptly, or the host reboots mid-execution, tasks that were `RUNNING` or `DISPATCHED` may have executed partial external side effects (e.g. file mutations, network dispatches, database writes).

### Invariant
**Never assume automatic completion or blind idempotent replay.**
1. Workers whose PIDs are dead are marked `WorkerStatus.FAILED`.
2. Tasks in `PENDING` state are marked `QueueTaskStatus.FAILED` (safe, no host side effect executed).
3. Tasks in `RUNNING` or `DISPATCHED` state are transitioned to `QueueTaskStatus.AMBIGUOUS` when `mark_in_flight_as_ambiguous=True`.

### Operator Incident Reconciliation Procedure
When an alert fires for `AMBIGUOUS` tasks:

1. **Inspect Ambiguous Tasks:**
   ```bash
   python -c "
   from subagentbridge.storage.team_store import TeamStore
   store = TeamStore('/var/lib/simpul/simpul.db')
   items = store.list_queue_by_team('<team_id>')
   for item in items:
       if item.status == 'AMBIGUOUS':
           print(f'Dispatch: {item.dispatch_id}, Task: {item.task_id}, Payload: {item.payload}')
   "
   ```

2. **Inspect Host State for Side Effects:**
   - Review git commit status in the worker's assigned worktree (`git status`, `git log -n 1`).
   - Check if expected artifacts were created and are non-empty.
   - Inspect external logs or destination systems.

3. **Execute Operator Reconciliation:**
   Use `reconcile_ambiguous_task(dispatch_id, store, resolution, operator_notes)`:
   - **Scenario A (Clean / No Side Effects):** Safe to re-dispatch from beginning:
     ```python
     reconcile_ambiguous_task(dispatch_id, store, resolution="RETRY", operator_notes="Worktree verified clean; safe to retry")
     ```
   - **Scenario B (Completed Successfully Prior to Crash):** Artifacts exist and are verified:
     ```python
     reconcile_ambiguous_task(dispatch_id, store, resolution="MARK_COMPLETED", operator_notes="Verified artifacts manually")
     ```
   - **Scenario C (Partial Irrecoverable Failure):** Abandon task to prevent corrupting state:
     ```python
     reconcile_ambiguous_task(dispatch_id, store, resolution="MARK_FAILED", operator_notes="Partial side effect detected; manual remediation completed")
     ```

---

## 5. Bounded Queues, Load, and Resource Ceilings

### Resource Ceilings
- **Worker Process Timeout:** Default 300 seconds per command step.
- **Queue Task Backlog Ceiling:** Default max 10,000 items per team queue.
- **Token Budget Ceilings:** Strictly enforced per session in `WorkerConfig.tokens_consumed`.
- **Process Memory Limits:** NOT VERIFIED. Windows Job Object *UI* restrictions are not a proven memory ceiling. Linux cgroups and resource-enforced worker limits require separate implementation and host acceptance.

---

## 6. SBOM, Checksum Verification & Supply-Chain Attestation

### Checksum Verification
Every release asset distributed via GitHub releases must provide a `SHA256SUMS` manifest:
```bash
sha256sum --check SHA256SUMS
```

### SBOM Generation
Generate CycloneDX / SPDX Software Bill of Materials (SBOM) during release:
```bash
pip install pip-audit cyclonedx-bom
cyclonedx-py environment --outfile sbom.json
pip-audit --desc
```

---

## 7. Installation, Rollback, and Smoke Tests

### Post-Deployment Smoke Test
After installing a new release wheel or container:
```bash
# 1. Run baseline sanity checks
python -m pytest tests/test_mcp_production_server.py -v

# 2. Run operational resilience drill
python -m pytest tests/test_operational_resilience.py -v
```

### Rollback Procedure
If unexpected regression occurs post-release:
1. Stop orchestrator supervisor processes.
2. Revert installation package to prior stable release:
   ```bash
   pip install subagentbridge==1.1.3
   ```
3. Restore SQLite database from pre-upgrade backup using `TeamStore.restore_from_backup()`.
4. Restart orchestrator and audit queue status.

---

## 8. Incident Severity Matrix & Triage Playbook

| Severity | Definition | Target Response | Action Protocol |
|:---|:---|:---|:---|
| **SEV-1 (Critical)** | Data integrity loss, unauthorized approval execution, security boundary escape | Immediate (< 15m) | Halt orchestrator, isolate network, invoke rollback, audit ledger |
| **SEV-2 (Major)** | Unhandled crash leaving tasks stuck in AMBIGUOUS, worker spawn failure | < 1 hour | Run `reconcile_team_after_crash()`, review operator runbook |
| **SEV-3 (Minor)** | Transient rate limit, non-blocking telemetry delay | < 24 hours | Standard triage, ticket logging |
