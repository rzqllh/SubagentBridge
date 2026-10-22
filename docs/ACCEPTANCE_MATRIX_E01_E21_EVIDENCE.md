> **Scope clarification — 23 October 2026:** This is the historical 21 October E01–E21 unit-test evidence, not independent proof of full product acceptance. In particular **E18's recorded PASS covers the implemented token-test scenario, not an adversarial same-user broker/secret isolation attack**. E22 and E23 are additional required checks and are not covered by this 21-test matrix. No fresh run has been performed during the Simpul documentation refresh. See [status](SIMPUL_STATUS.md).

# Acceptance Matrix E01 to E21 Verification Evidence

Repository: `rzqllh/SubagentBridge`  
Governing Policy: `docs/TEAM_RULES.md` and Plan v3.1  
Date of Verification: 2026-10-21  
Commit Baseline: `096295a545c5acc11f69dd4f769dd36ed52eb10d`  
Test File: `tests/test_acceptance_matrix_e01_e21.py`  
Test Execution Command: `python -m unittest tests/test_acceptance_matrix_e01_e21.py`  
Full Suite Discovery: `python -m unittest discover -s tests -p "test_*.py"`  
Suite Results: 250 tests ran, 246 passed, 4 skipped (optional external Orca/remote network), 0 errors, 0 failures, 0 xfail. Exit code: 0.

---

## Acceptance Matrix Scenarios (Plan v3.1)

| ID | Criterion Name | Mechanism Verified | Status | Test Name |
|---|---|---|---|---|
| E01 | Native Full Journey | PM -> Developer -> ExecutorReceipt -> QA Verdict lifecycle without Orca | PASS | `test_E01_native_full_journey` |
| E02 | Disagreement & 3-Round Termination | 3 QA fix cycles without acceptance escalate to human BLOCKED | PASS | `test_E02_disagreement_and_three_rounds_blocked` |
| E03 | False-Proof Rejection | Unissued executor receipts fail closed at QA verification | PASS | `test_E03_false_proof_rejected` |
| E04 | Tree SHA Invalidation | Codebase tree changes invalidate prior QA verification receipts | PASS | `test_E04_tree_sha_integrity_invalidation` |
| E05 | Human Approval & Replay Protection | High-entropy token approval; replaying approved token is denied | PASS | `test_E05_approval_identity_and_replay_prevention` |
| E06 | Skill Injection & Hash Denial | Unapproved skills or tampered skill hashes fail closed | PASS | `test_E06_skill_injection_and_tamper_denied` |
| E07 | Forbidden Edits Boundary | Worker attempting QA test modification is classified as QA_CHANGE and blocked | PASS | `test_E07_forbidden_edits_boundary` |
| E08 | Windows Teardown & Process Cleanup | Isolated child process execution terminates cleanly without handle leaks | PASS | `test_E08_windows_teardown_and_process_cleanup` |
| E09 | Persistent Budget & Concurrency Cutoff | SQLite durable budget ceiling and worker concurrency limit enforced | PASS | `test_E09_persistent_budget_concurrency_cutoff` |
| E10 | 9Router Capability Negotiation | Client requests for unsupported capabilities fail closed immediately | PASS | `test_E10_9router_capability_negotiation_fails_closed` |
| E11 | Policy-Sensitive Triggers Human Gate | High-risk actions (deps, git push, creds, deletes) require human approval | PASS | `test_E11_policy_sensitive_triggers_gate` |
| E12 | Ledger Persistence & Recovery | Unreconciled session crash recorded; atomic reconciliation in SQLite | PASS | `test_E12_persistence_and_recovery` |
| E13 | Optional Orca Isolation | System operates fully native without Orca CLI binary present | PASS | `test_E13_optional_orca_isolation` |
| E14 | Prompt Injection Treated as Data | Malicious arguments in payload fail closed as UNKNOWN policy | PASS | `test_E14_prompt_injection_treated_as_data` |
| E15 | Standard 5-Field Handoff Report | Reports enforce STATUS, EVIDENCE, UNCERTAINTY, DECISIONS, NEEDS HUMAN | PASS | `test_E15_standard_report_format` |
| E16 | Receipt Authority Rejection | Unregistered receipts cannot be converted to valid Evidence | PASS | `test_E16_receipt_authority_unissued_rejected` |
| E17 | Tree Binding & Dirty Checkout Rejection | Dirty git working tree prevents QA evidence from issuing | PASS | `test_E17_tree_binding_dirty_checkout_rejection` |
| E18 | Broker Secret Isolation | Worker cannot guess or pass fabricated auth tokens to broker | PASS | `test_E18_same_user_broker_secret_isolation` |
| E19 | Phase Label Compliance | Enforces GATE_MODE: CHAT_APPROVAL and AUTONOMY: OFF headers | PASS | `test_E19_phase_labels_compliance` |
| E20 | Skipped Test Cannot Be VERIFIED | Partial or skipped test runs cannot be claimed as VERIFIED | PASS | `test_E20_harness_skip_recorded_as_unverified` |
| E21 | Windows Bootstrap Tooling Self-Test | Python bootstrap tools verify SHA-256 integrity and requirements | PASS | `test_E21_bootstrap_tooling_selftest` |

---

## Execution Logs

```text
======================================================================
python -m unittest tests/test_acceptance_matrix_e01_e21.py
.....................
----------------------------------------------------------------------
Ran 21 tests in 0.097s

OK
======================================================================
python -m unittest discover -s tests -p "test_*.py"
Ran 250 tests in 2.363s
OK (skipped=4)
```

## Security Posture
- Autonomy: `AUTONOMY: OFF`
- Confinement: `RISK_ACCEPTED_SAME_IDENTITY` (Phase A Supervised Development under D-01)
- Gate Mode: `CHAT_APPROVAL` (D-03)
- Router Loopback: `127.0.0.1` only, zero external egress (D-02)
