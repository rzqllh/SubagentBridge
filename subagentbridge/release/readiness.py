"""PR-12 evidence inventory. No missing check may be interpreted as PASS."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

REQUIRED = ('clean_windows_setup','native_no_orca_e2e','local_9router_authenticated',
            'independent_qa_exact_tree','human_gate_negative','crash_restart_recovery',
            'skills_tamper_denial','permission_bypass_denial','worker_concurrency',
            'security_review','ci_linux','ci_windows','windows_process_tree_cleanup')

@dataclass(frozen=True,slots=True)
class ReleaseDecision:
    status: str
    missing: tuple[str,...]
    rejected: tuple[str,...]

class ReleaseGate:
    @staticmethod
    def evaluate(evidence: Mapping[str,str])->ReleaseDecision:
        missing = tuple(k for k in REQUIRED if evidence.get(k) != 'PASS')
        rejected = tuple(k for k in REQUIRED if evidence.get(k) == 'REJECTED')
        if rejected:
            return ReleaseDecision('REJECTED', missing, rejected)
        if missing:
            return ReleaseDecision('UNVERIFIED', missing, ())
        # Caller-supplied strings are claims, not authenticated verifier evidence.
        return ReleaseDecision('CLAIMS_PRESENT_UNVERIFIED',(),())
