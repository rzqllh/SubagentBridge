# SubagentBridge: Native Mode vs Optional Orca

This document clarifies the relationship between Native mode and the optional Orca adapter in SubagentBridge.

---

## 1. Native Mode is Complete and Independent

**SubagentBridge is designed to run 100% natively without Orca.**

- All PM, Developer, and QA dispatch lifecycles, SQLite audit ledgers, durable budgets, approval brokers, and Antigravity MCP interfaces are built using standard Python and local subsystems.
- Orca is **never required** for installation, local development, test execution, or production usage of SubagentBridge.
- Verified under Scenario E13 in `tests/test_acceptance_matrix_e01_e21.py`.

---

## 2. Optional Orca Backend (`OptionalOrcaBackend`)

For environments that have an external Orca runtime installed:
- SubagentBridge provides an opt-in adapter interface (`OptionalOrcaBackend`).
- When disabled (`enabled=False`, default), the adapter returns `OrcaProbe(available=False, enforcement_class="UNSUPPORTED_ENFORCEMENT")` without attempting any CLI calls or subprocess launches.
- Orca can never issue human approvals or create QA verdicts.
- Dispatch through Orca raises a permission error until an isolated CLI adapter and execution boundary are independently verified.
