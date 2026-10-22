# Simpul — Development source of truth

**Snapshot:** 2026-10-23 · **Product:** Simpul (formerly SubagentBridge) · **Repository:** [rzqllh/SubagentBridge](https://github.com/rzqllh/SubagentBridge) · **Development branch:** `integrate/roadmap-v4-verified` / [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3).

This is the next-developer handoff compiled from the project's governing Plan v3.1, repository source, GitHub CI/PR review and historical Simpul conversations. It is **a plan and evidence index, not a claim that pending work is complete**. Baseline examined: `a9840e5af80f18c43db88a01f7a2413fc559f891` before this documentation packet. Any new source commit invalidates earlier SHA-bound QA results.

## Open this packet in order

1. [STATUS_AND_HISTORY.md](STATUS_AND_HISTORY.md) — state of PRs, CI, what past reports did and did not prove, SIMPUL-01 discrepancies.
2. [ROADMAP.md](ROADMAP.md) — the canonical 15-stage PR-00..PR-12 plan, execution dependencies and release phases.
3. [BACKLOG.md](BACKLOG.md) — actionable P0/P1/P2 work, code areas, exit criteria and Codex findings.
4. [ACCEPTANCE_GATES.md](ACCEPTANCE_GATES.md) — E01–E23, INV-01–12, AG-1 and evidence requirements.
5. [ARCHITECTURE_AND_INTEGRATIONS.md](ARCHITECTURE_AND_INTEGRATIONS.md) — intended runtime flow vs real source, 9Router, Antigravity, skills/harness, Orca, Xyeena Rig boundary.
6. [GOVERNANCE_AND_DECISIONS.md](GOVERNANCE_AND_DECISIONS.md) — hard rules, human approval decisions, prohibitions.
7. [DEVELOPER_RUNBOOK.md](DEVELOPER_RUNBOOK.md) — exact next-session commands, sequencing, review packet, verification, handoff.

## Non-negotiable status

- **Do not merge PR #3 now.** Its last reviewed GitHub Actions run had four red platform jobs due to one baseline documentation contract assertion; CI must rerun green on the *new* HEAD.
- The baseline code has substantive open P1/P2 review findings; a green CI alone would not close them.
- **`AUTONOMY: OFF`**, `GATE_MODE: CHAT_APPROVAL`, `RISK_ACCEPTED_SAME_IDENTITY`. This is **not** OS isolation or proof of secure same-user human approval.
- E18 adversarial broker proof, E22 checkout-root containment, E23 live remote-pinned verifier checkout, real Antigravity E2E and authenticated live 9Router remain blocking evidence.
- Python module, distribution, CLI, configuration prefix and MCP server identifier remain `subagentbridge` / `SUBAGENTBRIDGE_*` for backward compatibility. Rebranding does not authorize breaking API changes.

## Source precedence

1. Explicit current human decisions and `docs/TEAM_RULES.md`; exact, recorded approval gates.
2. Checked-out source, exact SHA/tree, executed independent logs and current GitHub checks.
3. Canonical `artifacts/bootstrap/v3_1/candidate/Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md`; acceptance changes require a separately authorized decision.
4. This derivative tracker.
5. Historical developer reports, automated reviews and conversations are **evidence or proposed tasks**, not independent QA/approval.

**Important:** the older Plan's `PR-00–PR-12` numbering is a roadmap-stage system, not GitHub PR numbers. The current GitHub PR #2 carries PR-00 recovery, and GitHub PR #3 combines candidate stages. Preserve original plan and history rather than rewriting them.

## Change management

Update this packet after each meaningful verified milestone. Mark an item verified only with a linkable review packet recording HEAD SHA, tree SHA, test command, exit code, evidence log/hash, actual independent verifier and unresolved caveats. No auto-merge, no retconning review reports, no implied permission to modify source/tests/CI/dependencies or deploy from this packet.
