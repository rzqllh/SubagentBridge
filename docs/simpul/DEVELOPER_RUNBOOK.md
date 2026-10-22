# Simpul — Next-developer runbook and copy-ready review packet

**Entry mode:** supervised, serial, no Hermes subagents during roadmap re-verification. **`AUTONOMY: OFF`**. Operate on an explicit workspace, one scoped task at a time. No source, CI, dependency, network, merge, or release mutation without relevant human gate.

## 1. Establish actual truth first

On a Windows development machine:

~~~powershell
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git remote -v
git log -5 --oneline
git diff --stat
~~~

Compare expected GitHub PR head and tree, not just branch name. A previously reported SIMPUL-01 execution claimed edits while `HEAD`/`TREE` were unchanged and worktree clean. Reproduce `git diff`, hash and `git show` before accepting that claim.

Relevant GitHub links: [PR #2](https://github.com/rzqllh/SubagentBridge/pull/2), [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3), [last red run](https://github.com/rzqllh/SubagentBridge/actions/runs/39866552770).

## 2. Fastest safe next task

**SIM-001 (documentation assertion; bundled in this packet)**: inspect `tests/test_pr00_source_doc_truth.py` and `docs/API_REFERENCE.md`. The latter must accurately contain the literal `Removed from MCP exposure by P0 lockdown` and `legacy worker execution is **disabled`. Validate locally:

~~~powershell
python -m unittest tests.test_pr00_source_doc_truth -v
python -m unittest discover -s tests -p "test_*.py" -v
~~~

Only when this packet's new CI has run may you mark SIM-001 closed. Do not change the test to mask a documentation drift. If other CI failures appear, capture logs and reclassify.

## 3. Next implementation slices

1. Resolve PR #2 merge conflicts and 3 Codex findings with explicit human approval for touching CI, preserve `main` public docs; do not merge as part of a troubleshooting session.
2. Fix PR #3 P1 fail-closed defects first: approval rejection finality, forged receipt, sticky recovery, fix-loop cap, audit failure, ledger identity. Each fix gets regression evidence.
3. Persist MCP run/task state and wire real `submit_goal`→coordinator→worker lifecycle, with one workspace per production system.
4. Resolve 9Router authentication and provider-terms scope, then establish local supervised native workflow.
5. Close P2 replay and extra-env leaks, test cross-workspace security.
6. Independent E18/E21/E22/E23 and actual Antigravity E2E; rerun every modified test on new exact SHA.
7. Review release readiness and only then request human merge/tag/publish decisions.

Never implement different stages in one unreviewable ad-hoc patch; keep small reviewable commits and clean evidence. Changes to tests or CI require their own prior approval.

## 4. Required test stack (after human approval for installs/CI)

~~~powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m unittest discover -s artifacts/bootstrap/v3_1/tests -p "test_*.py" -v
python -m unittest tests.test_acceptance_matrix_e01_e21 -v
python -m ruff check subagentbridge
python -m mypy subagentbridge
python -m bandit -r subagentbridge -lll
~~~

These commands are *verification instructions*, not claims they ran today. Availability/version/policy for ruff, mypy, bandit and dependencies must be checked before installing. E21 BVE `selftest` and E22/23 need separate exact-tool commands/independent logs according to Plan v3.1. On Windows, provide actual clean venv, stdio MCP and child-process evidence. Skipped required tests make the relevant gate `UNVERIFIED`.

## 5. Verification/review packet template (produce after **every** milestone)

~~~text
PROJECT: Simpul
MILESTONE: SIMPUL-XX / SIM-XXX
DATE_UTC: YYYY-MM-DDTHH:MM:SSZ
REPOSITORY: rzqllh/SubagentBridge
BRANCH: <branch>
BASE_SHA: <40-hex>
HEAD_SHA: <40-hex>
TREE_SHA: <40-hex>
WORKTREE: clean | dirty
ACTUAL_CHANGED_FILES: <paths from git diff / git show>
SCOPE: <approved objective>
OUT_OF_SCOPE: <not changed>
GATE_MODE: CHAT_APPROVAL
AUTONOMY: OFF
INDEPENDENCE: INDEPENDENT | LIMITED | NONE
EVIDENCE_AUTHORITY: <executor / independent QA, not model prose>
TEST_MATRIX: <command | platform | exit code | pass/fail/skip | log path | log hash>
REGRESSION_EVIDENCE: <before/after + negative cases>
CODEx_REVIEW: <finding ID | addressed? link to code/tests/thread>
ACCEPTANCE_E01_E23: <each in scope, PASS/FAIL/UNVERIFIED/BLOCKED>
SECURITY_UNCERTAINTIES: <precise unknowns>
STATUS: VERIFIED | UNVERIFIED | BLOCKED
EVIDENCE: <real artifacts, SHA/tree, log paths, commands, exit codes>
UNCERTAINTY: <known gaps>
DECISIONS: <specific recorded decisions>
NEEDS HUMAN: <exact approvals/blockers>
UNVERIFIED_CLAIMS: <none or explicit>
NEXT_TASK: <one bounded slice>
~~~

A source diff, an answer from a coding agent, and a test report are different things; do not substitute one for another. QA must be independent of implementer and tests. Full QA verdict is issued only if the verifier executed it against that HEAD, not by summarizing somebody else's output.

## 6. Final merge and publication sequence

**No merges yet.** Once every relevant gate is independently verified: (a) reconcile and human-approve PR #2 into `main`; (b) rebase/re-target PR #3 safely without losing documentation/source history, and revalidate new exact HEAD; (c) human-approve PR #3 merge; (d) reproducible build/clean-install, checksums, release notes, optional signature, release approval; (e) publish GitHub release. A "mergeable" badge only confirms Git merge mechanics, not CI or quality.

## 7. Maintaining this packet

At each real milestone, update [BACKLOG.md](BACKLOG.md), [ROADMAP.md](ROADMAP.md), [ACCEPTANCE_GATES.md](ACCEPTANCE_GATES.md), [STATUS_AND_HISTORY.md](STATUS_AND_HISTORY.md) in the same documented change. Do not mark `VERIFIED` unless source SHA and independent evidence have been refreshed. Never remove unresolved historical Codex threads merely for appearance.
