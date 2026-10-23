"""native_runtime.py — Supervised Native Execution Engine (PR-03b, PR-04, PR-06, PR-09).

Implements the real supervised lifecycle:
submit_goal
  -> PM task decomposition
  -> frozen acceptance criteria
  -> controlled developer dispatch
  -> ToolExecutor
  -> trustworthy execution receipts
  -> independent QA
  -> final result

Under governance invariants:
- AUTONOMY: OFF
- GATE_MODE: CHAT_APPROVAL
- CONFINEMENT: RISK_ACCEPTED_SAME_IDENTITY
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
from typing import Mapping, Sequence

from subagentbridge.composition import ProductionSystem
from subagentbridge.domain.contracts import Role, Run, Task
from subagentbridge.domain.registry import Principal
from subagentbridge.execution.isolation.runner import IsolatedExecutionRunner
from subagentbridge.execution.tool_executor.supervised import SupervisedReadOnlyExecutor
from subagentbridge.models.nine_router import CallBudget
from subagentbridge.storage.sqlite_store import SQLiteStore
from subagentbridge.team.coordinator import SupervisedCoordinator
from subagentbridge.workspaces.scope import ScopedWorkspace


def resolve_tree_sha(workspace_path: Path) -> str:
    """Resolve the git tree SHA or compute a deterministic SHA256 fallback."""
    try:
        res = subprocess.run(  # nosec B603
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=str(workspace_path),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    # Deterministic fallback: hash directory contents or return stable tree SHA
    hasher = sha256()
    try:
        for p in sorted(workspace_path.rglob("*")):
            if p.is_file() and not p.is_symlink() and ".git" not in p.parts:
                hasher.update(str(p.relative_to(workspace_path)).encode("utf-8"))
                try:
                    hasher.update(p.read_bytes()[:65536])
                except Exception:
                    pass
    except Exception:
        pass
    digest = hasher.hexdigest()
    return digest if digest != sha256().hexdigest() else ("0" * 40)


def check_clean_checkout(workspace_path: Path) -> bool:
    """Verify whether workspace checkout is genuinely clean without uncommitted changes."""
    try:
        res = subprocess.run(  # nosec B603
            ["git", "status", "--porcelain"],
            cwd=str(workspace_path),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if res.returncode == 0:
            ignored_prefixes = (
                ".subagentbridge",
                "store.db",
                "audit.db",
                ".pytest_cache",
                "__pycache__",
                ".ruff_cache",
            )
            dirty_lines = [
                line.strip()
                for line in res.stdout.strip().splitlines()
                if line.strip() and not any(
                    ig in line for ig in ignored_prefixes
                )
            ]
            return len(dirty_lines) == 0
    except Exception:
        pass
    return False


class TaskDecomposer:
    """PM Task Decomposer: breaks a high-level goal into an ordered, frozen DAG."""

    @staticmethod
    def decompose_goal(
        goal: str,
        run_id: str,
        tree_sha: str,
        policy_revision: str = "v1",
    ) -> tuple[dict[str, Task], dict[str, tuple[str, ...]], list[dict]]:
        """Decompose goal into PM, Developer, and QA tasks with explicit criteria and dependencies."""
        pm_task_id = f"{run_id}_pm"
        dev_task_id = f"{run_id}_dev"
        qa_task_id = f"{run_id}_qa"

        pm_task = Task(
            task_id=pm_task_id,
            run_id=run_id,
            acceptance_criteria=(f"Scope and acceptance criteria defined for: {goal.strip()}",),
            tree_sha=tree_sha,
            policy_revision=policy_revision,
        )
        dev_task = Task(
            task_id=dev_task_id,
            run_id=run_id,
            acceptance_criteria=(
                f"Implementation satisfies {goal.strip()}",
                "Pass invariant test suite",
                "Clean working tree",
            ),
            tree_sha=tree_sha,
            policy_revision=policy_revision,
        )
        qa_task = Task(
            task_id=qa_task_id,
            run_id=run_id,
            acceptance_criteria=(
                "Independent QA verification passes with clean checkout and valid receipts",
            ),
            tree_sha=tree_sha,
            policy_revision=policy_revision,
        )

        tasks = {
            pm_task_id: pm_task,
            dev_task_id: dev_task,
            qa_task_id: qa_task,
        }
        dependencies: dict[str, tuple[str, ...]] = {
            pm_task_id: (),
            dev_task_id: (pm_task_id,),
            qa_task_id: (dev_task_id,),
        }

        task_records = [
            {
                "task_id": pm_task_id,
                "run_id": run_id,
                "title": "Analyze requirements and freeze acceptance criteria",
                "status": "PENDING",
                "role": "PM",
                "dependencies": [],
                "evidence_ids": [],
            },
            {
                "task_id": dev_task_id,
                "run_id": run_id,
                "title": f"Implement: {goal.strip()}",
                "status": "PENDING",
                "role": "DEVELOPER",
                "dependencies": [pm_task_id],
                "evidence_ids": [],
            },
            {
                "task_id": qa_task_id,
                "run_id": run_id,
                "title": "Independent QA verification and receipt review",
                "status": "PENDING",
                "role": "QA",
                "dependencies": [dev_task_id],
                "evidence_ids": [],
            },
        ]

        return tasks, dependencies, task_records


class SupervisedNativeLifecycle:
    """Supervised native execution lifecycle coordinator."""

    def __init__(
        self,
        sys: ProductionSystem,
        workspace_path: Path | str,
        store: SQLiteStore | None = None,
        confinement: str = "RISK_ACCEPTED_SAME_IDENTITY",
    ) -> None:
        self.sys = sys
        self.workspace_path = Path(workspace_path).resolve()
        self.store = store
        self.confinement = confinement
        self.scoped_workspace = ScopedWorkspace(self.workspace_path)
        self.runner = IsolatedExecutionRunner(self.workspace_path, confinement=self.confinement)
        self.inspection_executor = SupervisedReadOnlyExecutor(self.workspace_path)

    def _ensure_principals(self, run_id: str) -> tuple[Principal, Principal, Principal, Principal]:
        """Ensure unique, typed principals are registered in IdentityRegistry for the run."""
        identities = self.sys.identities
        # Use run-scoped principal IDs to prevent collisions across runs
        pm_id = f"pm_{run_id}"
        dev_id = f"dev_{run_id}"
        qa_id = f"qa_{run_id}"
        exe_id = f"executor_{run_id}"

        pm = identities.register(pm_id, Role.PM)
        dev = identities.register(dev_id, Role.DEVELOPER)
        qa = identities.register(qa_id, Role.QA)
        executor = identities.register(exe_id, Role.EXECUTOR)
        return pm, dev, qa, executor

    def create_coordinator_for_run(
        self,
        run_id: str,
        tasks: Mapping[str, Task],
        dependencies: Mapping[str, tuple[str, ...]],
        policy_revision: str = "v1",
    ) -> tuple[SupervisedCoordinator, tuple[Principal, Principal, Principal, Principal]]:
        """Instantiate SupervisedCoordinator and register run principals."""
        pm, dev, qa, executor = self._ensure_principals(run_id)
        run_obj = Run(run_id=run_id, project_id=self.workspace_path.name, policy_revision=policy_revision)

        coordinator = SupervisedCoordinator(
            run=run_obj,
            tasks=tasks,
            dependencies=dependencies,
            identities=self.sys.identities,
            receipts=self.sys.receipts,
            budget=self.sys.budget,
            qa_test_hashes=self.sys.qa_gate.test_hashes,
        )
        self.sys.coordinator = coordinator
        return coordinator, (pm, dev, qa, executor)

    def execute_lifecycle(
        self,
        run_id: str,
        coordinator: SupervisedCoordinator,
        principals: tuple[Principal, Principal, Principal, Principal],
        task_records: list[dict],
        command_map: Mapping[str, Sequence[str]] | None = None,
        provider_terms_approved: bool = False,
        consult_model: bool = False,
        model_id: str | None = None,
    ) -> dict:
        """Execute the full DAG of tasks under supervision, receipts, and QA review."""
        pm, dev, qa, executor = principals
        record_map = {r["task_id"]: r for r in task_records}
        commands = dict(command_map or {})

        if self.store is not None and self.store.get_run(run_id) is None:
            self.store.upsert_run({
                "run_id": run_id,
                "goal": "Native lifecycle execution",
                "workspace_path": str(self.workspace_path),
                "status": "IN_PROGRESS",
                "model": "default",
            })

        for task_id in coordinator.order:
            task_contract = coordinator._tasks[task_id].task
            record = record_map[task_id]

            # 1. Freeze acceptance criteria
            coordinator.freeze(task_id, pm)
            record["status"] = "FROZEN"
            if self.store is not None:
                self.store.upsert_task(record)
            self._log_event(run_id, f"freeze:{task_id}", "TASK_FROZEN", {"task_id": task_id})

            # 2. Begin dispatch (reserve budget)
            idempotency_key = f"dispatch:{run_id}:{task_id}"
            dispatch_plan = coordinator.begin(
                task_id,
                pm=pm,
                idempotency_key=idempotency_key,
                token_allowance=500,
                cost_microunits=10000,
            )
            record["status"] = "DISPATCHED"
            if self.store is not None:
                self.store.upsert_task(record)
                self.store.upsert_dispatch({
                    "dispatch_id": dispatch_plan.dispatch_id,
                    "task_id": task_id,
                    "attempt": 1,
                    "idempotency_key": idempotency_key,
                    "tree_sha": dispatch_plan.tree_sha,
                    "policy_revision": dispatch_plan.policy_revision,
                    "status": "DISPATCHED",
                })
            self._log_event(
                run_id,
                f"dispatch:{dispatch_plan.dispatch_id}",
                "TASK_DISPATCHED",
                {"task_id": task_id, "dispatch_id": dispatch_plan.dispatch_id},
            )

            # 3. Load role skills as instructional content
            role_skills = self.sys.skills.get_skills_for_role(record.get("role", "DEVELOPER"))
            for sk in role_skills:
                try:
                    self.sys.skills.load_harness_content(sk)
                except Exception:
                    pass

            # Optional model consultation under D-02 review gate
            if consult_model:
                if not provider_terms_approved:
                    return {
                        "status": "FAILED",
                        "run_id": run_id,
                        "failed_task_id": task_id,
                        "reason": "D-02 provider terms review required before model invocation",
                    }
                chosen_model = model_id or (
                    self.sys.nine_router.models.models[0].model_id
                    if self.sys.nine_router.models and self.sys.nine_router.models.models
                    else "default"
                )
                budget = CallBudget(requests=1, tokens=500)
                try:
                    chat_res = self.sys.nine_router.chat(
                        model_id=chosen_model,
                        messages=(
                            {"role": "system", "content": f"Task Role: {record.get('role', 'DEVELOPER')}"},
                            {"role": "user", "content": f"Execute task: {record.get('title', task_id)}"},
                        ),
                        max_tokens=250,
                        budget=budget,
                        provider_terms_approved=True,
                        max_retries=1,
                    )
                    self._log_event(
                        run_id,
                        f"model_chat:{task_id}",
                        "MODEL_CONSULTED",
                        {
                            "task_id": task_id,
                            "model": chosen_model,
                            "usage_class": chat_res.usage_class,
                            "prompt_tokens": chat_res.prompt_tokens,
                            "completion_tokens": chat_res.completion_tokens,
                        },
                    )
                except Exception as exc:
                    self._log_event(
                        run_id,
                        f"model_err:{task_id}",
                        "MODEL_ERROR",
                        {"task_id": task_id, "error": str(exc)},
                    )

            # 4. Developer execution under ToolExecutor supervision
            cmd = commands.get(task_id) or commands.get(record.get("role", "")) or commands.get("default")
            if not cmd:
                record["status"] = "FAILED"
                if self.store is not None:
                    self.store.upsert_task(record)
                self._log_event(run_id, f"no_cmd:{task_id}", "COMMAND_MISSING", {"task_id": task_id})
                return {
                    "status": "FAILED",
                    "run_id": run_id,
                    "failed_task_id": task_id,
                    "reason": f"no developer command provided for execution of task {task_id}; synthetic exit code is prohibited",
                }

            try:
                result = self.runner.run_isolated(cmd, timeout_seconds=30)
                exit_code = result.exit_code
            except Exception:
                exit_code = 1

            if exit_code != 0:
                record["status"] = "FAILED"
                if self.store is not None:
                    self.store.upsert_task(record)
                return {
                    "status": "FAILED",
                    "run_id": run_id,
                    "failed_task_id": task_id,
                    "reason": f"process execution failed with exit code {exit_code}",
                }

            # 5. Developer reports process succeeded (with genuine exit_code == 0)
            coordinator.report_process_succeeded(
                developer=dev,
                task_id=task_id,
                dispatch_id=dispatch_plan.dispatch_id,
                tree_sha=dispatch_plan.tree_sha,
            )
            record["status"] = "PROCESS_SUCCEEDED"
            if self.store is not None:
                self.store.upsert_task(record)
            self._log_event(
                run_id,
                f"proc_succ:{dispatch_plan.dispatch_id}",
                "PROCESS_SUCCEEDED",
                {"task_id": task_id, "dispatch_id": dispatch_plan.dispatch_id},
            )

            # 6. ToolExecutor issues trustworthy execution receipt from actual execution
            receipt = self.sys.receipts.issue(
                executor,
                task_id=task_id,
                dispatch_id=dispatch_plan.dispatch_id,
                tree_sha=dispatch_plan.tree_sha,
                exit_code=exit_code,
            )
            evidence = self.sys.receipts.create_evidence(
                receipt.receipt_id,
                task_id=task_id,
                dispatch_id=dispatch_plan.dispatch_id,
                tree_sha=dispatch_plan.tree_sha,
            )

            # 7. Independent QA review
            # Inspect actual tree SHA and verify clean checkout without synthetic claims
            is_clean = check_clean_checkout(self.workspace_path)
            current_tree_sha = resolve_tree_sha(self.workspace_path)

            # Read actual QA test hashes from disk
            actual_test_hashes: dict[str, str] = {}
            for rel_path in self.sys.qa_gate.test_hashes:
                test_file = (self.workspace_path / rel_path).resolve()
                if test_file.is_file():
                    actual_test_hashes[rel_path] = sha256(test_file.read_bytes()).hexdigest()
                else:
                    actual_test_hashes[rel_path] = "0" * 64

            # Execute qualifying QA tests
            qa_passed = False
            qa_test_files = [
                str(self.workspace_path / rel_path)
                for rel_path in self.sys.qa_gate.test_hashes
                if (self.workspace_path / rel_path).is_file()
            ]
            if qa_test_files:
                import sys as _sys
                try:
                    qa_run = self.runner.run_isolated(
                        [_sys.executable, "-m", "pytest", *qa_test_files],
                        timeout_seconds=30,
                    )
                    qa_passed = (qa_run.exit_code == 0)
                except Exception:
                    qa_passed = False

            covered_criteria = task_contract.acceptance_criteria if qa_passed else ()

            decision = coordinator.qa_review(
                qa=qa,
                task_id=task_id,
                evidence=(evidence,),
                covered_criteria=covered_criteria,
                actual_test_hashes=actual_test_hashes,
                actual_tree_sha=current_tree_sha,
                clean=is_clean,
                fix_round=0,
            )

            if decision.status == "QA_VERIFIED":
                record["status"] = "VERIFIED"
                record["evidence_ids"] = [evidence.evidence_id]
                if self.store is not None:
                    self.store.upsert_task(record)
                self._log_event(
                    run_id,
                    f"qa_ver:{dispatch_plan.dispatch_id}",
                    "TASK_VERIFIED",
                    {
                        "task_id": task_id,
                        "dispatch_id": dispatch_plan.dispatch_id,
                        "evidence_id": evidence.evidence_id,
                    },
                )
            else:
                record["status"] = decision.status
                if self.store is not None:
                    self.store.upsert_task(record)
                return {
                    "status": "FAILED",
                    "run_id": run_id,
                    "failed_task_id": task_id,
                    "reason": decision.reason,
                }

        return {
            "status": "COMPLETED",
            "run_id": run_id,
            "tasks": list(record_map.values()),
        }

    def _log_event(self, run_id: str, idempotency_key: str, event_type: str, payload: dict) -> None:
        try:
            self.sys.ledger.append_once(
                stream=f"run:{run_id}",
                idempotency_key=f"{idempotency_key}:{run_id}",
                event_type=event_type,
                payload=payload,
            )
        except Exception:
            pass
