# PR-00 — Verified-Source Baseline and Decision Packet

**Status:** DRAFT / UNVERIFIED. This report is based on GitHub source retrieval and commit comparison, **not** a clone, test execution, or independent verifier.

## Source of truth
- Target repository: `rzqllh/SubagentBridge`.
- Baseline main SHA (GitHub commit search and compare): `2a467bd4a82c65a30931554acef879fda9794a5f`.
- Baseline commit: `chore: import SubagentBridge baseline`.
- The baseline commit file list exposes 20 tracked files, with no `tests/`, `pyproject.toml`, or CI workflow in **main**.
- Existing branch `hardening/m2.5-runtime-safety` is **9 commits ahead of main**, 0 behind. It contains `pyproject.toml`, `tests/test_agy_runner.py`, `agy_runner.py`, and a skill/bootstrap. Do not discard or automatically merge it. Its test explicitly expects `--dangerously-skip-permissions`; this is not compatible with autonomous enforcement.
- The README's "implementation not yet started" is stale: on main, `subagentbridge/server.py`, `manager.py`, `storage/sqlite_store.py` exist.
- The concrete runner registry on main is empty (`_REGISTRY = {}`); runners cannot be claimed working from the tool definitions alone.
- No runtime, Windows, Linux, Antigravity, 9Router, CI, or security verification was performed in this PR-00 document stage.

## Threat-model and legacy code observations (source only)
1. `server.py` exposes LLM-callable `approve_action`; there is no human-origin proof in the function.
2. `spawn_agent` defaults to `skip_permissions=True`; `manager.Session` also defaults to True.
3. `PendingActionQueue.is_gated` string-matches `tool_call` events after subprocess output. This is not pre-execution interception.
4. `check_path_in_workspace` accepts any registered session workspace. There are no per-dispatch/role ACLs.
5. `Session.kill` calls `_process.kill()`; no proven Windows child process tree teardown.
6. Retry safety is a text reminder, not exactly-once execution or idempotency control.
7. `rehydrate` resets persisted `working` sessions to idle without proving process reconciliation.
8. SQLite persistence is mutable by the host user. WAL does not provide cryptographic integrity or append-only OS protection.
9. `docs/PRD.md` specifies dated model names and API wrappers as design proposals, not verified runtime compatibility.
10. No baseline tests in the main commit listing; tests on the hardening branch must be audited separately.

## First PR scope (proposed; split into phases)
**PR-00A, staged in this draft:** upload the original governing documents without editing their content; copy Team Rules byte-for-byte; document baseline and unresolved security/protocol conflicts. No production-code changes.

**PR-00B, requires exact human approval before edits:** reconcile README/docs; add a standard-library `unittest` fake runner and deterministic non-network baseline tests; define Windows/Linux CI workflow and dependency installation policy. Treat every unsupported gate as expected failure/unverified; never falsify a green gate.

Out of scope: worker autonomy, 9Router, Orca adapter, real approval broker, OS sandbox, QA certification. This is contract/bootstrap only.

## Proposed acceptance criteria
- [ ] TEAM_RULES text equals human source SHA-256: `aa9e843bb2c13a369c5a26f4932f48418cf4b407e0e3a6659aaab5659f86272b`; verify locally from a Git checkout.
- [ ] Original Plan v2 text equals SHA-256: `03650c37da206dcfbc31505a6e2e0e0723d3203ac9157070b3c3bb9c2957dab6`; verify locally from a Git checkout.
- [ ] Original verifier and goal files are also preserved as reference artifacts; the proposed addendum does not silently override v2.
- [ ] Main/hardening branch inventory, working baseline, and unsupported guarantees are documented with source pointers.
- [ ] Independent verifier derives test cases before reading implementation narrative, runs tests on a clean checkout, and records actual command/exit/output/tree evidence.
- [ ] For full PR-00B: Windows/Linux CI and isolated baseline tests must be witnessed, not assumed.
- [ ] Every file or dependency change that falls under Team Rules §1 has separate operation-specific approval.

## Proposed Human Decision Packet DP-00 (NOT YET APPROVED)
The user explicitly authorized staging the uploaded documents to GitHub and starting PRs one at a time. That authorization covers **only document staging and creation of a draft PR**. It is *not* operation-specific approval for modifying CI/dependencies, autonomous workers, release, merge, or any push of implementation.

For PR-00B the human must decide:
1. **Scope:** permit modifying `README.md`, baseline documentation and new `tests/` using stdlib `unittest` (no additional Python package for tests).
2. **CI:** permit a new GitHub Actions workflow `.github/workflows/ci.yml`; first show its exact contents before any change, including triggers, read-only token permissions, Windows and Ubuntu runner images, install steps, and test commands.
3. **Dependency/install:** prefer no new packages; if an existing dependency must be installed from a new upstream host, request approval specifying provider, pinned version, license, and network host before action.
4. **Git operations:** approve each precisely identified implementation commit/push and eventual merge as separate one-time gate. **This draft PR must not be merged yet.**
5. **Verification:** designate a fresh, separate verifier session/model, or record `INDEPENDENCE: LIMITED` and require human diff review.

## Explicit evidence limitations
`NOT PERFORMED`: git clone, `git status --porcelain` on a local checkout, Python tests, lint, CI runs, 9Router smoke, Antigravity IDE smoke, independent verification, or sandbox bypass tests. This environment cannot resolve github.com for container git. GitHub connector read, branch, and document-write operations are not equivalent to running tests.

**STATUS: UNVERIFIED.** The draft is a staging checkpoint and decision record, not an accepted PR-00.
