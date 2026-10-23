"""PR-01 domain message routing / idempotence; no I/O, no network."""
from __future__ import annotations

import concurrent.futures
import unittest
from subagentbridge.domain import Message, MessageRegistry


class MessageLedgerTests(unittest.TestCase):
    def test_once_only_for_same_target_and_dispatch(self):
        registry = MessageRegistry()
        msg = Message('m', 'developer', 'qa', 't', 'd', 'message')
        self.assertTrue(registry.record(msg, task_id='t', dispatch_id='d'))
        self.assertFalse(registry.record(msg, task_id='t', dispatch_id='d'))
        self.assertEqual(registry.recorded_count, 1)

    def test_cross_dispatch_denied_before_record(self):
        registry = MessageRegistry()
        msg = Message('m', 'developer', 'qa', 't', 'old-dispatch', 'message')
        with self.assertRaises(PermissionError):
            registry.record(msg, task_id='t', dispatch_id='new-dispatch')
        self.assertEqual(registry.recorded_count, 0)

    def test_conflicting_reuse_of_message_id_is_error(self):
        registry = MessageRegistry()
        m1 = Message('m', 'developer', 'qa', 't', 'd', 'safe')
        m2 = Message('m', 'developer', 'qa', 't', 'd', 'different')
        self.assertTrue(registry.record(m1, task_id='t', dispatch_id='d'))
        with self.assertRaises(ValueError):
            registry.record(m2, task_id='t', dispatch_id='d')

    def test_concurrent_duplicate_record_is_single(self):
        registry = MessageRegistry()
        msg = Message('m', 'developer', 'qa', 't', 'd', 'safe')
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(lambda _: registry.record(msg, task_id='t', dispatch_id='d'), range(100)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(registry.recorded_count, 1)

    def test_message_cannot_be_broadcast(self):
        registry = MessageRegistry()
        msg = Message('m', 'developer', '*', 't', 'd', 'broadcast')
        with self.assertRaises(PermissionError):
            registry.record(msg, task_id='t', dispatch_id='d')


if __name__ == '__main__':
    unittest.main()
