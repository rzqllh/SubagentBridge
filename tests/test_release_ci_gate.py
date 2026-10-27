"""Release provenance gate: only actual merged main-sha cross-platform CI counts."""
from __future__ import annotations

import pytest

from subagentbridge.release.ci_gate import verify_main_ci


SHA = "a" * 40
REPO = "rzqllh/SubagentBridge"
NAMES = [
    f"Baseline tests / {os_name} / Python {version}"
    for os_name in ("ubuntu-latest", "windows-latest")
    for version in ("3.11", "3.13")
]


def _responses(*, event="push", sha=SHA, status="completed", conclusion="success", job_names=None):
    run = {
        "id": 42, "head_sha": sha, "head_branch": "main", "event": event,
        "path": ".github/workflows/ci.yml", "status": status, "conclusion": conclusion,
    }
    jobs = [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in (NAMES if job_names is None else job_names)
    ]
    def getter(url, token):
        assert token == "test-token"
        if "/workflows/ci.yml/runs?" in url:
            return {"workflow_runs": [run]}
        assert "/actions/runs/42/jobs?" in url
        return {"jobs": jobs}
    return getter


def test_release_requires_all_four_jobs_for_exact_main_commit():
    assert verify_main_ci(REPO, SHA, "test-token", getter=_responses())


@pytest.mark.parametrize("options", [
    {"event": "pull_request"}, {"sha": "b" * 40},
    {"status": "in_progress"}, {"conclusion": "failure"},
    {"job_names": NAMES[:3]},
])
def test_release_rejects_nonmatching_or_incomplete_ci(options):
    assert not verify_main_ci(REPO, SHA, "test-token", getter=_responses(**options))


def test_release_rejects_invalid_identity_and_missing_token():
    with pytest.raises(ValueError):
        verify_main_ci("attacker/repo", SHA, "test-token", getter=_responses())
    with pytest.raises(ValueError):
        verify_main_ci(REPO, "main", "test-token", getter=_responses())
    with pytest.raises(ValueError):
        verify_main_ci(REPO, SHA, "", getter=_responses())


def test_release_fails_closed_if_github_api_unreachable():
    def unavailable(url, token):
        raise OSError("network error")
    with pytest.raises(OSError):
        verify_main_ci(REPO, SHA, "test-token", getter=unavailable)
