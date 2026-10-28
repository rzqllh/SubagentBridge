> **CURRENT PUBLIC RELEASE:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4) (28 October 2026), exact `main` SHA `3be6e3b58c444ad7afcbff5ed42efa62b9cbbab2`, [4/4 CI](https://github.com/rzqllh/SubagentBridge/actions/runs/40622640492) and [release workflow with verified build attestation SUCCESS](https://github.com/rzqllh/SubagentBridge/actions/runs/40623111287). The older v1.1.0/v1.1.1 receipts and commands below are preserved for historical audit, **not the current installation instructions**. Use [public v1.1.4 Antigravity installation guide](../public/GETTING_STARTED.md). E18 and authenticated human-approval issues remain BLOCKED.

# Simpul — Release Readiness and Operator Guide

> **Published release:** [Simpul v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1) · 27 October 2026 · merged main SHA `861f040dc12c33da681331e454ef41299f2dc70b` · workflow 40444832484 SUCCESS. E18 remains BLOCKED.

## Scope

The C00–C07 stacked change set brings native Python Lead/Worker orchestration contracts, independent OS worker processes and JSONL IPC, local capability-checked harness routing, durable dispatch and priority queue, authenticated message/handoff checks, checkpoint recovery, Git worktree ownership, and migration from legacy `orca_*` tables to `simpul_*`.

The full development history is in [the parity audit](SIMPUL_CINDY_PARITY_REPORT.md). PRs #9–#12 were merged individually; PR #16 integrated C04–C07, while #13–#15 were closed as superseded after confirming their commits were included.

## Install v1.1.1

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.1
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m subagentbridge.server
```

The last command launches an MCP stdio server, **not** a chat UI. On macOS/Linux use `.venv/bin/python`. For supported reproduction, use the immutable published `v1.1.0` tag rather than a historical feature branch.

## Developer verification gate

Run in a checked-out release commit:

```bash
python -m pip install -e .
python -m pip install ruff==0.14.0 mypy==1.18.2 bandit==1.9.4
python -m pytest tests artifacts/bootstrap/v3_1/tests -rs
python -B -m unittest discover -s tests -p "test_*.py"
python -m ruff check --select E4,E7,E9,F subagentbridge
python -m mypy --ignore-missing-imports --check-untyped-defs subagentbridge
python -m bandit -q -r -ll subagentbridge
```

Require passing CI on the **exact commit to be merged** for all four combinations: Windows/Ubuntu and Python 3.11/3.13. Distinguish `skipped` tests from tests actually exercised. Treat review comments as open until explicitly resolved.

## Operating constraints and security

- `AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`: no unattended privileged command, merge, tag or release.
- E18: `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`. Lead and workers share an OS account; filesystem and process sandboxing between those processes is **not** provided.
- Model-supplied `approved: true`, self-reported exit code, or a handoff summary is **not** human authority or execution provenance.
- External host adapters declare capabilities; not all are independently verified against a real external session.
- Worktree deletion must preserve dirty, ignored, locked and unknown-owned paths. No force cleanup or raw recursive deletion.
- SQLite migration uses an online logical backup before destructive table transformation, independent optional-column mapping, explicit transaction rollback, and legacy read-only views. Backups remain operator-owned files and must not be silently overwritten.
- Task recovery may be *at-least-once* after ambiguous external side effects. Resume must rebind the exact dispatch, task, worker, team, commit and workspace, then revalidate observed artifacts.

## Merge and release criteria

A release is only eligible when all relevant correctness and review findings are closed, all stacked PRs merge without lost commits or unsafe force updates, merged `main` passes the complete CI matrix, distribution/version metadata matches the intended tag, documentation reflects actual published behavior, and an authorized operator approves release. Create the release from that tested `main` SHA, attach changelog and release receipts, then perform a clean-environment install smoke test.

Before deleting local worktrees, inspect their individual Git status, ignored files, branch ownership, tags, active PRs, and any SQLite backups. Never assume a green PR test authorizes deleting a user's workspace.

## Attribution

Simpul is independently implemented in Python and does not bundle Cindy source code. Cindy's architecture was studied for its multi-worker coordination patterns. See [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md), including the upstream project and pinned research revision. The release must preserve the notice. 

## Publication receipt

- GitHub Release [v1.1.0](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.0), published 27 October 2026.
- Main merge commit: `a29f0d98957651e482fbae989a906bb09873f329`.
- Candidate CI: 40440192101, 4/4 PASS; tested tree SHA `36551fe8faa25bd4c2886db0c41c8d4cab7bd39c` matches main merge tree.
- Release workflow: [40440851542](https://github.com/rzqllh/SubagentBridge/actions/runs/40440851542), SUCCESS.
- Assets: wheel, source archive, SHA256SUMS.txt.
- E18 same-user OS confinement remains BLOCKED (accepted risk), not a kernel sandbox.

## v1.1.1 runtime integrity publication receipt

- [Release v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1), released from exact `861f040dc12c33da681331e454ef41299f2dc70b`.
- PR #19 candidate CI [4/4 PASS](https://github.com/rzqllh/SubagentBridge/actions/runs/40444244325) on Windows/Ubuntu Python 3.11/3.13. Merged `main` source tree matches the tested PR tree.
- Release workflow [40444832484](https://github.com/rzqllh/SubagentBridge/actions/runs/40444832484): SUCCESS; wheel, sdist and SHA256SUMS published.
- Correctness: SQLite shared read/write lock, serialized cross-process resume, trusted approval renewal/preflight, fail-closed ambiguous recovery, child Python safe-path hardening.
- Non-goals: no same-user kernel sandboxing (E18 BLOCKED), no external authenticated human-approval UI, no verified enterprise workload certification.
