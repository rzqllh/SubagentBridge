"""PR-02 candidate: recovery receipt and state must commit atomically."""
import sqlite3
import tempfile
from pathlib import Path
import unittest
from subagentbridge.storage.audit_ledger import AuditLedger, ReplayConflict


class AtomicRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = AuditLedger(Path(self.tmp.name) / 'audit.db')
        self.addCleanup(self.ledger.close)
        self.ledger.note_unreconciled(stream='run', session_id='s', cause='crash')

    def test_reconcile_event_and_state_commit_together(self):
        self.ledger.reconcile_closed(stream='run', session_id='s', evidence_key='operator-reconciled')
        self.assertEqual(self.ledger.recovery_state(stream='run', session_id='s'), 'RECONCILED_CLOSED')
        events = self.ledger.read(stream='run', reader_stream='run')
        self.assertEqual([e.event_type for e in events], ['RECOVERY_RECONCILED'])
        self.ledger.verify(stream='run')
        with self.assertRaises(ValueError):
            self.ledger.reconcile_closed(stream='run', session_id='s', evidence_key='operator-reconciled')
        self.assertEqual(len(self.ledger.read(stream='run', reader_stream='run')), 1)

    def test_failed_update_rolls_back_event_too(self):
        # Fault injection: raise inside the same SQLite transaction after event insert.
        self.ledger._conn.execute("""CREATE TRIGGER test_fail_recovery_update BEFORE UPDATE ON recovery_state
            BEGIN SELECT RAISE(ABORT, 'test interruption'); END;""")
        with self.assertRaises(sqlite3.DatabaseError):
            self.ledger.reconcile_closed(stream='run', session_id='s', evidence_key='candidate')
        self.assertEqual(self.ledger.recovery_state(stream='run', session_id='s'), 'RECOVERY_REQUIRED')
        self.assertEqual(self.ledger.read(stream='run', reader_stream='run'), [])
        self.ledger._conn.execute('DROP TRIGGER test_fail_recovery_update')
        self.ledger.reconcile_closed(stream='run', session_id='s', evidence_key='candidate')
        self.assertEqual(len(self.ledger.read(stream='run', reader_stream='run')), 1)

    def test_duplicate_evidence_across_sessions_does_not_alias_events(self):
        self.ledger.note_unreconciled(stream='run', session_id='s2', cause='crash')
        self.ledger.reconcile_closed(stream='run', session_id='s', evidence_key='same-key')
        self.ledger.reconcile_closed(stream='run', session_id='s2', evidence_key='same-key')
        events = self.ledger.read(stream='run', reader_stream='run')
        self.assertEqual(len(events), 2)
        self.assertNotEqual(events[0].idempotency_key, events[1].idempotency_key)

if __name__ == '__main__': unittest.main()
