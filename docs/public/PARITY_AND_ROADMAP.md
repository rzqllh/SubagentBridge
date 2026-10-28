# Simpul — Antigravity-first subagent roadmap and Orca/Cindy parity

**Status: public v1.1.4, 28 October 2026.** This is a **feature/evidence map**, not a promise that all Orca/Cindy features or native IDE integrations are present.

## Product direction

**Primary host: Google Antigravity IDE.** Simpul is designed as a **native-first, supervised multi-worker subagent supervisor** connected through MCP stdio. Antigravity is the *front-end host* where the user initiates supervised work; Simpul is the *control plane* that manages roles, worker subprocesses, queues, permissions, evidence, and recovery. It is **not** an alternative IDE, a new built-in Antigravity UI, or an unrestricted coding autopilot.

**References and provenance:**
- **Cindy:** architectural reference for lead/worker coordination, session lifecycle, dispatch, queues, messages, handoffs, and worktrees. Simpul independently implements these patterns in Python. [Historical detailed comparison](../simpul/SIMPUL_CINDY_PARITY_REPORT.md) · [Upstream credit](../../THIRD_PARTY_NOTICES.md).
- **Orca:** optional adapter/compatibility and legacy `Orca*` API / `orca_*` migration names. The core does **not** require Orca installed. Reference similarity is not protocol or behavior equivalence.
- **Antigravity:** primary MCP IDE target. Actual IDE-level end-to-end version acceptance must be tested separately from unit tests and host capability declarations.

## Parity snapshot (v1.1.4)

| Capability / parity target | Present in Simpul | Not yet proven / important limit |
|---|---|---|
| Lead/worker identities and lifecycle | Typed sessions, teams, worker statuses and ownership | No guaranteed exact match to every Cindy/Orca UI behavior |
| Native workers | Real OS subprocesses, PID tracking and IPC | Same-user workers are **not isolated hostile-code sandboxes** (E18) |
| Dispatch, queue and messaging | SQLite persisted tasks, priorities, dedup, steering, handoffs | Not a blanket guarantee of exactly-once external side effects |
| Workspace management | Git worktrees, worker assignment, safe cleanup checks | Worktrees are not an OS permissions boundary |
| Checkpoint / recovery | Durable checkpoints and fail-closed reconciliation | Ambiguous side effects need human reconciliation |
| Multi-harness support | Native and capability-declared Antigravity, Codex, Claude Code, Pi adapters | A declared adapter is not a live host E2E acceptance certificate |
| MCP control in Antigravity IDE | MCP stdio server with `submit_goal`, readback, execution and evidence tools | No built-in Simpul editor/worker sidebar; real IDE workflow not independently signed off |
| Human permission model | Default-deny, one-use IPC grants, opt-in action-bound decision-verifier API | No production WebAuthn/OIDC relying party or trusted operator UI (#22) |
| Supply chain | v1.1.4 exact-main four-platform CI, signed build attestations, checksums | Signed dependency SBOM / host acceptance / restoration soak incomplete (#23) |

**No percentage parity claim:** these categories represent **bounded implemented core functions**, not complete API/UX equivalence with current upstream. Historical phase labels `C00–C07 COMPLETE` apply to their documented acceptance scope, not to complete Cindy/Orca parity or native Antigravity experience.

## What using the released version looks like

```text
Human → Antigravity IDE Agent panel
      → Simpul MCP stdio (subagentbridge.server)
      → supervised run / role & policy coordination
      → native worker processes, queue, handoffs, Git worktrees
      → evidence, checkpoint and QA reporting
```

A user must configure the MCP server in Antigravity IDE (see [install and first use](GETTING_STARTED.md)). After connection, they can submit goals, inspect task status and evidence, and run **only** authorized supervised commands. The existence of the native team Python APIs does not mean every team operation is exposed as a model-callable MCP tool, nor does `submit_goal` automatically invoke a complete safe autonomous coding crew.

## Next development milestones (not automatically approved)

1. **Antigravity host parity:** an externally reproducible end-to-end install, tool discovery, goal→PM→Developer→QA run, observability and recovery in a real IDE build. Add a clear operator-facing experience without claiming unsupported native IDE hooks.
2. **Orca/Cindy behavior parity:** verify real session/team creation, delegation/steering, queue race behavior, role isolation, handoff and long-running interruption against the pinned source/evidence matrix. Implement differences by bounded PR, not by borrowing unsupported claims.
3. **Hostile-worker security, issue #21:** separately privileged Windows worker identity / process+filesystem+network restrictions, Linux OS-enforced sandbox and host-negative adversarial evidence. Until then, **AUTONOMY: OFF**.
4. **Genuine human approvals, issue #22:** independently trusted WebAuthn/OIDC, action-specific user intent and replay prevention, authenticated approval UX, real E2E receipts. Current challenge-verifier fixture is *not* an IdP.
5. **Release and resilience, issue #23:** restore, chaos/soak, external side-effect reconciliation, signed dependency-accurate SBOM, independent acceptance. Do not label enterprise-ready without evidence.

The historical detailed phase plan remains [Roadmap v3.1](../simpul/ROADMAP.md) and [Parity Execution Report](../simpul/SIMPUL_CINDY_PARITY_REPORT.md). Those documents preserve the 2026 implementation history and should **not** be mistaken for live release status. Current runtime-facing documentation is [Public Docs](README.md), [MCP integration](../MCP_INTEGRATION.md) and [Enterprise Readiness](../ENTERPRISE_READINESS.md).
