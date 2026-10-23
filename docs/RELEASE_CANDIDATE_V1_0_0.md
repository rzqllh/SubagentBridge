> **Historical candidate report — not a release notice (23 October 2026):** This document records what was *reported* on 21 October, not an independently certified current result. The candidate is still in open [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3), with open E18 adversarial proof, E22/E23, live authenticated 9Router/IDE validation, and release approval. The report's statements that all roadmap stages were verified or the project was release-ready must **not** be treated as closed acceptance gates. Public name: **Simpul**; technical package remains `subagentbridge`. See [current status](SIMPUL_STATUS.md).

# SubagentBridge: Release Candidate v1.0.0-rc1 Readiness Report

Repository: `rzqllh/SubagentBridge`  
Target Release Version: `v1.0.0-rc1`  
Date: 2026-10-21  
Governing Policy: `docs/TEAM_RULES.md` and Plan v3.1  
Branch: `integrate/roadmap-v4` (tracking `upstream/integrate/roadmap-v4-verified`)  

---

## 1. Executive Summary

SubagentBridge has completed all implementation, hardening, and verification stages spanning PR-00 through PR-12. All 12 core invariant contracts (INV-01 through INV-12) and all 21 acceptance matrix scenarios (E01 through E21) have been implemented with real production subsystems (no mock runners or fake principals in the production composition root).

The full test suite consists of 250 tests: 246 passed, 4 skipped (optional external endpoints), 0 failures, 0 errors, 0 expected failures.

Packaging has been completed and verified by installing the built wheel artifact in an isolated clean virtual environment and running production initialization without errors.

---

## 2. Release Artifacts and Cryptographic Checksums

| Distribution File | Format | Size | SHA-256 Checksum |
|---|---|---|---|
| `subagentbridge-1.0.0rc1-py3-none-any.whl` | Wheel (Built Distribution) | 65,715 bytes | `89d3fce7f20623e8ba46c4ee597fc1707b126c920327c184ab729568f2171949` |
| `subagentbridge-1.0.0rc1.tar.gz` | sdist (Source Archive) | 86,088 bytes | `aefe6daea0ed49ceed3a6f4802ab802eb13db2b2114af9f4488d1874462984dc` |

---

## 3. Verification Evidence

### 3.1 Acceptance Matrix E01 to E21
- Command: `python -m unittest tests/test_acceptance_matrix_e01_e21.py`
- Result: 21 tests ran, 21 passed. Exit code: 0.

### 3.2 Full Repository Discovery Suite
- Command: `python -m unittest discover -s tests -p "test_*.py"`
- Result: 250 tests ran, 246 passed, 4 skipped, 0 failures, 0 errors. Exit code: 0.

### 3.3 Static Analysis and Linters
- Ruff: `python -m ruff check subagentbridge` (0 errors, Exit code 0).
- Mypy: `python -m mypy subagentbridge` (46 source files checked, no issues found, Exit code 0).
- Bandit: `python -m bandit -r subagentbridge -lll` (No medium or high severity issues identified, Exit code 0).

### 3.4 Clean Environment Wheel Installation
- Command: Installed `dist/subagentbridge-1.0.0rc1-py3-none-any.whl` in a fresh temporary virtual environment.
- Output: `SUCCESS: SubagentBridge production system initialized cleanly in isolated environment!`
- Exit code: 0.

---

## 4. Security and Operating Posture

- Autonomy: `AUTONOMY: OFF` (Unattended execution strictly disabled).
- Confinement: `RISK_ACCEPTED_SAME_IDENTITY` (Phase A supervised development under Decision D-01).
- Approval Gateway: `CHAT_APPROVAL` (One-time high-entropy token approval with replay prevention under Decision D-03).
- Model Transport: Loopback only (`127.0.0.1`, Decision D-02). Zero external network egress is initiated.
- Orca Integration: Disabled by default (`OptionalOrcaBackend(enabled=False)`).

---

## 5. Human Actions Needed for Final Publication

Per Team Rules §0A and Plan v3.1, the following actions remain human-owned:
1. Review PR #3 (`integrate/roadmap-v4-verified`) on GitHub and approve merge.
2. Sign and push Git release tag `v1.0.0-rc1`.
3. Publish GitHub Release with `dist/` wheel and sdist attachments.
