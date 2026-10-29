"""Tests for Issue #44 (PAR-01): Parity Matrix Truth and Consistency Verification.

Validates that:
1. docs/simpul/parity_matrix.json exists, parses cleanly, and strictly adheres to schema contracts.
2. Pinned upstream commits match the exact audit SHAs (Cindy b7e46bc, Orca CLI 5beeefc).
3. Every cited Simpul source file and test evidence file actually exists in the repository.
4. Security blockers (#21 E18 OS worker isolation, #22 production operator approval) are strictly marked BLOCKED.
5. Out-of-scope capabilities (#60 Remote SSH, #61 Cindy desktop/mobile/marketplace) are marked NOT_ADOPTED with documented rationale.
6. Permitted status enums are strictly enforced.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = REPO_ROOT / "docs" / "simpul" / "parity_matrix.json"

EXPECTED_CATEGORIES = {
    "lead_worker_lifecycle_and_batch",
    "queue_and_steering",
    "workspace_and_worktree",
    "resilience_and_recovery",
    "host_integration_and_mcp",
    "security_boundaries",
}

VALID_STATUSES = {
    "CODE_PRESENT",
    "UNIT_TESTED",
    "INTEGRATED",
    "HOST_E2E_PASS",
    "BLOCKED",
    "NOT_ADOPTED",
}

PINNED_CINDY_SHA = "b7e46bcbbe41eeee2f16381fef00df61a31a3b8b"
PINNED_ORCA_CLI_SHA = "5beeefcb57555962bb93facc54b5f82484731802"


def _load_matrix() -> dict[str, Any]:
    assert MATRIX_PATH.exists(), f"Missing required matrix file: {MATRIX_PATH}"
    with open(MATRIX_PATH, "r", encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


class TestParityMatrixTruth(unittest.TestCase):
    """Verifies schema, citations, pinned commits, and status integrity of parity_matrix.json."""

    def test_parity_matrix_schema_and_metadata(self) -> None:
        """Verify top-level metadata, governance, and pinned upstream commit hashes."""
        data = _load_matrix()
        self.assertEqual(data["schema_version"], "1.0.0")
        self.assertEqual(data["governance"]["autonomy"], "OFF")
        self.assertEqual(data["governance"]["gate_mode"], "CHAT_APPROVAL")
        self.assertEqual(data["governance"]["host_target"], "Google Antigravity IDE")

        cindy = data["pinned_upstream"]["cindy"]
        self.assertEqual(cindy["pinned_sha"], PINNED_CINDY_SHA)

        orca_cli = data["pinned_upstream"]["orca_cli"]
        self.assertEqual(orca_cli["pinned_sha"], PINNED_ORCA_CLI_SHA)

    def test_parity_matrix_categories_and_statuses(self) -> None:
        """Verify category structure and strict status validation for every feature."""
        data = _load_matrix()
        categories = data.get("categories", {})
        self.assertEqual(set(categories.keys()), EXPECTED_CATEGORIES)

        all_feature_ids: set[str] = set()

        for cat_name, features in categories.items():
            self.assertIsInstance(features, list, f"Category {cat_name} must be a list")
            self.assertGreater(len(features), 0, f"Category {cat_name} must contain at least one feature")

            for feat in features:
                fid = feat["feature_id"]
                self.assertNotIn(fid, all_feature_ids, f"Duplicate feature_id: {fid}")
                all_feature_ids.add(fid)

                status = feat["status"]
                self.assertIn(status, VALID_STATUSES, f"Feature {fid} has invalid status {status}")
                self.assertTrue(feat["security_boundary"], f"Feature {fid} must have an explicit security_boundary statement")
                self.assertTrue(feat["name"], f"Feature {fid} missing name")
                self.assertTrue(feat["target_behavior"], f"Feature {fid} missing target_behavior")

    def test_parity_matrix_source_and_test_evidence_paths_exist(self) -> None:
        """Ensure every referenced source file and test file exists on disk (no phantom references)."""
        data = _load_matrix()
        categories = data["categories"]

        for cat_name, features in categories.items():
            for feat in features:
                fid = feat["feature_id"]
                simpul_impl = feat.get("simpul_implementation")
                if simpul_impl and simpul_impl.get("source_file"):
                    src_rel = simpul_impl["source_file"]
                    src_path = REPO_ROOT / src_rel
                    self.assertTrue(src_path.is_file(), f"Feature {fid} references non-existent source file: {src_rel}")

                evidence = feat.get("test_evidence")
                if evidence and evidence.get("test_file"):
                    test_rel = evidence["test_file"]
                    test_path = REPO_ROOT / test_rel
                    self.assertTrue(test_path.is_file(), f"Feature {fid} references non-existent test file: {test_rel}")

    def test_parity_matrix_security_blockers_and_non_adopted_scopes(self) -> None:
        """Verify security gates #21 and #22 are BLOCKED and optional extras are NOT_ADOPTED."""
        data = _load_matrix()
        categories = data["categories"]

        feature_map = {
            feat["feature_id"]: feat
            for cat_list in categories.values()
            for feat in cat_list
        }

        # Issue #21 / E18: Hostile worker OS isolation
        e18_feat = feature_map["PAR-FEAT-22"]
        self.assertEqual(e18_feat["status"], "BLOCKED")
        self.assertTrue("E18" in e18_feat["security_boundary"] or "same-user" in e18_feat["security_boundary"])

        # Issue #22: Authenticated human approval
        auth_feat = feature_map["PAR-FEAT-23"]
        self.assertEqual(auth_feat["status"], "BLOCKED")
        self.assertIn("BLOCKED", auth_feat["security_boundary"])

        # Issue #60: Remote SSH
        ssh_feat = feature_map["PAR-FEAT-25"]
        self.assertEqual(ssh_feat["status"], "NOT_ADOPTED")
        self.assertIsNotNone(ssh_feat["not_adopted_rationale"])
        self.assertGreater(len(ssh_feat["not_adopted_rationale"]), 10)

        # Issue #61: Cindy desktop/browser extras
        desktop_feat = feature_map["PAR-FEAT-26"]
        self.assertEqual(desktop_feat["status"], "NOT_ADOPTED")
        self.assertIsNotNone(desktop_feat["not_adopted_rationale"])
        self.assertIn("Antigravity IDE", desktop_feat["not_adopted_rationale"])


if __name__ == "__main__":
    unittest.main()
