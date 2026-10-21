import unittest
from subagentbridge.execution.orca_adapter import OptionalOrcaBackend
class OrcaOptionalTests(unittest.TestCase):
 def test_disabled_no_calls(self):
  calls=[]
  b=OptionalOrcaBackend(enabled=False,status_runner=lambda:(calls.append(1) or {'available':True}))
  self.assertFalse(b.probe().available)
  self.assertEqual(calls,[])
 def test_enabled_does_not_claim_enforcement(self):
  b=OptionalOrcaBackend(enabled=True,status_runner=lambda:{'available':True})
  self.assertTrue(b.probe().available)
  self.assertEqual(b.probe().enforcement_class,'UNSUPPORTED_ENFORCEMENT')
  with self.assertRaises(PermissionError):b.dispatch('t','d')
  with self.assertRaises(PermissionError):b.cancel('d')
 def test_done_is_not_qa_verified(self):
  o=OptionalOrcaBackend.normalize_worker_done({'dispatch_id':'d','status':'worker_done'})
  self.assertEqual(o['status'],'WAITING_QA')
  self.assertFalse(o['verified'])
 def test_malformed_is_rejected(self):
  for v in ({},{'dispatch_id':'d','status':'VERIFIED'},None):
   with self.assertRaises(ValueError):OptionalOrcaBackend.normalize_worker_done(v)
if __name__=='__main__':unittest.main()
