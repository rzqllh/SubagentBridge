"""PR-11 opt-in Orca adapter seam; no Orca binary invocation in disabled mode.

Interface is deliberately conservative: no undocumented job/cancel commands. A
real CLI implementation requires a pinned Orca upstream and live smoke tests.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True,slots=True)
class OrcaProbe:
    available: bool
    enforcement_class: str
    details: str

class OptionalOrcaBackend:
    def __init__(self, *, enabled: bool=False, status_runner: Callable[[],dict]|None=None):
        self.enabled=enabled
        self._status_runner=status_runner
        self._owned:set[str]=set()

    def probe(self)->OrcaProbe:
        if not self.enabled:
            return OrcaProbe(False,'UNSUPPORTED_ENFORCEMENT','Orca disabled, no CLI calls')
        if self._status_runner is None:
            return OrcaProbe(False,'UNSUPPORTED_ENFORCEMENT','No verified Orca CLI adapter configured')
        try:
            details=self._status_runner()
        except (OSError,ValueError,RuntimeError) as exc:
            return OrcaProbe(False,'UNSUPPORTED_ENFORCEMENT',type(exc).__name__)
        if not isinstance(details,dict) or type(details.get('available')) is not bool:
            return OrcaProbe(False,'UNSUPPORTED_ENFORCEMENT','Malformed status response')
        return OrcaProbe(details['available'],'UNSUPPORTED_ENFORCEMENT',
                         'CLI detected; isolation and dispatch support NOT VERIFIED')

    def dispatch(self,task_id:str,dispatch_id:str):
        raise PermissionError('Orca dispatch unsupported until CLI and isolation verified')

    def cancel(self,dispatch_id:str):
        raise PermissionError('Orca cancellation unsupported; never use global reset')

    @staticmethod
    def normalize_worker_done(data:dict)->dict:
        if not isinstance(data,dict) or not data.get('dispatch_id') or data.get('status')!='worker_done':
            raise ValueError('invalid worker completion signal')
        return {'dispatch_id':data['dispatch_id'],'status':'WAITING_QA','verified':False}
