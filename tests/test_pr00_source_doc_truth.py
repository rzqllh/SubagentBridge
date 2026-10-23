"""PR-00 P0 source/documentation drift guard (stdlib, no runtime MCP import)."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CurrentP0DocumentationContract(unittest.TestCase):
    def test_current_source_denial_contract(self):
        server = ast.parse((ROOT / "subagentbridge/server.py").read_text(encoding="utf-8"))
        manager = ast.parse((ROOT / "subagentbridge/manager.py").read_text(encoding="utf-8"))
        methods = {node.name: node for node in server.body if isinstance(node, ast.FunctionDef)}
        for method in ("approve_action", "apply_code_fix"):
            fn = methods[method]
            self.assertFalse(any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                                 and isinstance(d.func.value, ast.Name) and d.func.value.id == "mcp"
                                 and d.func.attr == "tool" for d in fn.decorator_list), method)
        spawn = methods["spawn_agent"]
        defaults = {a.arg: d for a, d in zip(spawn.args.args[-len(spawn.args.defaults):], spawn.args.defaults)}
        self.assertIs(defaults["skip_permissions"].value, False)
        sess = next(node for node in manager.body if isinstance(node, ast.ClassDef) and node.name == "Session")
        init = next(node for node in sess.body if isinstance(node, ast.AnnAssign) and
                    isinstance(node.target, ast.Name) and node.target.id == "skip_permissions")
        self.assertIs(init.value.value, False)

    def test_live_docs_no_old_approval_default_claim(self):
        live = ((ROOT / "README.md").read_text(encoding="utf-8") +
                (ROOT / "docs/SECURITY.md").read_text(encoding="utf-8"))
        for stale in (
            "publishes `approve_action` over MCP",
            "The default `skip_permissions=True` is unsafe",
            "`skip_permissions=True` remains an unsafe default",
            "The existing `approve_action` MCP tool",
        ):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, live)
        api = (ROOT / "docs/API_REFERENCE.md").read_text(encoding="utf-8")
        self.assertIn("Removed from MCP exposure by P0 lockdown", api)
        self.assertIn("legacy worker execution is **disabled", api)


if __name__ == "__main__":
    unittest.main()
