# Simpul — Full development roadmap (Plan v3.1 continuity)

This is a **forward development roadmap**, not an assertion that all stages are independently verified. Original governing specification: [Production PR Plan v3.1](../../artifacts/bootstrap/v3_1/candidate/Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md). Exactly 15 stages, retaining original IDs: PR-00, PR-01, PR-02, PR-03, PR-03b, PR-04a, PR-04b, PR-05, PR-06, PR-07, PR-08, PR-09, PR-10, PR-11, PR-12.

## Phase 0 — Repair current blockers (before any merge)

1. Restore PR-00 documentation-truth contract, rerun all 4 CI jobs and ensure all required suites, not only top-level tests, are discovered.
2. Triage and fix all 3 open PR #2 and 12 open PR #3 Codex findings. Add negative/regression tests for each. Preserve original findings; resolve only after verifying actual fix.
3. Reconcile PR #2 with updated `main` without erasing the branding/public-doc changes; apply immutable-head CI checkout and BVE test discovery corrections only after required exact-scope human approval.
4. Reconcile the large PR #3 against the fixed baseline; if changes require new implementation PRs, keep them reviewable and preserve original GitHub PR history.
5. Run independent SHA-bound QA again; past PR/CI results cannot be reused after source changes.

## The canonical stage matrix

| Stage | Planned deliverable | Current candidate observation | Remaining exit gate |
| --- | --- | --- | --- |
| PR-00 | Baseline truth, threat model, invariant tests, reproducible BVE/CI | PR #2 exists; currently merge-conflicted / reviews open | Correct immutable-head CI, full v3.1 tests, DP-00 provenance, independent QA |
| PR-01 | Typed domain, identity, state machine, receipt authority contracts | Modules + tests present | No fake receipt can mark VERIFIED in real API |
| PR-02 | Durable audit/recovery, atomic idempotency and WAL | SQLite modules present | Crash/restart, no cross-session key collision, durable run/task lifecycle |
| PR-03 | Fail-closed policy, human broker | Broker module present | Reject finality; real same-user adversarial E18; no LLM approval |
| PR-03b | Test-only PM/Dev/QA walking skeleton | Synthetic tests present | Six specified positive/negative paths; no fake principals in prod |
| PR-04a | Per-dispatch worktrees, cleanup | Process/workspace modules present | Sticky RECOVERY_REQUIRED, actual Windows grandchildren cleanup |
| PR-04b | Bridge ToolExecutor, receipt issuer, confinement class | Supervised executor utilities present | No untrusted shell in autonomous mode; E07 and OS threat evidence |
| PR-05 | Native 9Router and actual coding worker | Local text client and offline tests present | Live auth (past HTTP 401), tool-use loop, truthful capability + usage |
| PR-06 | PM/Dev/QA runtime planner, concurrency/budget | Coordinator/planner modules present | Real server dispatch; ledger-scoped limits; bounded fix cycles |
| PR-07 | Hash/path trusted skills and Harness content | LocalSkillRegistry present | Role-filtered actual dispatch, tamper/re-approval and Windows tests |
| PR-08 | Targeted durable messages, dedup and brainstorming | Message bus present | Collision-free idempotency and live targeted handoff |
| PR-09 | Independent QA engine, source/test protection, DoD | Evidence gate modules + tests present | Unforgeable issued receipts in actual lifecycle, E16/17, 3-round gate |
| PR-10 | Antigravity MCP control plane and HITL UX | Tool endpoints registered | `submit_goal` executes real lifecycle; restart recovery, live IDE |
| PR-11 | Optional Orca adapter, no dependency by default | Disabled seam present | Optional smoke only after safe scope; native no-Orca must work |
| PR-12 | Hardening, Windows/Linux release, docs and artifacts | Reported RC package exists historically | ALL E01–E23 + independent QA + green checks + tag/release approval |

Do not delete or rename historical stage IDs. Current GitHub PR #3 combining many stages does not waive per-stage acceptance tests or scope reviews.

## Dependency/implementation order

`PR-00 → 01 → 02 → 03 → 03b → 04a → 04b → 05 → 06 → (07,08) → 09 → 10 → [11 optional] → 12`.

**Recommended workstream sequencing from the existing repo:** baseline/CI → integrity and approval vulnerabilities → persistent control-plane state → actual dispatch and tool execution → router/provider integration → QA end-to-end → E18/E22/E23 → release. Stages may be reworked without changing immutable history; each fix should be a small, verifiable change.

## Phase milestones for next development

| Milestone | Scope | Exit outcome |
| --- | --- | --- |
| S-00 CI restore | Docs contract, PR #2 CI/BVE foundations | New-head green Windows/Linux test suites + correct immutable checkout |
| S-01 Critical safety | Approval rejection finality, receipt forgery, recovery/fix-round/secret protections | All relevant negative tests pass; no premature VERIFIED |
| S-02 Durable orchestration | Persist runs/tasks/dispatch and budget scope; workspace separation | Restart/idempotence/multi-workspace tests, 100% traceable submissions |
| S-03 Live native journey | Antigravity/stdio `submit_goal` → actual PM/Dev/QA; local 9Router | Real supervised end-to-end at exact SHA, correct token usage |
| S-04 Independent verification | E01–E23, adversarial E18, Windows E22, remote E23; independent QA | No skipped required checks, clean-room evidence and explicit verdict |
| S-05 Release | Clean merges, packaging, documentation, license, tag/release | Human-approved signed/immutable release with checksums |

## Release criteria

No claim of production readiness, stable autonomy or completed roadmap until all blocking code reviews, CI, gate scenarios, end-to-end runs, independent verifier and human decisions are closed with actual evidence. `AUTONOMY: OFF` remains the current product posture; future autonomous operation would be a **separately gated new milestone** only if AG-1 is demonstrably satisfied.
