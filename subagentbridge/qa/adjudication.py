"""PR-09 partial: pure gate over already-issued PR-01 registries.

A model-produced receipt object, stdout text or an unregistered verdict is NOT
accepted. This does NOT verify whether OS command execution was isolated.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping
from subagentbridge.domain.contracts import Evidence
from subagentbridge.domain.registry import Principal, QaVerdict, ReceiptIssuerRegistry

@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    status: str
    reason: str

class QaEvidenceGate:
    def __init__(self, receipts: ReceiptIssuerRegistry, *, frozen_criteria: tuple[str,...],
                 qa_test_hashes: Mapping[str,str]):
        if not frozen_criteria or not all(isinstance(x,str) and x.strip() for x in frozen_criteria):
            raise ValueError('frozen acceptance criteria required')
        if not qa_test_hashes or not all(isinstance(p,str) and p.startswith('tests/')
                                        and len(h)==64 and all(c in '0123456789abcdef' for c in h)
                                        for p,h in qa_test_hashes.items()):
            raise ValueError('pinned QA-owned test paths/hashes required')
        self.receipts=receipts
        self.criteria=tuple(frozen_criteria)
        self.test_hashes=dict(qa_test_hashes)

    def check(self, *, qa: Principal, evidence: tuple[Evidence,...], covered_criteria: tuple[str,...],
              actual_test_hashes: Mapping[str,str], task_id: str, dispatch_id: str,
              expected_tree: str, actual_tree: str, checkout_clean: bool,
              fix_round: int, human_waiver: bool = False) -> tuple[EvidenceDecision, QaVerdict|None]:
        if fix_round >= 3:
            return EvidenceDecision('BLOCKED','three fix rounds exhausted: human required'),None
        if not checkout_clean or not expected_tree or actual_tree != expected_tree:
            return EvidenceDecision('UNVERIFIED','dirty checkout or wrong tree'),None
        if self.test_hashes != dict(actual_test_hashes):
            return EvidenceDecision('UNVERIFIED','QA tests changed, missing or substituted'),None
        if set(covered_criteria) != set(self.criteria) or len(covered_criteria)!=len(self.criteria):
            return EvidenceDecision('UNVERIFIED','frozen acceptance criteria not fully covered'),None
        if human_waiver:
            return EvidenceDecision('UNVERIFIED','human waiver is not QA evidence'),None
        if not evidence:
            return EvidenceDecision('UNVERIFIED','executor receipts required'),None
        try:
            v=self.receipts.create_qa_verdict(qa,evidence=evidence,task_id=task_id,
              dispatch_id=dispatch_id,tree_sha=expected_tree,accepted=True)
        except (PermissionError,ValueError,TypeError,AttributeError) as exc:
            return EvidenceDecision('UNVERIFIED','provenance rejected: '+type(exc).__name__),None
        return EvidenceDecision('QA_VERIFIED','registered, matched evidence for frozen criteria'),v
