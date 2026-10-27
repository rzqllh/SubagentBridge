## C07 security posture (27 October 2026)

Authorization is **default-deny**. A model-originated approval boolean or QA claim is not trusted provenance. Worker commands require a cryptographically bound, single-use ticket from an authenticated approval authority; automated test fixtures do not constitute a production human interface. Task resume must return `AWAITING_APPROVAL` when the human decision is still blocked, not dispatch a command. Alive OS PIDs without owned IPC streams must be treated as unattached. E18 same-user OS confinement remains `BLOCKED (RISK_ACCEPTED_SAME_IDENTITY)`; never describe it as kernel isolation. See [release readiness](simpul/RELEASE_READINESS.md).

# Simpul — Human approvals and security boundary

**Status: development candidate, not security certified.** The code implements `ApprovalBroker` token and operation-fingerprint logic, but a malicious worker using the same OS identity may be able to access secrets or UI state. Its unit tests are **not** E18 adversarial isolation evidence.

## Policy and intended decisions

- D-01: `RISK_ACCEPTED_SAME_IDENTITY` — supervised Phase-A risk acceptance, **not** OS isolation.
- D-03: `CHAT_APPROVAL` — human decisions must be explicit and operation-bound. Chat messages are not automatically an authenticated out-of-band channel.
- D-02: text model client restricted to literal HTTP loopback origins; upstream 9Router behavior requires separate assessment.
- `AUTONOMY: OFF`. No Always Allow, timeout auto-approval, model self-approval, or unauthorized test/CI/dependency changes.

## What exists in candidate code

The policy classifier identifies sensitive changes (credentials, dependencies, git writes/pushes, QA/test changes, network and out-of-scope paths) and fails closed for unknown operations. The `ApprovalBroker` module includes operation fingerprints, high-entropy token validation and replay rejection. These checks are useful controls but do not substitute for isolation of the approving human from untrusted workers.

`approve_action` is **not an MCP tool**; the preserved Python compatibility function denies requests. `reject_approval` is an MCP tool because denial cannot confer access. Do not interpret `get_pending_approvals` or `reject_approval` as proof that authorization is secure or complete.

## Required independent validation before autonomy

- E18: attempt realistic same-OS-user secret stealing, forged approval, UI automation and broker-origin spoofing; test the worker's actual privilege boundary.
- E22: attempt checkout/workspace traversal, symlink/junction and race escapes from the real worker integration.
- E23: reproduce an exact pinned remote checkout in a clean independent environment.
- Verify end-to-end operation-specific approval enforcement **before** execution, not by reading logs after tool execution.
- Verify arbitrary build/test subprocess containment under a genuinely separate security principal for unattended mode.

No known documentation-only modification closes any of these conditions. See [Project Status](SIMPUL_STATUS.md) and [Execution Confinement](TOOL_EXECUTOR_CONFINEMENT.md).
