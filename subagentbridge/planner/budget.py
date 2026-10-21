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
        if (any(type(x) is not int for x in (tokens, cost_microunits, max_workers))
                or min(tokens, cost_microunits, max_workers) < 0 or max_workers == 0):
            raise ValueError('nonnegative integer budgets and positive worker ceiling required')
        self.tokens=tokens
        self.cost=cost_microunits
        self.max_workers=max_workers
        self._reservations:dict[str,Reservation]={}
        self._lock=Lock()

    def reserve(self, *, dispatch_id:str, token_allowance:int, cost_microunits:int) -> Reservation:
        if (type(dispatch_id) is not str or not dispatch_id.strip()
                or any(type(x) is not int for x in (token_allowance, cost_microunits))
                or min(token_allowance, cost_microunits) < 0):
            raise ValueError('dispatch ID and nonnegative integer ceilings required')
        with self._lock:
            if dispatch_id in self._reservations: raise BudgetExceeded('dispatch cannot reserve twice')
            if len(self._reservations)>=self.max_workers or token_allowance>self.tokens or cost_microunits>self.cost:
                raise BudgetExceeded('concurrency or token/cost ceiling exceeded')
            r=Reservation(dispatch_id,token_allowance,cost_microunits)
            self.tokens-=token_allowance;self.cost-=cost_microunits;self._reservations[dispatch_id]=r
            return r

    def release(self, dispatch_id:str, *, unused_tokens:int=0, unused_cost:int=0) -> None:
        if (any(type(x) is not int for x in (unused_tokens, unused_cost))
                or unused_tokens < 0 or unused_cost < 0):
            raise ValueError('refunds must be nonnegative integers')
        with self._lock:
            r=self._reservations.get(dispatch_id)
            if r is None:raise KeyError('unknown dispatch')
            if not 0<=unused_tokens<=r.token_allowance or not 0<=unused_cost<=r.cost_microunits:
                raise ValueError('refund not verified by reservation')
            self.tokens+=unused_tokens;self.cost+=unused_cost;del self._reservations[dispatch_id]

    def snapshot(self)->dict:
        with self._lock:
            return {'tokens_available':self.tokens,'cost_available':self.cost,'active':len(self._reservations)}


def validate_task_dag(dependencies: Mapping[str, tuple[str, ...]],
                      acceptance_criteria: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Validate a frozen DAG iteratively, including large/deep task plans."""
    if (not isinstance(dependencies, Mapping) or
            not isinstance(acceptance_criteria, Mapping) or not dependencies or
            set(dependencies) != set(acceptance_criteria)):
        raise ValueError('complete task list and AC required')
    if any(type(task) is not str or not task.strip() or len(task) > 256
           for task in dependencies):
        raise ValueError('task IDs must be bounded nonempty text')
    for task, ac in acceptance_criteria.items():
        if (type(task) is not str or not task.strip()
                or not isinstance(ac, (tuple, list)) or not ac
                or any(type(x) is not str or not x.strip() for x in ac)
                or len(set(ac)) != len(ac)):
            raise ValueError('each task needs unique measurable AC')
    graph = {}
    for task, deps in dependencies.items():
        if (not isinstance(deps, (list, tuple))
                or any(type(dep) is not str or not dep.strip() or len(dep) > 256 for dep in deps)
                or len(set(deps)) != len(deps)):
            raise ValueError('dependencies must have unique valid IDs')
        graph[task] = tuple(deps)
        if any(dep not in dependencies for dep in deps):
            raise ValueError('unknown dependency')
    result = []
    visiting: set[str] = set()
    visited: set[str] = set()
    for task in sorted(graph):
        if task in visited:
            continue
        stack = [(task, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                visiting.remove(node)
                visited.add(node)
                result.append(node)
                continue
            if node in visiting:
                raise ValueError('dependency cycle')
            if node in visited:
                continue
            visiting.add(node)
            stack.append((node, True))
            for dep in reversed(graph[node]):
                if dep not in visited:
                    stack.append((dep, False))
    return tuple(result)
