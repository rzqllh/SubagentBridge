"""PR-06 partial: pure deterministic DAG validation and budget reservation.

No worker spawning, authorization, economic rate inference, or token counting.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from threading import Lock

class BudgetExceeded(RuntimeError): pass

@dataclass(frozen=True)
class Reservation:
    dispatch_id: str
    token_allowance: int
    cost_microunits: int

class BudgetLedger:
    def __init__(self, *, tokens: int, cost_microunits: int, max_workers: int):
        if min(tokens,cost_microunits,max_workers)<0 or max_workers==0: raise ValueError('invalid budget')
        self.tokens=tokens
        self.cost=cost_microunits
        self.max_workers=max_workers
        self._reservations:dict[str,Reservation]={}
        self._lock=Lock()

    def reserve(self, *, dispatch_id:str, token_allowance:int, cost_microunits:int) -> Reservation:
        if not dispatch_id or min(token_allowance,cost_microunits)<0:raise ValueError('valid identity and ceilings required')
        with self._lock:
            if dispatch_id in self._reservations: raise BudgetExceeded('dispatch cannot reserve twice')
            if len(self._reservations)>=self.max_workers or token_allowance>self.tokens or cost_microunits>self.cost:
                raise BudgetExceeded('concurrency or token/cost ceiling exceeded')
            r=Reservation(dispatch_id,token_allowance,cost_microunits)
            self.tokens-=token_allowance;self.cost-=cost_microunits;self._reservations[dispatch_id]=r
            return r

    def release(self, dispatch_id:str, *, unused_tokens:int=0, unused_cost:int=0) -> None:
        with self._lock:
            r=self._reservations.get(dispatch_id)
            if r is None:raise KeyError('unknown dispatch')
            if not 0<=unused_tokens<=r.token_allowance or not 0<=unused_cost<=r.cost_microunits:
                raise ValueError('refund not verified by reservation')
            self.tokens+=unused_tokens;self.cost+=unused_cost;del self._reservations[dispatch_id]

    def snapshot(self)->dict:
        with self._lock:
            return {'tokens_available':self.tokens,'cost_available':self.cost,'active':len(self._reservations)}


def validate_task_dag(dependencies: Mapping[str,tuple[str,...]], acceptance_criteria: Mapping[str,tuple[str,...]])->tuple[str,...]:
    if not dependencies or set(dependencies)!=set(acceptance_criteria):raise ValueError('complete task list and AC required')
    for task,ac in acceptance_criteria.items():
        if not task or not ac or any(not isinstance(x,str) or not x.strip() for x in ac):raise ValueError('each task needs measurable AC')
    graph={k:tuple(v) for k,v in dependencies.items()}
    result=[];visiting=set();visited=set()
    def dfs(node):
        if node in visiting: raise ValueError('dependency cycle')
        if node in visited:return
        visiting.add(node)
        for dep in graph[node]:
            if dep not in graph:raise ValueError('unknown dependency')
            dfs(dep)
        visiting.remove(node);visited.add(node);result.append(node)
    for task in sorted(graph):dfs(task)
    return tuple(result)
