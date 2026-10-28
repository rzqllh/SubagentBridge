"""Public documentation release-truth checks for the current default branch.

These static checks prevent the main onboarding links from silently drifting
back to old tags. They are NOT live Antigravity host acceptance tests.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_v114_public_onboarding_points_to_published_release() -> None:
    for file in (
        "README.md",
        "docs/INSTALLATION_QUICKSTART.md",
        "docs/public/README.md",
        "docs/public/GETTING_STARTED.md",
        "docs/public/RELEASE_NOTES.md",
        "docs/SIMPUL_STATUS.md",
    ):
        contents = _text(file)
        assert "v1.1.4" in contents, file
        assert "releases/tag/v1.1.4" in contents, file

    for file in ("docs/INSTALLATION_QUICKSTART.md", "docs/public/GETTING_STARTED.md"):
        contents = _text(file)
        assert "git checkout v1.1.4" in contents
        assert "git checkout v1.1.1" not in contents
        assert "git checkout v1.1.3" not in contents


def test_antigravity_mcp_setup_and_usage_are_linked() -> None:
    start = _text("docs/public/GETTING_STARTED.md")
    index = _text("docs/public/README.md")
    readme = _text("README.md")
    reference = _text("docs/MCP_INTEGRATION.md")
    assert "mcp_config.json" in start and "MCP Servers" in start
    assert "subagentbridge.server" in start and "mcpServers" in start
    assert "submit_goal" in start and "get_run" in start and "list_tasks" in start
    assert "execute_run" in start and "BLOCKED" in start
    assert "PARITY_AND_ROADMAP.md" in index
    assert "docs/public/GETTING_STARTED.md" in readme
    assert "antigravity.google/docs/mcp" in reference


def test_parity_roadmap_does_not_claim_unverified_ide_or_enterprise_safety() -> None:
    roadmap = _text("docs/public/PARITY_AND_ROADMAP.md")
    security = _text("docs/public/SECURITY.md")
    readiness = _text("docs/ENTERPRISE_READINESS.md")
    for term in ("Antigravity IDE", "Cindy", "Orca", "E18", "WebAuthn", "BLOCKED"):
        assert term in roadmap or term in security
    assert "NOT ENTERPRISE-CERTIFIED" in readiness
    assert "#21" in readiness and "#22" in readiness and "#23" in readiness
    assert "NOT enterprise-certified" in security or "NOT enterprise" in security
