# Active bootstrap baseline: v3.1 (ratified planning contract)

- Repository: `rzqllh/SubagentBridge`; bootstrap PR: [#1](https://github.com/rzqllh/SubagentBridge/pull/1).
- Source branch at DP-00B approval: `feat/00-baseline-and-contracts`, HEAD `3fae42707d175e1ab1723c29ffcfb6c565a326f8` before this PR-00B commit.
- Human approved **v3.1 as a planning baseline**, then separately approved DP-00B Operations A and B in chat. Approval does **not** include merge, dependency change, production runtime change or enabling autonomy.
- Governing rules: `docs/TEAM_RULES.md`. Original content SHA-256 `aa9e843bb2c13a369c5a26f4932f48418cf4b407e0e3a6659aaab5659f86272b`.
- Pinned Plan v3.1: `candidate/Xyeena_SubagentBridge_Production_PR_Plan_v3_1.md`. SHA-256 `2b840256eb488cbaf1a404bf33ca28a2686b7b34cf062a4c26bb5c0fe7c39f0a`.
- Goal: `candidate/Xyeena_SubagentBridge_ANTIGRAVITY_GOAL_v3_1.md`; verifier prompt: `candidate/Xyeena_SubagentBridge_VERIFIER_PROMPT_v3_1.md`; helper: `candidate/bve_tool.py`, SHA-256 `30db221b6f665cb61a1054bb972b1155fa66633ea6af4f35681f83d9c3f919c6`.
- Exact v3.1 bootstrap artifact pins are checked by `tests/test_bootstrap_v31.py`. Older documents are archived as provenance and are not rewritten.
- Phase A: chat approval, self-attested; BVE requires a separate verifier session. Product `ExecutorReceipt` is not present. `AUTONOMY: OFF`.
- CI checks are baseline-only. Expected failures in invariant/security contract tests are outstanding work, **not** QA verification.

**NOT PERFORMED:** a clean independent verifier run against final PR HEAD, real Windows runtime security, 9Router/Antigravity integration, or Orca smoke. No enterprise-ready claim.
