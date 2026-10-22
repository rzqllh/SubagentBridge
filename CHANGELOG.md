# Changelog

## Simpul documentation update — 2026-10-23

Public branding is now **Simpul**. The default branch still contains the historical SubagentBridge baseline. PR #2 (baseline recovery) and PR #3 (unreleased 1.0.0rc1 candidate) remain open; no code release, merge or security certification is implied. See [SIMPUL_STATUS.md](docs/SIMPUL_STATUS.md).

The older roadmap notes below are historical proposals, not a statement of current implementation.


## [Unreleased]

### Planned for v0.1.0
- Core session manager (own implementation): `spawn_agent`, `send_message`,
  `wait_for_idle`, `get_agent_status`, `list_agents`, `get_model_usage`,
  `apply_code_fix`, `kill_agent`.
- Fix: `wait_for_idle` kills the subprocess on timeout instead of abandoning it.
- Fix: bounded auto-retry (default 2 attempts, exponential backoff) on
  non-zero exit.
- Fix: `apply_code_fix` hard-fails when no workspace is registered, no
  fallthrough.
- New: real HITL approval gate — `approve_action` / `reject_action` tools.
- New: `agy` and `claude` runners (parity with upstream).
- New: `gpt_sol` and `deepseek` runners.
- Docs: PRD, architecture, weakness tracker, API reference, runner spec,
  security notes, test plan, third-party notices.
