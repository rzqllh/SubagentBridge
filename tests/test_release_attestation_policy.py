"""Static fail-closed release provenance policy acceptance.

Does not substitute for a real signed-release drill or GitHub branch protection.
"""
from pathlib import Path


def test_release_pipeline_attests_exact_verified_build_before_publication():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8",
    )
    # Both permissions are necessary to create Sigstore-backed attestations.
    assert "id-token: write" in workflow
    assert "attestations: write" in workflow
    assert "actions: read" in workflow

    checkpoints = [
        "Enforce release branch and exact tested main commit",
        "python subagentbridge/release/ci_gate.py",
        "python -m build --wheel --sdist",
        "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
        "subject-path: 'dist/*'",
        'gh attestation verify "$artifact"',
        'gh release create "${TAG}"',
    ]
    offsets = [workflow.index(value) for value in checkpoints]
    assert offsets == sorted(offsets)
    assert "set -euo pipefail" in workflow
    assert "for artifact in dist/*" in workflow
    assert "sha256sum dist/* > SHA256SUMS.txt" in workflow
