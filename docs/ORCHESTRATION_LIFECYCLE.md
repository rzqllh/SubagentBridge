# SubagentBridge: Agent Orchestration and Lifecycle

This document describes how SubagentBridge coordinates specialized roles: Project Manager (PM), Developer, and Quality Assurance (QA).

---

## 1. Role Boundaries and Identity Isolation

Each agent role operates under a registered identity with explicit, non-overlapping responsibilities:

```
[ Human Principal ]
        |
        v (Submits Goal & Policy Revision)
   [ PM Agent ]
        |
        +---> Creates Tasks & Freezes Acceptance Criteria
        |
   [ Developer Agent ]
        |
        +---> Implements Changes
        +---> Executes Supervised Read-Only Tool / Test Runs
        +---> Obtains ExecutorReceipt bound to Git Tree SHA
        |
   [ QA Agent ] (Independent Verifier)
        |
        +---> Evaluates ExecutorReceipt against Frozen Criteria
        +---> Validates Clean Git Working Tree
        +---> Issues Cryptographic QaVerdict (Accepted or Rejected)
        |
        v
[ Verified / Blocked State ]
```

---

## 2. Task State Machine Transitions

Tasks advance through strictly defined states:
1. `CREATED`: Initial task definition created by PM.
2. `FROZEN`: Acceptance criteria locked and hashed; cannot be mutated by workers.
3. `DISPATCHED`: Assigned to a Developer worker with an idempotency key.
4. `PROCESS_SUCCEEDED`: Worker process completed with exit code 0.
5. `QA_VERIFIED`: Independent QA verified all criteria against exact tree SHA.
6. `BLOCKED`: Three fix rounds exhausted without agreement, or human gate required.
7. `RECOVERY_REQUIRED`: Worker crashed or power failure occurred during execution.

---

## 3. Disagreement Protocol and 3-Round Termination (Scenario E02)

To prevent infinite rework loops and runaway token expenditure:
- If Developer output fails QA verification, QA returns an unaccepted verdict with detailed test failure evidence.
- The system permits up to 3 fix cycles (`fix_round = 1, 2, 3`).
- If round 3 fails to produce an accepted QA verdict, the task transitions immediately to `BLOCKED`.
- Execution stops and requires explicit human developer intervention.

---

## 4. Git Tree Binding and Verification Invalidation (Scenario E04)

All `ExecutorReceipt` and `QaVerdict` records are bound to the exact Git tree SHA:
- Any file modification, touch, or branch switch alters the Git tree SHA.
- The `QaEvidenceGate` compares the expected tree SHA with the current tree SHA.
- If a mismatch occurs, or if the repository checkout is dirty, prior verification is automatically revoked and state reverts to `UNVERIFIED`.
