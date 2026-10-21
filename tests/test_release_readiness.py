import unittest
from subagentbridge.release.readiness import ReleaseGate, REQUIRED
class ReleaseTests(unittest.TestCase):
 def test_missing_never_passes(self):
  r=ReleaseGate.evaluate({'ci_windows':'PASS','ci_linux':'PASS'})
  self.assertEqual(r.status,'UNVERIFIED')
  self.assertIn('independent_qa_exact_tree',r.missing)
 def test_rejected_remains_rejected(self):
  r=ReleaseGate.evaluate({'security_review':'REJECTED'})
  self.assertEqual(r.status,'REJECTED')
 def test_no_merge_claim_even_with_all_proofs(self):
  r=ReleaseGate.evaluate({k:'PASS' for k in REQUIRED})
  self.assertEqual(r.status,'CLAIMS_PRESENT_UNVERIFIED')
if __name__=='__main__':unittest.main()
