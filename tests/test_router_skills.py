"""tests/test_router_skills.py — Verification suite for Phase P04 (Router & Skills).

Verifies:
1. Environment variable propagation to composition root preventing HTTP 401.
2. Model discovery and capability selection.
3. Bounded retries on transient router network failures.
4. D-02 enforcement (provider terms approval requirement).
5. Safe tool-call dispatch through SupervisedReadOnlyExecutor allowlist.
6. LocalSkillRegistry discovery, SHA-256 pinning, and tamper detection.
7. Role-based skill filtering and untrusted harness content loading.
8. MCP tools discover_models and list_skills.
9. SupervisedNativeLifecycle integration with skills and model routing.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest

from subagentbridge.composition import build_production_system
from subagentbridge.domain.contracts import Role
from subagentbridge.execution.native_runtime import (
    SupervisedNativeLifecycle,
    TaskDecomposer,
    resolve_tree_sha,
)
from subagentbridge.execution.tool_executor.supervised import SupervisedReadOnlyExecutor
from subagentbridge.models.capability import ModelCapabilities, ModelRoutingTable
from subagentbridge.models.nine_router import (
    CallBudget,
    JsonTransport,
    LocalRouterConfig,
    NineRouterClient,
    RouterUnavailable,
)
from subagentbridge.server import discover_models, list_skills, get_production_system, close_production_system
from subagentbridge.skills.registry import LocalSkillRegistry, SkillIntegrityError
from subagentbridge.storage.sqlite_store import SQLiteStore


class DummyTransport(JsonTransport):
    def __init__(self, responses: list[object] | None = None, fail_count: int = 0):
        self.responses = list(responses or [])
        self.fail_count = fail_count
        self.calls = []

    def request(self, *, config: LocalRouterConfig, method: str, path: str, payload: object) -> object:
        self.calls.append({"method": method, "path": path, "payload": payload})
        if self.fail_count > 0:
            self.fail_count -= 1
            raise RouterUnavailable("simulated transport connection failure")
        if self.responses:
            return self.responses.pop(0)
        return {"choices": [{"message": {"role": "assistant", "content": "dummy reply"}, "finish_reason": "stop"}]}


class TestRouterSkills(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name).resolve()

    def tearDown(self):
        close_production_system(self.workspace)
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_01_env_var_propagation_avoids_401(self):
        """Ensure NINE_ROUTER_BASE_URL and NINE_ROUTER_API_KEY propagate to composition root."""
        test_url = "http://127.0.0.1:9199"
        test_key = "secret-production-token-xyz"
        old_url = os.environ.get("NINE_ROUTER_BASE_URL")
        old_key = os.environ.get("NINE_ROUTER_API_KEY")
        try:
            os.environ["NINE_ROUTER_BASE_URL"] = test_url
            os.environ["NINE_ROUTER_API_KEY"] = test_key
            sys = get_production_system(self.workspace)
            self.assertEqual(sys.nine_router.config.base_url, test_url)
            self.assertEqual(sys.nine_router.config.api_key, test_key)
        finally:
            if old_url is not None:
                os.environ["NINE_ROUTER_BASE_URL"] = old_url
            else:
                os.environ.pop("NINE_ROUTER_BASE_URL", None)
            if old_key is not None:
                os.environ["NINE_ROUTER_API_KEY"] = old_key
            else:
                os.environ.pop("NINE_ROUTER_API_KEY", None)

    def test_02_model_discovery_and_selection(self):
        """Verify model discovery parses capabilities and allows capability-based selection."""
        config = LocalRouterConfig(base_url="http://127.0.0.1:9099", api_key="test-key")
        transport = DummyTransport(responses=[
            {
                "data": [
                    {
                        "id": "model-coder-v1",
                        "supported_parameters": ["tools", "response_format"],
                    },
                    {
                        "id": "model-fast-v1",
                        "supported_parameters": ["stream"],
                    },
                ]
            }
        ])
        client = NineRouterClient(config, transport=transport)
        models = client.discover()
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0].model_id, "model-coder-v1")
        self.assertTrue(models[0].tool_calls)
        self.assertTrue(models[0].structured_output)
        self.assertFalse(models[0].streaming)

        # Select by ID
        selected = client.models.select(["model-coder-v1"])
        self.assertEqual(selected.model_id, "model-coder-v1")

    def test_03_bounded_retries_on_transient_failure(self):
        """Verify NineRouterClient.chat retries transient failures up to max_retries."""
        config = LocalRouterConfig(base_url="http://127.0.0.1:9099", api_key="test-key")
        transport = DummyTransport(
            responses=[
                {
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "Success after retries"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 15, "completion_tokens": 8},
                }
            ],
            fail_count=2,
        )
        client = NineRouterClient(config, transport=transport)
        client.models = ModelRoutingTable([
            ModelCapabilities("m1", tool_calls=True, structured_output=True, streaming=True,
                              input_cost_known=False, output_cost_known=False)
        ])
        budget = CallBudget(requests=5, tokens=1000)

        # Retries = 1 should fail because 2 failures occur
        with self.assertRaises(RouterUnavailable):
            client.chat(
                model_id="m1",
                messages=({"role": "user", "content": "hi"},),
                max_tokens=100,
                budget=budget,
                provider_terms_approved=True,
                max_retries=1,
            )

        # Retries = 2 should succeed
        transport.fail_count = 2
        transport.responses = [
            {
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Success after retries"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 15, "completion_tokens": 8},
            }
        ]
        reply = client.chat(
            model_id="m1",
            messages=({"role": "user", "content": "hi"},),
            max_tokens=100,
            budget=budget,
            provider_terms_approved=True,
            max_retries=2,
        )
        self.assertEqual(reply.text, "Success after retries")
        self.assertEqual(reply.prompt_tokens, 15)
        self.assertEqual(reply.completion_tokens, 8)
        self.assertEqual(reply.usage_class, "actual")

    def test_04_d02_enforcement_denies_unapproved_model_invocation(self):
        """Verify chat raises PermissionError if provider_terms_approved is False."""
        config = LocalRouterConfig(base_url="http://127.0.0.1:9099", api_key="test-key")
        client = NineRouterClient(config, transport=DummyTransport())
        client.models = ModelRoutingTable([
            ModelCapabilities("m1", tool_calls=True, structured_output=True, streaming=True,
                              input_cost_known=False, output_cost_known=False)
        ])
        budget = CallBudget(requests=1, tokens=100)

        with self.assertRaises(PermissionError):
            client.chat(
                model_id="m1",
                messages=({"role": "user", "content": "hi"},),
                max_tokens=50,
                budget=budget,
                provider_terms_approved=False,
            )

    def test_05_safe_tool_execution_enforces_allowlist(self):
        """Verify execute_safe_tool_call allows safe read tools and denies unallowlisted tools."""
        config = LocalRouterConfig(base_url="http://127.0.0.1:9099", api_key="test-key")
        client = NineRouterClient(config, transport=DummyTransport())
        executor = SupervisedReadOnlyExecutor(self.workspace)

        # 1. Unsupervised call raises PermissionError
        with self.assertRaises(PermissionError):
            client.execute_safe_tool_call(
                tool_name="read_file",
                arguments={"path": "dummy.txt"},
                executor=executor,
                human_supervised=False,
            )

        # 2. Unallowlisted tool raises PermissionError
        with self.assertRaises(PermissionError):
            client.execute_safe_tool_call(
                tool_name="execute_arbitrary_shell",
                arguments={"cmd": "ls"},
                executor=executor,
                human_supervised=True,
            )

        # 3. Allowlisted read_text of existing file succeeds
        test_file = self.workspace / "sample.txt"
        test_file.write_text("hello from safe workspace", encoding="utf-8")
        res = client.execute_safe_tool_call(
            tool_name="read_text",
            arguments={"path": "sample.txt"},
            executor=executor,
            human_supervised=True,
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["content"], "hello from safe workspace")

    def test_06_local_skill_registry_discovery_pinning_tamper_detection(self):
        """Verify skill discovery, hash pinning, and tamper rejection."""
        skills_dir = self.workspace / ".skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skills_dir / "test_skill.md"
        skill_content = "# Test Skill\nInstructions for execution."
        skill_file.write_text(skill_content, encoding="utf-8", newline="\n")
        expected_sha = sha256(skill_content.encode("utf-8")).hexdigest()

        registry = LocalSkillRegistry(skills_dir)
        discovered = registry.discover_skills()
        self.assertIn("test_skill.md", discovered)
        self.assertEqual(discovered["test_skill.md"], expected_sha)

        # Pin skill
        registry.pin_skill("test_skill.md", expected_sha)
        loaded = registry.read_approved("test_skill.md")
        self.assertEqual(loaded, skill_content)

        # Tamper detection
        skill_file.write_text("# Tampered Skill Content", encoding="utf-8", newline="\n")
        with self.assertRaises(SkillIntegrityError):
            registry.read_approved("test_skill.md")

    def test_07_role_filtered_skill_access_and_harness_loading(self):
        """Verify skills are filtered by role and loaded as untrusted text."""
        skills_dir = self.workspace / ".skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        plan_skill = skills_dir / "plan_work.md"
        plan_skill.write_text("# Plan Work", encoding="utf-8", newline="\n")
        debug_skill = skills_dir / "debug_code.md"
        debug_skill.write_text("# Debug Code", encoding="utf-8", newline="\n")
        verify_skill = skills_dir / "verify_release.md"
        verify_skill.write_text("# Verify Release", encoding="utf-8", newline="\n")

        registry = LocalSkillRegistry(skills_dir)
        discovered = registry.discover_skills()
        for name, h in discovered.items():
            registry.pin_skill(name, h)

        pm_skills = registry.get_skills_for_role(Role.PM)
        self.assertIn("plan_work.md", pm_skills)
        self.assertNotIn("debug_code.md", pm_skills)

        dev_skills = registry.get_skills_for_role(Role.DEVELOPER)
        self.assertIn("debug_code.md", dev_skills)
        self.assertNotIn("verify_release.md", dev_skills)

        # Harness loading as text
        harness_text = registry.load_harness_content("debug_code.md")
        self.assertEqual(harness_text, "# Debug Code")

    def test_08_mcp_discover_models_and_list_skills(self):
        """Verify FastMCP discover_models and list_skills endpoints."""
        sys = get_production_system(self.workspace)
        sys.nine_router.transport = DummyTransport(responses=[
            {
                "data": [
                    {
                        "id": "default",
                        "supported_parameters": ["tools", "response_format"],
                    }
                ]
            }
        ])

        # Pin a skill into the registry
        skill_file = self.workspace / ".skills" / "my_plan.md"
        skill_content = "# Planning instructions"
        skill_file.write_text(skill_content, encoding="utf-8")
        h = sha256(skill_content.encode("utf-8")).hexdigest()
        sys.skills.pin_skill("my_plan.md", h)

        models = discover_models(str(self.workspace))
        self.assertIsInstance(models, list)
        self.assertTrue(len(models) > 0)
        self.assertEqual(models[0]["model_id"], "default")

        skills = list_skills(role="PM", workspace_path=str(self.workspace))
        self.assertIsInstance(skills, list)
        found = [s["skill"] for s in skills]
        self.assertIn("my_plan.md", found)

    def test_09_supervised_native_lifecycle_with_model_consultation(self):
        """Verify SupervisedNativeLifecycle can consult router under approved D-02 terms."""
        db_file = self.workspace / ".subagentbridge" / "audit.db"
        sys = build_production_system(workspace_root=self.workspace, db_path=db_file)
        store_db = self.workspace / ".subagentbridge" / "store.db"
        store = SQLiteStore(store_db)

        try:
            # Setup mock router reply
            sys.nine_router.transport = DummyTransport(
                responses=[
                    {
                        "choices": [
                            {
                                "message": {"role": "assistant", "content": "Analysis verified"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 20, "completion_tokens": 10},
                    }
                ] * 3
            )

            lifecycle = SupervisedNativeLifecycle(sys, self.workspace, store=store)
            run_id = "run_p04_test"
            tree_sha = resolve_tree_sha(self.workspace)
            tasks, deps, task_records = TaskDecomposer.decompose_goal(
                goal="Verify model and skill routing integration",
                run_id=run_id,
                tree_sha=tree_sha,
            )
            coord, principals = lifecycle.create_coordinator_for_run(run_id, tasks, deps)

            res = lifecycle.execute_lifecycle(
                run_id=run_id,
                coordinator=coord,
                principals=principals,
                task_records=task_records,
                provider_terms_approved=True,
                consult_model=True,
            )

            self.assertEqual(res["status"], "COMPLETED")
            for t in res["tasks"]:
                self.assertEqual(t["status"], "VERIFIED")
        finally:
            store.close()
            sys.close()


if __name__ == "__main__":
    unittest.main()
