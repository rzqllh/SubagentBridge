"""PR-02 candidate security regression tests (no original QA tests modified)."""
from __future__ import annotations

import sqlite3
import tempfile
import threading
from pathlib import Path
import unittest

from subagentbridge.storage.audit_ledger import AuditLedger, LedgerIntegrityError, ReplayConflict, GENESIS
from subagentbridge.recovery import reconcile_stale_sessions


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'audit.db'
        self.ledger = AuditLedger(self.db)

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def test_append_replay_and_conflict(self):
        a = self.ledger.append(stream='run-A', idempotency_key='e1', event_type='START', payload={'ok': True})
        self.assertEqual(a.seq, 1)
        self.assertEqual(self.ledger.append(stream='run-A', idempotency_key='e1', event_type='START', payload={'ok': True}), a)
        with self.assertRaises(ReplayConflict):
            self.ledger.append(stream='run-A', idempotency_key='e1', event_type='START', payload={'ok': False})
        self.assertEqual(len(self.ledger.read(stream='run-A', reader_stream='run-A')), 1)

    def test_stream_isolation(self):
        self.ledger.append(stream='a', idempotency_key='x', event_type='X', payload={})
        self.ledger.append(stream='b', idempotency_key='x', event_type='X', payload={})
        with self.assertRaises(PermissionError):
            self.ledger.read(stream='a', reader_stream='b')
        self.assertNotEqual(self.ledger.verify(stream='a'), GENESIS)

    def test_redaction_nested(self):
        self.ledger.append(stream='a', idempotency_key='x', event_type='SECRET', payload={'password': 'hush', 'meta': {'access-token': 'token', 'ok': [1]}})
        body = self.ledger.read(stream='a', reader_stream='a')[0].payload
        self.assertEqual(body['password'], '[REDACTED]')
        self.assertEqual(body['meta']['access-token'], '[REDACTED]')
        self.assertNotIn(b'hush', self.db.read_bytes())

    def test_mutation_detection(self):
        self.ledger.append(stream='a', idempotency_key='x', event_type='X', payload={'x': 1})
        self.ledger.append(stream='a', idempotency_key='y', event_type='Y', payload={'x': 2})
        conn = sqlite3.connect(self.db)
        try:
            with conn:
                conn.execute("UPDATE audit_events SET payload_json='{}' WHERE seq=1")
        finally:
            conn.close()
        with self.assertRaises(LedgerIntegrityError):
            self.ledger.verify(stream='a')
        with self.assertRaises(LedgerIntegrityError):
            self.ledger.append(stream='a', idempotency_key='z', event_type='Z', payload={})

    def test_tail_truncation_requires_external_anchor(self):
        self.ledger.append(stream='a', idempotency_key='x', event_type='X', payload={})
        old_tail = self.ledger.verify(stream='a')
        conn = sqlite3.connect(self.db)
        try:
            with conn:
                conn.execute("DELETE FROM audit_events WHERE stream='a'")
        finally:
            conn.close()
        self.assertEqual(self.ledger.verify(stream='a'), GENESIS)
        with self.assertRaises(LedgerIntegrityError):
            self.ledger.verify(stream='a', expected_tail=old_tail)

    def test_backup_restore(self):
        self.ledger.append(stream='a', idempotency_key='x', event_type='X', payload={})
        backup = Path(self.temp.name) / 'backup.db'
        self.ledger.backup_to(backup)
        restored = AuditLedger(backup)
        try:
            self.assertEqual(restored.verify(stream='a'), self.ledger.verify(stream='a'))
        finally:
            restored.close()

    def test_recovery_uncertain_not_idle(self):
        count = reconcile_stale_sessions(self.ledger, stream='run-a', observed_sessions=[('s1','working'), ('s2','idle')])
        self.assertEqual(count, 1)
        self.assertEqual(self.ledger.recovery_state(stream='run-a', session_id='s1'), 'RECOVERY_REQUIRED')
        self.assertIsNone(self.ledger.recovery_state(stream='run-a', session_id='s2'))
        self.ledger.reconcile_closed(stream='run-a', session_id='s1', evidence_key='verified-owner-gone')
        self.assertEqual(self.ledger.recovery_state(stream='run-a', session_id='s1'), 'RECONCILED_CLOSED')

    def test_concurrent_append_is_serialized(self):
        barrier = threading.Barrier(12)
        failures = []
        def write(i):
            try:
                barrier.wait(timeout=3)
                self.ledger.append(stream='a', idempotency_key=str(i), event_type='STEP', payload={'i': i})
            except Exception as exc:
                failures.append(exc)
        ts = [threading.Thread(target=write, args=(i,)) for i in range(12)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertFalse(failures, failures)
        self.assertEqual(len(self.ledger.read(stream='a', reader_stream='a')), 12)

    def test_broken_migration_version_rejected(self):
        self.ledger.close()
        conn = sqlite3.connect(self.db)
        try:
            with conn:
                conn.execute("UPDATE audit_schema SET version=99 WHERE component='ledger'")
        finally:
            conn.close()
        with self.assertRaises(LedgerIntegrityError):
            AuditLedger(self.db)
        self.ledger = AuditLedger.__new__(AuditLedger)
        self.ledger.close = lambda: None

    def test_non_json_or_nan_fail_closed(self):
        with self.assertRaises((ValueError, TypeError)):
            self.ledger.append(stream='a', idempotency_key='x', event_type='X', payload={'bad':object()})
        with self.assertRaises(ValueError):
            self.ledger.append(stream='a', idempotency_key='x', event_type='X', payload={'nan':float('nan')})

    def test_existing_legacy_schema_remains_unchanged(self):
        conn = sqlite3.connect(self.db)
        try:
            with conn:
                row = conn.execute("SELECT name FROM sqlite_master WHERE name='sessions'").fetchone()
                self.assertFalse(row)
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
