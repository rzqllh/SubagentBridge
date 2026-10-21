# SubagentBridge: Architecture Specification

This document details the production architecture of SubagentBridge across its domain contracts, composition root, persistence layer, execution boundary, and verification gates.

---

## 1. System Architecture Overview

```
                      +-----------------------------+
                      |   Antigravity IDE (Host)    |
                      +-----------------------------+
                                     |  MCP (stdio)
                                     v
                      +-----------------------------+
                      |    Production MCP Server    |
                      |  (subagentbridge/server.py) |
                      +-----------------------------+
                                     |
               +---------------------+---------------------+
               |                     |                     |
               v                     v                     v
    +--------------------+  +--------------------+  +--------------------+
    |  Durable Audit &   |  |   Approval Broker  |  |  Production Root   |
    |   Budget Ledgers   |  | (One-Time Tokens)  |  |   (composition.py) |
    +--------------------+  +--------------------+  +--------------------+
               |                     |                     |
               |                     |                     v
               |                     |              +--------------------+
               |                     |              | Policy Classifier  |
               |                     |              +--------------------+
               |                     |                     |
               v                     v                     v
    +--------------------------------------------------------------------+
    |                       Agent Manager Engine                         |
    |          PM Role  --->  Developer Role  --->  QA Role              |
    +--------------------------------------------------------------------+
               |                     |                     |
               v                     v                     v
    +--------------------+  +--------------------+  +--------------------+
    | Local 9Router      |  | Supervised Tool    |  | QA Evidence Gate   |
    | Loopback (127.0.0.1|  | Executor & Runner  |  | (Tree SHA Binding) |
    +--------------------+  +--------------------+  +--------------------+
```

---

## 2. Component Subsystems

### 2.1 Production Composition Root (`subagentbridge/composition.py`)
Provides deterministic dependency injection for the entire system:
- `AuditLedger`: WAL-mode SQLite storage tracking all state transitions and crash recovery.
- `DurableBudgetLedger`: SQLite transaction-serialized budget ceilings and worker concurrency tracking.
- `ApprovalBroker`: High-entropy token approval manager with replay protection.
- `SupervisedReadOnlyExecutor`: Verified read-only execution creating `ExecutorReceipt`s.
- `QaEvidenceGate`: Multi-party adjudication verifying frozen criteria against exact Git trees.
- `NineRouterClient`: Model capability routing restricted to `127.0.0.1` loopback transport.
- `LocalSkillRegistry`: SHA-256 pinned skill reader preventing directory traversal.

### 2.2 Domain Data Contracts (`subagentbridge/domain/contracts.py`)
Immutable slots dataclasses representing application entities:
- `Run`: Scoped execution project and policy revision.
- `Task`: Atomic unit of work with frozen, unique acceptance criteria.
- `Dispatch`: Idempotent execution attempt bound to a specific tree SHA.
- `Evidence`: Transport representation linking receipts to task trees.
- `Approval`: Audit record of human authorization.

### 2.3 Execution Isolation (`subagentbridge/execution/isolation/runner.py`)
Executes commands in isolated subdirectories:
- Environment scrubbing removes all broker secrets and API keys.
- Process trees are monitored and terminated within timeouts on Windows.
- Standard error and standard output are hashed and recorded.

### 2.4 Human Approval Broker (`subagentbridge/approval/broker.py`)
- Pre-execution policy enforcement.
- Model-callable approval signatures are removed from the MCP surface.
- Actions can only be authorized via out-of-band high-entropy tokens.
- Replaying a used token fails closed.

### 2.5 Local 9Router Loopback Transport (`subagentbridge/models/nine_router.py`)
- Restricted exclusively to loopback addresses (`127.0.0.1`).
- Fails closed when model capabilities are missing or unverified.
- Zero unauthorized external network egress.
