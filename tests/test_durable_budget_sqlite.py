"""Tests for SQLite-backed durable budget ledger across restarts and connections.

Proves:
1. Transactional budget deduction persists across independent connections / restarts.
2. Concurrent reservations fail closed if budget or max workers exceeded.
3. Refunds restore allowances atomically.
4. Input validation and double-reservation denials work identically to in-memory ledger.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from subagentbridge.planner.budget import (
    BudgetExceeded,
    DurableBudgetLedger,
    Reservation,
)


class DurableBudgetLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "budget.db"

    def tearDown(self):
        self.tmp.cleanup()

    def test_persists_across_independent_instances_and_restarts(self):
        ledger1 = DurableBudgetLedger(
            db_path=self.db_path,
            tokens=10000,
            cost_microunits=50000,
            max_workers=3,
        )
        r1 = ledger1.reserve(dispatch_id="disp-01", token_allowance=4000, cost_microunits=20000)
        self.assertEqual(r1.dispatch_id, "disp-01")
        ledger1.close()

        # Simulate restart with fresh instance connecting to same SQLite file
        ledger2 = DurableBudgetLedger(
            db_path=self.db_path,
            tokens=10000,
            cost_microunits=50000,
            max_workers=3,
        )
        snap = ledger2.snapshot()
        self.assertEqual(snap["tokens_available"], 6000)
        self.assertEqual(snap["cost_available"], 30000)
        self.assertEqual(snap["active"], 1)

        # Attempting second reservation that exceeds remaining tokens must fail closed
        with self.assertRaises(BudgetExceeded):
            ledger2.reserve(dispatch_id="disp-02", token_allowance=7000, cost_microunits=10000)

        # Releasing disp-01 with partial refund
        ledger2.release("disp-01", unused_tokens=1000, unused_cost=5000)
        snap2 = ledger2.snapshot()
        self.assertEqual(snap2["tokens_available"], 7000)
        self.assertEqual(snap2["cost_available"], 35000)
        self.assertEqual(snap2["active"], 0)
        ledger2.close()

    def test_rejects_duplicate_dispatch_and_over_refunding(self):
        ledger = DurableBudgetLedger(
            db_path=self.db_path,
            tokens=5000,
            cost_microunits=10000,
            max_workers=2,
        )
        ledger.reserve(dispatch_id="disp-dup", token_allowance=1000, cost_microunits=1000)
        with self.assertRaises(BudgetExceeded):
            ledger.reserve(dispatch_id="disp-dup", token_allowance=1000, cost_microunits=1000)

        with self.assertRaises(ValueError):
            ledger.release("disp-dup", unused_tokens=2000, unused_cost=1000)

        ledger.close()

    def test_max_worker_concurrency_ceiling_enforced(self):
        ledger = DurableBudgetLedger(
            db_path=self.db_path,
            tokens=100000,
            cost_microunits=100000,
            max_workers=2,
        )
        ledger.reserve(dispatch_id="worker-1", token_allowance=100, cost_microunits=100)
        ledger.reserve(dispatch_id="worker-2", token_allowance=100, cost_microunits=100)

        with self.assertRaises(BudgetExceeded):
            ledger.reserve(dispatch_id="worker-3", token_allowance=100, cost_microunits=100)

        ledger.close()


if __name__ == "__main__":
    unittest.main()
