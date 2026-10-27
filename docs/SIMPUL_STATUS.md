# Simpul — Project Status

**As of:** 27 October 2026  
**Latest published:** [v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1)  
**Package:** `subagentbridge` · **Repository:** [rzqllh/SubagentBridge](https://github.com/rzqllh/SubagentBridge)  
**Release merge SHA:** `861f040dc12c33da681331e454ef41299f2dc70b`  
**Release workflow:** [40444832484](https://github.com/rzqllh/SubagentBridge/actions/runs/40444832484) — SUCCESS

## Delivery and verified scope

- **C00–C07:** Native Simpul/Lead/Worker contract and typed lifecycle, real worker OS processes and JSONL IPC, durable SQLite dispatch and message channels, checked artifact handoffs, checkpoint continuity, worktree ownership, and safe `orca_*` database migration with compatibility aliases. Architecture inspired by Cindy research; independently implemented.
- **v1.1.1 runtime integrity corrections:** All shared SQLite reads and writes serialized; atomic cross-process task resumption; consistent human approval/workspace binding; preflight of all command approvals before side effects; consumed-ticket renewal; fail-closed ambiguous replay; Python child `-P` safe-path to protect trusted runtime imports from writable workspaces.
- **CI:** PR #19 final source tree passed the 4-job matrix (Ubuntu/Windows × Python 3.11/3.13), including full pytest, static quality/security checks, and import smoke test. Source tree of the merged `main` matches the tested PR head. Release workflow revalidated the exact `main` SHA before publishing wheel, sdist and checksums.

## Enterprise safety gates

| Gate | Status |
|---|---|
| Supervised multi-worker execution, local SQLite persistence, versioned migration | **VERIFIED (bounded)** |
| Concurrent shared-store integrity / multi-step human approval preflight | **VERIFIED (bounded)** |
| Signed / independently authenticated real human approval surface | **BLOCKED for enterprise** |
| E18 same-OS-identity worker confinement under hostile workloads | **BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)** |
| Exactly-once recovery of external side effects across crashes | **NOT GUARANTEED** |
| All real external host versions / multi-tenant production acceptance | **NOT VERIFIED** |

Governance remains `AUTONOMY: OFF` and `GATE_MODE: CHAT_APPROVAL`. A green CI matrix does not make a same-user worker an OS security sandbox, establish independent human identity, or certify malicious-worker isolation. Use dedicated least-privilege user accounts and supervised trusted workspaces.

## Current release artifacts

[GitHub Release v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1) contains:
- `subagentbridge-1.1.1-py3-none-any.whl`
- `subagentbridge-1.1.1.tar.gz`
- `SHA256SUMS.txt`

## Navigation and provenance

- [Public user guides](public/README.md) · [Installation](INSTALLATION_QUICKSTART.md) · [Security](public/SECURITY.md)
- [Enterprise readiness evidence & remaining blockers](ENTERPRISE_READINESS.md)
- [Core Cindy parity audit with historical phase receipts](simpul/SIMPUL_CINDY_PARITY_REPORT.md)
- [Release validation](simpul/RELEASE_READINESS.md) · [Third-party attribution](../THIRD_PARTY_NOTICES.md)

Historical PR #17 (C08 candidate) was closed as **superseded**, not merged; its remaining reviewer comments retain their actual historic GitHub disposition. The v1.1.1 corrections landed independently through PR #19. No local Windows user worktrees/backups were deleted as part of publication.
