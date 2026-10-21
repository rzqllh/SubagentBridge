import tempfile
from pathlib import Path
import unittest
from subagentbridge.domain.contracts import Message
from subagentbridge.storage.audit_ledger import AuditLedger,ReplayConflict
from subagentbridge.messaging.bus import DurableMessageBus
class BusTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.ledger=AuditLedger(Path(self.t.name)/'events.db');self.bus=DurableMessageBus(self.ledger,stream='run1')
 def tearDown(self):self.ledger.close();self.t.cleanup()
 def msg(self,text='hi'):
  return Message('m1','dev','qa','task','dispatch',text)
 def test_exactly_once_record_and_ack(self):
  self.assertTrue(self.bus.enqueue(self.msg(),active_task_id='task',active_dispatch_id='dispatch'))
  self.assertFalse(self.bus.enqueue(self.msg(),active_task_id='task',active_dispatch_id='dispatch'))
  self.assertTrue(self.bus.ack('m1',recipient_id='qa'))
  self.assertFalse(self.bus.ack('m1',recipient_id='qa'))
 def test_modified_replay_rejected(self):
  self.bus.enqueue(self.msg(),active_task_id='task',active_dispatch_id='dispatch')
  with self.assertRaises(ReplayConflict):self.bus.enqueue(self.msg('changed'),active_task_id='task',active_dispatch_id='dispatch')
 def test_wrong_dispatch_rejected(self):
  with self.assertRaises(PermissionError):self.bus.enqueue(self.msg(),active_task_id='task',active_dispatch_id='new')
 def test_wrong_ack_recipient_rejected(self):
  self.bus.enqueue(self.msg(),active_task_id='task',active_dispatch_id='dispatch')
  with self.assertRaises(PermissionError):self.bus.ack('m1',recipient_id='pm')
 def test_reopen_preserves_duplicate(self):
  self.bus.enqueue(self.msg(),active_task_id='task',active_dispatch_id='dispatch')
  again=DurableMessageBus(self.ledger,stream='run1')
  self.assertFalse(again.enqueue(self.msg(),active_task_id='task',active_dispatch_id='dispatch'))
if __name__=='__main__':unittest.main()
