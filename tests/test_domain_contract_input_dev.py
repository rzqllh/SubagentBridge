"""Developer-owned fail-closed validation probes for pure PR-01 contracts."""
from __future__ import annotations
from dataclasses import replace
import unittest
from subagentbridge.domain.contracts import (
    Run, Task, Dispatch, Message, Approval, Budget, SCHEMA_VERSION,
)

class ContractInputHardening(unittest.TestCase):
    def test_schema_version_cannot_be_boolean(self):
        for obj in (Run('r','p','policy'), Task('t','r',('ac',),'tree','policy')):
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                replace(obj,schema_version=True)

    def test_wrong_identity_types_or_control_chars_denied(self):
        examples = ((Run('r','p','policy'),'run_id',True),
                    (Task('t','r',('ac',),'tree','policy'),'tree_sha',42),
                    (Dispatch('d','t',1,'key','tree','p'),'idempotency_key','bad\nkey'),
                    (Message('m','from','to','t','d','hello'),'from_principal',42),
                    (Approval('id','fp','p'),'decision_id','x\x00y'))
        for obj, field, new in examples:
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(obj,**{field:new})

    def test_duplicate_acceptance_criteria_denied(self):
        with self.assertRaises(ValueError):
            Task('t','r',('same','same'),'tree','policy')

    def test_budget_rejects_boolean_and_float(self):
        baseline=Budget(10,2,300)
        for field, value in (('max_tokens', True), ('max_attempts', 2.5),
                             ('max_cost_microunits', False)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(baseline,**{field:value})

    def test_dispatch_attempt_cannot_be_true(self):
        with self.assertRaises(ValueError):
            Dispatch('d','t',True,'key','tree','p')

    def test_approval_must_be_tri_state(self):
        for value in ('false', 1, 0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Approval('d','fingerprint','p',approved=value)

    def test_message_payload_must_be_text(self):
        with self.assertRaises(ValueError):
            Message('m','from','to','t','d',None)

if __name__ == '__main__':unittest.main()
