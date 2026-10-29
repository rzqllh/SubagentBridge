# Security invariant catalogue : PR-00

These invariants define required behavior. Read [Security](SECURITY.md) for enforcement limits. Passing a test is not a security certification. `AUTONOMY: OFF`.

| ID | Contract (must be proven with executable negative tests) | Planned gate / PR |
|---|---|---|
| INV-01 | No task VERIFIED without registered independent QA verdict and executor-issued receipts for exact clean tree | E16, E17 / PR-01,03b,09 |
| INV-02 | Developer and PM cannot issue QA verdict or executor receipt | E16 / PR-01 |
| INV-03 | Human gate can only be resolved via authenticated, worker-inaccessible D-03 channel | E05, E18 / PR-03 |
| INV-04 | Unanswered/timed-out approvals remain BLOCKED | E05, E11 / PR-03 |
| INV-05 | Change to verified tree always revokes VERIFIED | E04, E17 / PR-01,09 |
| INV-06 | Autonomous workers have no raw shell; all side effects pass Bridge ToolExecutor | E07, E11 / PR-04b |
| INV-07 | Tests/builds never run as broker/control-plane identity with autonomy enabled | E18, AG-1 / PR-04b |
| INV-08 | Worker cannot access broker credentials, policy, approvals or UI channel | E18 / PR-03,04b |
| INV-09 | Stale dispatch cannot complete newer retry/attempt | E02, E12 / PR-01,02 |
| INV-10 | Untrusted messages, files and skills cannot override permissions | E06, E14 / PR-03,07 |
| INV-11 | Message/token/currency and retry ceilings stop execution before extra side effects | E09 / PR-06 |
| INV-12 | No production composition root registers test-only Fake workers/issuers | PR-03b |

## CI contract: red is visible

`tests/test_invariants_contract.py` contains **twelve named expected failures**, one per invariant. They deliberately assert current missing interfaces or unsafe legacy behavior. An `expectedFailure` result is **not** a pass for that invariant even when the unit test process returns exit 0; it remains `UNVERIFIED`. `unexpected success` is a gate to investigate:never silently waive or relax an assertion. These scaffolding probes are **not** substitute for required executable adversarial tests.

When a PR implements one invariant, first prove negative tests using the actual execution boundary, receipts and independent verifier on the exact SHA, then update the test's expected-failure classification with explicit test ownership and human approval if test edits are required. PR-00 does not weaken any future acceptance criterion.

Prior legacy probes in `tests/test_legacy_security_gaps.py` also remain expected failures. CI passing with xfails means **baseline harness runs**, not that Bridge safety is verified.
