import unittest
from subagentbridge.mcp.read_api import SnapshotReadApi,TaskSnapshot
class SnapshotApiTests(unittest.TestCase):
 def setUp(self):
  self.api=SnapshotReadApi({'r':(TaskSnapshot('t','r','UNVERIFIED',('rec',)),)})
 def test_snapshot(self):
  self.assertEqual(self.api.get_run('r')['task_count'],1)
  self.assertEqual(self.api.list_tasks('r')[0]['status'],'UNVERIFIED')
  self.assertFalse(self.api.get_task_evidence('r','t')['verification_claimed'])
 def test_unknown_run(self):
  self.assertEqual(self.api.get_run('missing')['status'],'NOT_FOUND')
 def test_no_untrusted_state_mutation(self):
  for call in (self.api.submit_goal,self.api.answer_questions,self.api.cancel_run):
   self.assertEqual(call('r')['status'],'BLOCKED')
  self.assertEqual(self.api.get_run('r')['task_count'],1)
if __name__=='__main__':unittest.main()
