# Simpul — Current project status

**As of:** 28 October 2026  
**Published:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4) · **release/main SHA:** `3be6e3b58c444ad7afcbff5ed42efa62b9cbbab2`  
**Verification:** [main 4/4 Ubuntu/Windows CI success](https://github.com/rzqllh/SubagentBridge/actions/runs/40622640492) · [published build/attestation release workflow SUCCESS](https://github.com/rzqllh/SubagentBridge/actions/runs/40623111287)  
**Package and MCP technical name:** `subagentbridge`; product brand: **Simpul**.

## Primary purpose

Simpul is a **native-first supervised multi-worker subagent supervisor** whose **primary intended MCP host is Google Antigravity IDE**. It takes selected architectural cues from Cindy and Orca (lead/worker sessions, dispatch, queue, messaging, handoff and worktrees), **not a claim of full upstream parity or shipped IDE-native UI**. The native Python core works without Orca.

Current primary guides: [Antigravity installation and first use](public/GETTING_STARTED.md), [public parity/roadmap](public/PARITY_AND_ROADMAP.md), [MCP tool reference](API_REFERENCE.md).

## Delivered in the public v1.1.4 line (bounded verification)

- Native lead/worker typed contracts and real worker subprocess IPC/PID tracking.
- SQLite-backed session/task/queue persistence, inter-agent messages, worktrees, checkpoint recovery and verified handoff checks.
- Supervised PM → Developer → QA domain lifecycle and MCP goal, task, evidence and cancellation tools. The default `submit_goal` handler records a run; it **does not** imply unrestricted autonomous coding.
- Explicit policy/default-deny approvals; optional verified operator adapter with action-specific challenge and legacy-grant migration. **No production external WebAuthn/OIDC relying party or trusted human approval UI is shipped.**
- Per-decision and per-consumption durable SQLite compare-and-swap to prevent stale supervisory approvals and ticket replay.
- Opt-in strict distinct-worker OS identity policy, with unsupported same-user/Windows-UI-only modes refusing strict identity claims.
- Protected `main` ruleset; public wheel, sdist, checksum, GitHub/Sigstore build attestation with verification before publication.

## Still blocked / not enterprise-ready

| Issue / scope | Current verdict | What remains |
|---|---|---|
| [#21 — E18 hostile-worker isolation](https://github.com/rzqllh/SubagentBridge/issues/21) | **BLOCKED** | Real Windows/Linux OS-privilege separation and repeatable adversarial host negative tests |
| [#22 — independent human approval](https://github.com/rzqllh/SubagentBridge/issues/22) | **BLOCKED** | Production WebAuthn/OIDC RP, operator UI and independent action/role attestation |
| [#23 — enterprise operations](https://github.com/rzqllh/SubagentBridge/issues/23) | **PARTIAL** | Signed dependency SBOM, real restore/rollback and long-running chaos/soak, independent acceptance |
| Exact Orca/Cindy or Antigravity UX parity | **PARTIAL / NOT PROVEN** | Real upstream semantic comparison and installed-IDE end-to-end acceptance for relevant versions |

**Operating policy:** `AUTONOMY: OFF`, `GATE_MODE: CHAT_APPROVAL`, default same-user security limitation `RISK_ACCEPTED_SAME_IDENTITY`. No unattended privileged modification or artificial claim that fixture approval tests authenticate humans. Replaying ambiguous side effects after a crash requires trusted reconciliation.

## Release files

[Release v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4) includes:
- `subagentbridge-1.1.4-py3-none-any.whl`
- `subagentbridge-1.1.4.tar.gz`
- `SHA256SUMS.txt`

Historical phase evidence and earlier versions remain in the [Cindy/Orca execution report](simpul/SIMPUL_CINDY_PARITY_REPORT.md) and [developer roadmap](simpul/ROADMAP.md). Those are history and planning artifacts, not proof of complete current parity.
