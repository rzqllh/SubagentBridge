# SubagentBridge

SubagentBridge is a native-first Model Context Protocol (MCP) subagent supervisor designed for Google Antigravity IDE and Windows development environments. It coordinates specialized Project Manager (PM), Developer, and Quality Assurance (QA) agents with durable SQLite audit persistence, cryptographic Git tree binding, one-time token human approvals, and local 9Router model routing.

---

## 1. Key Capabilities

- **Role-Based Orchestration:** Explicit lifecycle boundaries between PM (task decomposition), Developer (supervised implementation), and independent QA (evidence verification).
- **Cryptographic Tree Binding:** Every `ExecutorReceipt` and `QaVerdict` is bound to the exact Git tree SHA. Any dirty checkout or source modification revokes prior verification.
- **Human Approval Security:** Dangerous operations require one-time approval tokens issued through an out-of-band broker. Replay attempts and model self-approvals fail closed.
- **Durable Persistence:** SQLite WAL audit ledger and durable budget enforcement with atomic transaction serialization across restarts.
- **Local 9Router Integration:** High-performance loopback model transport (`127.0.0.1`) with capability negotiation that fails closed on unsupported models.
- **100% Native Independence:** Operates completely without Orca. An opt-in adapter is provided for environments that authorize external runners.

---

## 2. Release Status and Operating Boundaries

- **Current Version:** `v1.0.0-rc1` (Roadmap PR-00 through PR-12 verified).
- **Autonomy Posture:** `AUTONOMY: OFF`. Unattended privileged modifications are blocked.
- **Confinement Tier:** `RISK_ACCEPTED_SAME_IDENTITY` (Phase A supervised execution under Decision D-01).
- **Gate Mode:** `CHAT_APPROVAL` (Decision D-03).
- **Model Transport:** Loopback only (`127.0.0.1`, Decision D-02). Zero external network egress is initiated.

---

## 3. Windows-First Quick Start

### Prerequisites
- Windows 10/11 (64-bit) or modern Linux.
- Python 3.11, 3.12, or 3.13.
- Git in PATH.

### Installation (PowerShell)
```powershell
# Clone the repository
git clone https://github.com/rzqllh/SubagentBridge.git
Set-Location SubagentBridge

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install package
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

### Run Verification Suite
```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Expected output: 250 tests ran, 246 passed, 4 skipped (optional external endpoints), 0 errors, 0 failures.

---

## 4. Antigravity IDE Integration

Configure SubagentBridge in your Antigravity IDE MCP configuration:

```json
{
  "mcpServers": {
    "subagentbridge": {
      "command": "python",
      "args": [
        "-m",
        "subagentbridge.server"
      ],
      "env": {
        "SUBAGENTBRIDGE_DB_PATH": "subagentbridge.db",
        "SUBAGENTBRIDGE_GATE_MODE": "CHAT_APPROVAL",
        "SUBAGENTBRIDGE_ROUTER_URL": "http://127.0.0.1:8080/v1"
      }
    }
  }
}
```

---

## 5. Example PM -> Developer -> QA Lifecycle

```python
from subagentbridge.composition import create_production_system
from subagentbridge.domain.contracts import Role

# Initialize production system with durable SQLite storage
system = create_production_system(db_path="subagentbridge.db")

try:
    # 1. PM creates a task and freezes acceptance criteria
    task = system.create_task(
        task_id="task-001",
        run_id="run-001",
        criteria=("AC-1: Clean checkout", "AC-2: Tests pass exit 0"),
        tree_sha="current-tree-sha",
        policy_revision="rev-1",
    )

    # 2. Developer executes verified read-only test run
    receipt = system.executor.execute_read_only(
        ["python", "-m", "unittest", "tests/test_invariants_contract.py"],
        task_id="task-001",
        dispatch_id="disp-001",
        tree_sha="current-tree-sha",
    )

    # 3. Independent QA evaluates receipt and validates criteria
    qa_principal = system.identities.register("qa-agent", Role.QA)
    evidence = system.receipts.create_evidence(receipt.receipt_id, task_id="task-001", dispatch_id="disp-001", tree_sha="current-tree-sha")
    verdict = system.receipts.create_qa_verdict(
        qa_principal,
        evidence=(evidence,),
        task_id="task-001",
        dispatch_id="disp-001",
        tree_sha="current-tree-sha",
        accepted=True,
    )
    print("Task verified:", verdict.accepted)
finally:
    system.close()
```

---

## 6. Technical Documentation Index

- [Installation and Quick Start](docs/INSTALLATION_QUICKSTART.md)
- [Configuration and Environment Variables](docs/CONFIGURATION.md)
- [Architecture Specification](docs/ARCHITECTURE.md)
- [API Reference](docs/API_REFERENCE.md)
- [Human Approval and Security Model](docs/SECURITY_APPROVAL_MODEL.md)
- [Local 9Router Setup](docs/NINE_ROUTER_SETUP.md)
- [Antigravity MCP Integration](docs/MCP_INTEGRATION.md)
- [Agent Orchestration Lifecycle](docs/ORCHESTRATION_LIFECYCLE.md)
- [ToolExecutor and Confinement](docs/TOOL_EXECUTOR_CONFINEMENT.md)
- [Persistence and Recovery](docs/PERSISTENCE_RECOVERY.md)
- [Skills Registry and Trust](docs/SKILLS_REGISTRY.md)
- [Native Mode vs Optional Orca](docs/NATIVE_VS_ORCA.md)
- [Testing and QA Guide](docs/TESTING_QA_GUIDE.md)
- [Acceptance Matrix E01 to E21 Evidence](docs/ACCEPTANCE_MATRIX_E01_E21_EVIDENCE.md)
- [Compatibility and Limitations](docs/COMPATIBILITY_LIMITATIONS.md)
- [Troubleshooting and FAQ](docs/TROUBLESHOOTING_FAQ.md)
- [Developer Contribution Guide](docs/CONTRIBUTING.md)

---

## 7. Attribution and License

Design references and third-party notices are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Project license is in [LICENSE](LICENSE).
