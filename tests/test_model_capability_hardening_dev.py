"""Developer-owned negative tests; not QA invariant tests."""
from __future__ import annotations
import unittest
from subagentbridge.models.capability import ModelCapabilities, ModelRoutingTable


class DiscoveredCapabilityHardening(unittest.TestCase):
    def mk(self, name='a'):
        return ModelCapabilities(name,True,None,True,False,False)

    def test_duplicate_model_ids_denied(self):
        with self.assertRaises(ValueError):
            ModelRoutingTable([self.mk(),self.mk()])

    def test_untyped_capability_cost_flags_denied(self):
        for flags in ((1, False), (True, None), (True, 'false')):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                ModelCapabilities('id',None,None,None,*flags)

    def test_unknown_and_wrong_record_types_denied(self):
        with self.assertRaises(ValueError):
            ModelRoutingTable(['known-model'])
        with self.assertRaises(ValueError):
            self.mk('')
