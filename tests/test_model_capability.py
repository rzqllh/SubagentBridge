import unittest
from subagentbridge.models.capability import ModelCapabilities,ModelRoutingTable,UnknownCapability
class CapabilityTests(unittest.TestCase):
 def mk(self,id,tools):return ModelCapabilities(id,tools,None,True,False,False)
 def test_coding_refuses_unknown_and_false(self):
  r=ModelRoutingTable([self.mk('a',None),self.mk('b',False)])
  with self.assertRaises(UnknownCapability):r.select(['a','b'],coding=True)
 def test_capability_matched_fallback(self):
  r=ModelRoutingTable([self.mk('a',None),self.mk('b',True)])
  self.assertEqual(r.select(['a','b'],coding=True).model_id,'b')
 def test_no_assumed_models(self):
  with self.assertRaises(UnknownCapability):ModelRoutingTable([]).select(['gemini-super-free'])
 def test_streaming_requires_true(self):
  m=ModelCapabilities('m',True,True,None,False,False)
  with self.assertRaises(UnknownCapability):ModelRoutingTable([m]).select(['m'],streaming=True)
 def test_cost_unknown_is_preserved(self):
  self.assertFalse(self.mk('a',True).input_cost_known)
if __name__=='__main__':unittest.main()
