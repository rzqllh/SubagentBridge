"""PR-06 partial: pure deterministic DAG validation and budget reservation.

No worker spawning, authorization, economic rate inference, or token counting.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path
import sqlite3
from threading import Lock

class BudgetExceeded(RuntimeError):
    pass


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
        self.tokens = tokens
        self.cost = cost_microunits
        self.max_workers = max_workers
        self._reservations: dict[str, Reservation] = {}
        self._lock = Lock()

    def reserve(self, *, dispatch_id: str, token_allowance: int, cost_microunits: int) -> Reservation:
        if (type(dispatch_id) is not str or not dispatch_id.strip()
                or any(type(x) is not int for x in (token_allowance, cost_microunits))
                or min(token_allowance, cost_microunits) < 0):
            raise ValueError('dispatch ID and nonnegative integer ceilings required')
        with self._lock:
            if dispatch_id in self._reservations:
                raise BudgetExceeded('dispatch cannot reserve twice')
            if len(self._reservations) >= self.max_workers or token_allowance > self.tokens or cost_microunits > self.cost:
                raise BudgetExceeded('concurrency or token/cost ceiling exceeded')
            r = Reservation(dispatch_id, token_allowance, cost_microunits)
            self.tokens -= token_allowance
            self.cost -= cost_microunits
            self._reservations[dispatch_id] = r
            return r

    def release(self, dispatch_id: str, *, unused_tokens: int = 0, unused_cost: int = 0) -> None:
        if (any(type(x) is not int for x in (unused_tokens, unused_cost))
                or unused_tokens < 0 or unused_cost < 0):
            raise ValueError('refunds must be nonnegative integers')
        with self._lock:
            r = self._reservations.get(dispatch_id)
            if r is None:
                raise KeyError('unknown dispatch')
            if not 0 <= unused_tokens <= r.token_allowance or not 0 <= unused_cost <= r.cost_microunits:
                raise ValueError('refund not verified by reservation')
            self.tokens += unused_tokens
            self.cost += unused_cost
            del self._reservations[dispatch_id]

    def snapshot(self)->dict:
        with self._lock:
            return {'tokens_available':self.tokens,'cost_available':self.cost,'active':len(self._reservations)}


_BUDGET_SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_ledger (
    ledger_id TEXT PRIMARY KEY,
    tokens_remaining INTEGER NOT NULL,
    cost_remaining INTEGER NOT NULL,
    max_workers INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS budget_reservations (
    ledger_id TEXT NOT NULL DEFAULT 'default',
    dispatch_id TEXT NOT NULL,
    token_allowance INTEGER NOT NULL,
    cost_microunits INTEGER NOT NULL,
    created_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (ledger_id, dispatch_id)
);
"""


class DurableBudgetLedger:
    """SQLite-backed durable transactional budget ledger across restarts and processes."""

    def __init__(self, *, db_path: str | Path, tokens: int, cost_microunits: int, max_workers: int, ledger_id: str = "default") -> None:
        if (any(type(x) is not int for x in (tokens, cost_microunits, max_workers))
                or min(tokens, cost_microunits, max_workers) < 0 or max_workers == 0):
            raise ValueError('nonnegative integer budgets and positive worker ceiling required')
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_id = ledger_id
        self._lock = Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        with self._lock:
            self._conn.executescript(_BUDGET_SCHEMA)
            # Idempotent migration for existing tables created without ledger_id column:
            cols = [info[1] for info in self._conn.execute("PRAGMA table_info(budget_reservations)").fetchall()]
            if "ledger_id" not in cols:
                self._conn.execute("ALTER TABLE budget_reservations ADD COLUMN ledger_id TEXT NOT NULL DEFAULT 'default'")
                self._conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_budget_reservations_ledger_dispatch ON budget_reservations (ledger_id, dispatch_id)")
            row = self._conn.execute("SELECT tokens_remaining, cost_remaining, max_workers FROM budget_ledger WHERE ledger_id=?", (self.ledger_id,)).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO budget_ledger (ledger_id, tokens_remaining, cost_remaining, max_workers) VALUES (?, ?, ?, ?)",
                    (self.ledger_id, tokens, cost_microunits, max_workers)
                )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def reserve(self, *, dispatch_id: str, token_allowance: int, cost_microunits: int) -> Reservation:
        if (type(dispatch_id) is not str or not dispatch_id.strip()
                or any(type(x) is not int for x in (token_allowance, cost_microunits))
                or min(token_allowance, cost_microunits) < 0):
            raise ValueError('dispatch ID and nonnegative integer ceilings required')
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT tokens_remaining, cost_remaining, max_workers FROM budget_ledger WHERE ledger_id=?",
                    (self.ledger_id,)
                ).fetchone()
                if row is None:
                    raise BudgetExceeded("budget ledger not initialized")
                tokens_rem, cost_rem, max_workers = row

                dup = self._conn.execute(
                    "SELECT 1 FROM budget_reservations WHERE ledger_id=? AND dispatch_id=?",
                    (self.ledger_id, dispatch_id)
                ).fetchone()
                if dup:
                    raise BudgetExceeded("dispatch cannot reserve twice")

                active_count = self._conn.execute(
                    "SELECT COUNT(*) FROM budget_reservations WHERE ledger_id=?",
                    (self.ledger_id,)
                ).fetchone()[0]

                if active_count >= max_workers or token_allowance > tokens_rem or cost_microunits > cost_rem:
                    raise BudgetExceeded("concurrency or token/cost ceiling exceeded")

                new_tokens = tokens_rem - token_allowance
                new_cost = cost_rem - cost_microunits
                self._conn.execute(
                    "UPDATE budget_ledger SET tokens_remaining=?, cost_remaining=? WHERE ledger_id=?",
                    (new_tokens, new_cost, self.ledger_id)
                )
                self._conn.execute(
                    "INSERT INTO budget_reservations (ledger_id, dispatch_id, token_allowance, cost_microunits) VALUES (?, ?, ?, ?)",
                    (self.ledger_id, dispatch_id, token_allowance, cost_microunits)
                )
                self._conn.execute("COMMIT")
                return Reservation(dispatch_id, token_allowance, cost_microunits)
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def release(self, dispatch_id: str, *, unused_tokens: int = 0, unused_cost: int = 0) -> None:
        if (any(type(x) is not int for x in (unused_tokens, unused_cost))
                or unused_tokens < 0 or unused_cost < 0):
            raise ValueError('refunds must be nonnegative integers')
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT token_allowance, cost_microunits FROM budget_reservations WHERE ledger_id=? AND dispatch_id=?",
                    (self.ledger_id, dispatch_id)
                ).fetchone()
                if row is None:
                    raise KeyError("unknown dispatch")
                token_allowance, cost_allowance = row
                if not 0 <= unused_tokens <= token_allowance or not 0 <= unused_cost <= cost_allowance:
                    raise ValueError("refund not verified by reservation")

                ledger_row = self._conn.execute(
                    "SELECT tokens_remaining, cost_remaining FROM budget_ledger WHERE ledger_id=?",
                    (self.ledger_id,)
                ).fetchone()
                tokens_rem, cost_rem = ledger_row
                new_tokens = tokens_rem + unused_tokens
                new_cost = cost_rem + unused_cost

                self._conn.execute(
                    "UPDATE budget_ledger SET tokens_remaining=?, cost_remaining=? WHERE ledger_id=?",
                    (new_tokens, new_cost, self.ledger_id)
                )
                self._conn.execute(
                    "DELETE FROM budget_reservations WHERE ledger_id=? AND dispatch_id=?",
                    (self.ledger_id, dispatch_id)
                )
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def snapshot(self) -> dict:
        with self._lock:
            ledger_row = self._conn.execute(
                "SELECT tokens_remaining, cost_remaining FROM budget_ledger WHERE ledger_id=?",
                (self.ledger_id,)
            ).fetchone()
            active_count = self._conn.execute(
                "SELECT COUNT(*) FROM budget_reservations WHERE ledger_id=?",
                (self.ledger_id,)
            ).fetchone()[0]
            tokens = ledger_row[0] if ledger_row else 0
            cost = ledger_row[1] if ledger_row else 0
            return {'tokens_available': tokens, 'cost_available': cost, 'active': active_count}



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
