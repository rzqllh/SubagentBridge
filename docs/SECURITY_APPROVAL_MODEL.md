# SubagentBridge: Human Approval and Security Model

This document outlines the Human-in-the-Loop (HITL) approval architecture, policy classifier, and replay protection mechanisms.

---

## 1. Approval Broker Architecture (`ApprovalBroker`)

SubagentBridge implements an isolated approval broker adhering to Decision D-03:

1. **Operation Fingerprinting:** When an action requiring approval is detected, the broker creates a pending `ApprovalAction` with an immutable fingerprint:
   - Target operation name
   - Command line arguments (`argv`)
   - Target resource path
   - Session and dispatch identifiers
2. **One-Time Token Authentication:** Resolving an approval requires a high-entropy secret token (`auth_token`). Workers do not possess this secret.
3. **Replay Protection:** Once an action is approved or denied, its state transitions permanently to `APPROVED` or `REJECTED`. Replaying an approved token on the same action raises a `PermissionError`.
4. **Pre-Execution Gate:** Approvals occur **before** execution. Post-execution log observation is never treated as human authorization.

```python
from subagentbridge.approval.broker import ApprovalBroker, ApprovalState

broker = ApprovalBroker(broker_secret="high-entropy-secret-key")

# Worker registers proposed action:
action = broker.create_action(
    session_id="session-1",
    operation="git.push",
    resource="origin/main",
)

# Human resolves the action out-of-band:
resolved = broker.resolve_by_human(
    action.action_id,
    approved=True,
    auth_token="high-entropy-secret-key",
)
assert resolved.state == ApprovalState.APPROVED
```

---

## 2. Policy Classifier Gate Categories

The conservative `classify()` function analyzes requested operations into distinct categories:

| Gate Category | Sensitive Triggers | Action Taken |
|---|---|---|
| `AUTH_OR_SECRET` | Token writing, credential access | Gate required: human approval |
| `DEPENDENCY` | `pip install`, `npm install`, modifying lockfiles | Gate required: human approval |
| `CI_OR_DEPLOY` | Workflow modification, CI script changes | Gate required: human approval |
| `DESTRUCTIVE` | `rm -rf`, file deletion, table drop | Gate required: human approval |
| `GIT_PUSH_OR_REWRITE` | `git push`, history rewrite, branch force | Gate required: human approval |
| `NETWORK_EGRESS` | External network calls, remote URLs | Gate required: human approval |
| `OUTSIDE_WORKSPACE_WRITE`| Writes targeting parent directories | Gate required: human approval |
| `QA_OR_ACCEPTANCE_CHANGE`| Modifying test files in `tests/` | Gate required: human approval |
| `READ_ONLY_REQUEST` | Pure reads within workspace boundaries | Permitted without gate |
| `UNKNOWN` | Unrecognized commands, ambiguous payload | Gate required: fail closed |

---

## 3. Autonomy Gate Status

- Current setting: `AUTONOMY: OFF`
- Decision D-01: Phase A supervised development under `RISK_ACCEPTED_SAME_IDENTITY`.
- Decision D-03: Phase A chat-based approval under `GATE_MODE: CHAT_APPROVAL`.
- Full autonomous operation remains strictly disabled until out-of-band OS-level user isolation is fully realized.
