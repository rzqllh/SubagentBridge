"""Developer-owned regression tests, not QA invariant replacements."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from subagentbridge.domain.contracts import Message
from subagentbridge.messaging.bus import DurableMessageBus
from subagentbridge.storage.audit_ledger import AuditLedger, ReplayConflict


class AtomicMessageReplayTests(unittest.TestCase):
    def test_concurrent_connections_create_one_message_and_one_ack(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.db'
            ledgers = [AuditLedger(path) for _ in range(8)]
            barrier = threading.Barrier(len(ledgers))
            msg = Message('message-1', 'dev', 'qa', 'task', 'dispatch', 'payload')
            def enqueue(ledger):
                barrier.wait(timeout=5)
                return DurableMessageBus(ledger, stream='run').enqueue(
                    msg, active_task_id='task', active_dispatch_id='dispatch')
            try:
                with ThreadPoolExecutor(max_workers=len(ledgers)) as pool:
                    answers = list(pool.map(enqueue, ledgers))
                self.assertEqual(answers.count(True), 1)
                self.assertEqual(answers.count(False), 7)
                barrier2 = threading.Barrier(len(ledgers))
                def ack(ledger):
                    barrier2.wait(timeout=5)
                    return DurableMessageBus(ledger, stream='run').ack('message-1', recipient_id='qa')
                with ThreadPoolExecutor(max_workers=len(ledgers)) as pool:
                    answers = list(pool.map(ack, ledgers))
                self.assertEqual(answers.count(True), 1)
                self.assertEqual(answers.count(False), 7)
                self.assertEqual(len(ledgers[0].read(stream='run', reader_stream='run')), 2)
                ledgers[0].verify(stream='run')
            finally:
                for ledger in ledgers:
                    ledger.close()

    def test_modified_replay_across_reopened_connections_denied(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.db'
            a = AuditLedger(path)
            a.append_once(stream='s', idempotency_key='m', event_type='MESSAGE_QUEUED',payload={'value':'original'})
            a.close()
            b = AuditLedger(path)
            try:
                event, created = b.append_once(stream='s',idempotency_key='m',event_type='MESSAGE_QUEUED',payload={'value':'original'})
                self.assertFalse(created)
                self.assertEqual(event.seq, 1)
                with self.assertRaises(ReplayConflict):
                    b.append_once(stream='s',idempotency_key='m',event_type='MESSAGE_ACK',payload={'value':'original'})
                with self.assertRaises(ReplayConflict):
                    b.append_once(stream='s',idempotency_key='m',event_type='MESSAGE_QUEUED',payload={'value':'changed'})
            finally:
                b.close()

    def test_oversized_message_fails_without_any_write(self):
        with TemporaryDirectory() as tmp:
            ledger = AuditLedger(Path(tmp) / 'audit.db')
            try:
                bus = DurableMessageBus(ledger,stream='s')
                msg = Message('id','dev','qa','task','dispatch','€' * 30000)
                with self.assertRaises(ValueError):
                    bus.enqueue(msg, active_task_id='task',active_dispatch_id='dispatch')
                self.assertEqual(ledger.read(stream='s',reader_stream='s'), [])
            finally:
                ledger.close()

if __name__ == '__main__':
    unittest.main()
