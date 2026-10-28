"""Release metadata consistency and transparent security limitation policy."""
from __future__ import annotations

from pathlib import Path
import tomllib


def test_v114_release_metadata_matches_source_and_discloses_blockers() -> None:
    root = Path(__file__).resolve().parents[1]
    with (root / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert version == "1.1.4"
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    readiness = (root / "docs" / "ENTERPRISE_READINESS.md").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    # Workflow consumes Unreleased notes until the next version heading.
    release_notes = changelog.split("## [Unreleased]", 1)[1].split("## [1.1.3]", 1)[0]
    assert "v1.1.4" in release_notes
    assert "NOT an enterprise" in release_notes
    assert "E18" in release_notes and "#22" in release_notes
    assert "v1.1.4" in readme and "git checkout v1.1.4" in readme
    assert "NOT ENTERPRISE-CERTIFIED" in readiness
    assert '"release/v" + version' in workflow
    assert "main == os.environ[\"GITHUB_SHA\"]" in workflow
    assert "gh attestation verify" in workflow
