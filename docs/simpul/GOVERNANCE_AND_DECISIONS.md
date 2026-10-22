# Simpul — Governance, decision register, approval boundaries

This is an implementation handoff summary; it **does not replace** [Team Rules](../TEAM_RULES.md) or grant new authorizations.

## Existing decisions / hard restrictions

| Key | Existing decision | Required behavior |
| --- | --- | --- |
| AUTONOMY | **OFF** | No unattended privileged source edits, testing arbitrary untrusted code or merge/release automation |
| D-01 | **`RISK_ACCEPTED_SAME_IDENTITY`, Phase A supervised** | Risk disclosure: *no isolation*; cannot meet autonomy AG-1 |
| D-02 | **local-only 9Router loopback** | No unauthorized external provider network egress; upstream provider terms checked/approved separately |
| D-03 | **`CHAT_APPROVAL`, Phase A** | Explicit human decisions; no "Always Allow", agent-issued approval, UI bypass or timeout auto-approval |
| Native first | Orca adapter **optional**, default OFF | No Orca required for E01; never nested Orchestration |
| QA authority | Issued ExecutorReceipt + independent QA on exact tree | No QA VERIFIED from pasted stdout, PM assertion or screenshot |
| User SIMPUL-01 verification mode | **Hermes subagents OFF, serial work** | Don't spawn PM/Developer/QA/Orca or external workers merely to audit roadmap |
| Evidence | Exact SHA/tree + real command logs | Clean worktree alone does not prove code changed; no fake claims |
| Merge/release | Human only, after fresh verification | "Ready to merge" means no merge conflict, not safety acceptance |

### Scope and human decision packet

A reviewer must request a new scoped approval **before** any change to: authentication/credentials/broker, schema/migrations/data deletion, dependency install/upgrade/license, CI workflow, deployment, new network host, writes outside workspace, git push/rewrite/merge, QA/acceptance test modification/waiver, or material product trade-off. A user request to create documentation authorizes that *specific* documentation work; it is not a blanket waiver of these gates for future source changes.

Approval question: short context; exact proposed operation and SHA/files; maximum three options if decision needed; impact, alternative and what is blocked. No approval by silence. A denial is final for that operation, including no replay after changing from reject→allow.

### Risk register

| Risk | Current evidence status | Safeguard / blocker |
| --- | --- | --- |
| Same-user worker can spoof approval or inspect secrets | **Not independently proven isolated** | Keep autonomy OFF; E18 adversarial test / separate identity or genuine out-of-band control |
| Worker-supplied receipt can appear verified | Codex P1 finding | SIM-105 plus E16/E17 acceptance |
| Approval rejection overwritten by later approval | Codex P1 finding | SIM-108 terminal-state regression |
| Unbounded/forged redo cycles | Codex P1 finding | SIM-107 persistent fix counter |
| Durable ledger cross-project bleed | Codex P1 finding | SIM-106 scoped identities; migration gate |
| Trusted-looking false submission | Codex P1 finding | SIM-102/103/104 implementation and fault injection |
| Env var credentials exposed through extra_env | Codex P2 finding | SIM-204 fail-closed filtering test |
| Unsafe direct CLI / arbitrary test execution | Same OS identity, tool allowlist not sandbox | No autonomy; separate identity proof before future autonomy |
| Documentation, CI and roadmap drifting apart | Doc contract CI regression | SIM-001 plus source/docs drift checks, independent proof |
| Local test fixture mistaken for remote checkout | SIMPUL-01 E22/E23 discrepancy | E23 true GitHub pinned checkout & verifier packet |

### Default operational bounds from Plan v3.1 (proposals until confirmed in active config)

`max_active_workers=3`, `max_peer_discussion_rounds=2`, `max_dev_qa_fix_cycles=3`, bounded dispatch retries, bounded tokens/cost, per-dispatch worktree, no unsolicited pushes/deletes. These are *design defaults*, not proof that the current MCP server enforces them across its entire path.

## Do not conflate historical approvals

Earlier DP-VERIFY authorizations covered read-only pinned checkout, offline testing and evidence logs within stated scopes, with **no source edit/install/push/merge/deploy**. They are not evergreen authorization. Prior PR-00 G1 ordering failure yielded REJECTED, even if some checks passed. Reopened review requires a fresh exact revision packet.

## Decision points still owned by human

- Whether/when to introduce isolated worker identities/out-of-band broker and turn on a future AG-1 design (not now).
- Any CI/workflow changes required by PR #2 or new dependency/license/provider terms.
- Merge order/conflict reconciliation and final tag/distribution publication.
- Any change to required E01–E23 acceptance or Team Rules. Failing criteria remain FAIL/BLOCKED, not waived silently.
