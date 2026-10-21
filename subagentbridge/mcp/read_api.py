"""PR-10 partial: synchronous typed snapshot reads. No approval or mutation API.

No external MCP registered and no trusted native authentication proven.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task_id: str
    run_id: str
    status: str
    evidence_ids: tuple[str,...]

class SnapshotReadApi:
    def __init__(self, runs: Mapping[str, tuple[TaskSnapshot, ...]]):
        self._runs = dict(runs)

    def get_run(self, run_id: str) -> dict:
        tasks = self._runs.get(run_id)
        if tasks is None:
            return {'status': 'NOT_FOUND', 'run_id': run_id}
        return {'run_id':run_id,'status':'READ_ONLY','task_count':len(tasks)}
    def list_tasks(self, run_id: str) -> tuple[dict,...]:
        return tuple({'task_id':t.task_id,'status':t.status} for t in self._runs.get(run_id,()))
    def get_task_evidence(self, run_id: str, task_id: str) -> dict:
        for t in self._runs.get(run_id,()):
            if t.task_id == task_id:
                return {'task_id':task_id,'status':t.status,'receipt_ids':t.evidence_ids,
                        'verification_claimed':False}
        return {'status':'NOT_FOUND','task_id':task_id}
    def submit_goal(self,*args,**kwargs):
        return {'status':'BLOCKED','reason':'trusted policy, approval and execution not wired'}
    def answer_questions(self,*args,**kwargs):
        return {'status':'BLOCKED','reason':'authenticated human channel not wired'}
    def cancel_run(self,*args,**kwargs):
        return {'status':'BLOCKED','reason':'real process ownership not proven'}
