"""Production composition root for SubagentBridge (PR-03b, PR-10, INV-12).

Auditable assembly of real subsystems:
- AuditLedger (WAL-mode SQLite)
- DurableBudgetLedger (persisted transaction budgets)
- DurableMessageBus (idempotent message transport)
- LocalSkillRegistry (SHA-256 pinned skills)
- PolicyClassifier (fail-closed policy gate)
- SupervisedReadOnlyExecutor (4MiB bounds, workspace isolation)
- NineRouterClient (local loopback AI router)
- IdentityRegistry & ReceiptIssuerRegistry (typed principal boundaries)
- QaEvidenceGate (exact-tree evidence adjudication)
- SupervisedCoordinator (DAG team orchestrator)

Strictly denies fake principals or mock runners in production.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from subagentbridge.domain.contracts import Role, Run, Task
from subagentbridge.domain.registry import IdentityRegistry, ReceiptIssuerRegistry
from subagentbridge.execution.tool_executor.supervised import SupervisedReadOnlyExecutor
from subagentbridge.models.capability import ModelCapabilities, ModelRoutingTable
from subagentbridge.models.nine_router import LocalRouterConfig, NineRouterClient
from subagentbridge.messaging.bus import DurableMessageBus
from subagentbridge.planner.budget import DurableBudgetLedger
from subagentbridge.policy.classification import GateDecision, OperationRequest, classify
from subagentbridge.qa.adjudication import QaEvidenceGate
from subagentbridge.skills.registry import LocalSkillRegistry
from subagentbridge.storage.audit_ledger import AuditLedger
from subagentbridge.team.coordinator import SupervisedCoordinator

_FORBIDDEN_IDENTITIES = frozenset({"fake", "fake_runner", "fake_principal", "mock", "dummy", "untrusted"})


class PolicyClassifier:
    """Object interface over the pure fail-closed policy classification function."""

    @staticmethod
    def classify(request: OperationRequest) -> GateDecision:
        return classify(request)


@dataclass(slots=True)
class ProductionSystem:
    workspace_root: Path
    db_path: Path
    ledger: AuditLedger
    budget: DurableBudgetLedger
    bus: DurableMessageBus
    skills: LocalSkillRegistry
    classifier: PolicyClassifier
    executor: SupervisedReadOnlyExecutor
    identities: IdentityRegistry
    receipts: ReceiptIssuerRegistry
    qa_gate: QaEvidenceGate
    nine_router: NineRouterClient
    coordinator: SupervisedCoordinator | None = None

    def close(self) -> None:
        """Close underlying SQLite connections cleanly to prevent handle leaks."""
        try:
            self.budget.close()
        finally:
            self.ledger.close()


def build_production_system(
    workspace_root: str | Path,
    db_path: str | Path | None = None,
    nine_router_base_url: str = "http://127.0.0.1:9099",
    nine_router_api_key: str = "production-local-key",
    tokens_budget: int = 50000,
    cost_microunits: int = 1000000,
    max_workers: int = 3,
    runner_name: str = "native",
    principal_role: str = "DEVELOPER",
    custom_qa_hashes: Mapping[str, str] | None = None,
    custom_skill_pins: Mapping[str, str] | None = None,
) -> ProductionSystem:
    """Build and wire an auditable production system without fake principals or mock runners."""
    # 1. Reject fake principals and mock runners
    norm_runner = runner_name.strip().lower()
    norm_role = principal_role.strip().lower()
    if any(forbidden in norm_runner for forbidden in _FORBIDDEN_IDENTITIES):
        raise ValueError(f"production composition root rejects fake runner {runner_name!r}")
    if any(forbidden in norm_role for forbidden in _FORBIDDEN_IDENTITIES):
        raise ValueError(f"production composition root rejects fake principal {principal_role!r}")

    root_path = Path(workspace_root).resolve()
    if not root_path.exists():
        root_path.mkdir(parents=True, exist_ok=True)

    if db_path is None:
        db_file = root_path / ".subagentbridge" / "production_audit.db"
    else:
        db_file = Path(db_path).resolve()
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # 2. Wire core storage, budget, and message bus
    ledger = AuditLedger(db_file)
    budget = None
    try:
        budget = DurableBudgetLedger(
            db_path=db_file,
            tokens=tokens_budget,
            cost_microunits=cost_microunits,
            max_workers=max_workers,
        )
        bus = DurableMessageBus(ledger, stream="production_system_stream")

        # 3. Wire skills registry (using workspace .skills or empty default pins)
        skills_dir = root_path / ".skills"
        if not skills_dir.exists():
            skills_dir.mkdir(parents=True, exist_ok=True)
        skill_pins = dict(custom_skill_pins or {})
        skills = LocalSkillRegistry(skills_dir, pins=skill_pins)

        # 4. Wire policy classifier and supervised tool executor
        classifier = PolicyClassifier()
        executor = SupervisedReadOnlyExecutor(root_path)

        # 5. Wire typed identities and receipts
        identities = IdentityRegistry()
        receipts = ReceiptIssuerRegistry(identities)

        # 6. Wire QA evidence gate
        qa_pins: dict[str, str] = dict(custom_qa_hashes or {})
        if not qa_pins:
            test_path = "tests/test_invariants_contract.py"
            real_test = root_path / test_path
            if real_test.is_file():
                import hashlib
                qa_pins[test_path] = hashlib.sha256(real_test.read_bytes()).hexdigest()
            else:
                qa_pins[test_path] = "0" * 64

        qa_gate = QaEvidenceGate(
            receipts=receipts,
            frozen_criteria=("AC-1: deterministic verification",),
            qa_test_hashes=qa_pins,
        )

        # 7. Wire 9Router local adapter
        router_config = LocalRouterConfig(
            base_url=nine_router_base_url,
            api_key=nine_router_api_key,
        )
        model_cap = ModelCapabilities(
            model_id="default",
            tool_calls=True,
            structured_output=True,
            streaming=True,
            input_cost_known=True,
            output_cost_known=True,
        )
        routing_table = ModelRoutingTable([model_cap])
        nine_router = NineRouterClient(config=router_config)
        nine_router.models = routing_table

        # 8. Create production system container
        return ProductionSystem(
            workspace_root=root_path,
            db_path=db_file,
            ledger=ledger,
            budget=budget,
            bus=bus,
            skills=skills,
            classifier=classifier,
            executor=executor,
            identities=identities,
            receipts=receipts,
            qa_gate=qa_gate,
            nine_router=nine_router,
            coordinator=None,
        )
    except BaseException:
        if budget is not None:
            budget.close()
        ledger.close()
        raise
