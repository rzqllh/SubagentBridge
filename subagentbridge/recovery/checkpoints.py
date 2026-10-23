"""Checkpoint creator for interrupted workers; never assumes a worker exited."""
from __future__ import annotations

from collections.abc import Iterable
from ..storage.audit_ledger import AuditLedger


def reconcile_stale_sessions(ledger: AuditLedger, *, stream: str, observed_sessions: Iterable[tuple[str, str]]) -> int:
    """Mark uncertain sessions for external process ownership reconciliation.

    Does not kill processes, mark a task VERIFIED, or convert working to idle.
    """
    count = 0
    for session_id, observed_state in observed_sessions:
        if observed_state in {"working", "dispatching", "canceling"}:
            ledger.note_unreconciled(stream=stream, session_id=session_id, cause=f"unverified prior state: {observed_state}")
            count += 1
    return count
