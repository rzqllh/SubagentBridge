# SubagentBridge: Testing and QA Verification Guide

This guide describes how to run and interpret the test suites in SubagentBridge.

---

## 1. Test Architecture

The SubagentBridge test suite is organized into distinct layers:

1. **Contract and Invariant Tests (`tests/test_invariants_contract.py`):** Realizes invariants INV-01 through INV-12 covering state transitions, budget bounds, approval broker one-time tokens, and executor receipts.
2. **Durable Storage Tests (`tests/test_durable_budget_sqlite.py`, `tests/test_audit_ledger.py`):** Validates SQLite WAL mode, atomic commits, rollback on failure, and concurrency caps.
3. **Control Plane & Server Tests (`tests/test_mcp_production_server.py`, `tests/test_composition_root.py`):** Validates MCP tools, dependency injection, and AST lockdown.
4. **Live Loopback Tests (`tests/test_nine_router_live_loopback.py`):** Runs an in-process loopback HTTP server to test real 9Router discovery, capability negotiation, and D-02 policy enforcement.
5. **Acceptance Matrix Suite (`tests/test_acceptance_matrix_e01_e21.py`):** Executes all 21 acceptance criteria (E01 through E21) defined in Plan v3.1.

---

## 2. Running Tests

Run the full discovery suite:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Run only the acceptance matrix:
```bash
python -m unittest tests/test_acceptance_matrix_e01_e21.py
```

Run with standard library isolation (no external dependencies required):
All core unit and invariant tests use standard Python libraries (`unittest`, `sqlite3`, `hashlib`, `pathlib`, `json`).
