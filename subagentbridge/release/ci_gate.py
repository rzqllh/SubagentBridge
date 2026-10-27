"""Fail-closed GitHub Actions evidence gate for the exact release/main commit.

Unlike pull-request CI, a successful main-push matrix tests the actual merged
commit and tree. This does not replace branch protection or human review.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Callable
from urllib.request import Request, urlopen


_REQUIRED_JOBS = frozenset(
    f"Baseline tests / {os_name} / Python {python_version}"
    for os_name in ("ubuntu-latest", "windows-latest")
    for python_version in ("3.11", "3.13")
)


def _get_json(url: str, token: str) -> dict[str, Any]:
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(req, timeout=20) as response:  # nosec B310: fixed, validated GitHub API origin
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("Invalid GitHub Actions API payload")
    return payload


def verify_main_ci(
    repo: str,
    commit_sha: str,
    token: str,
    *,
    getter: Callable[[str, str], dict[str, Any]] | None = None,
) -> bool:
    """Require an exact-SHA main-push workflow with all four successful jobs."""
    if repo != "rzqllh/SubagentBridge" or re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None or not token:
        raise ValueError("Untrusted repository, commit SHA, or missing actions read token")
    get_json = getter or _get_json
    base = f"https://api.github.com/repos/{repo}"
    runs_url = (
        f"{base}/actions/workflows/ci.yml/runs?"
        f"head_sha={commit_sha}&branch=main&event=push&per_page=100"
    )
    runs = get_json(runs_url, token).get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("GitHub Actions did not return a workflow-runs list")

    for run in runs:
        if not isinstance(run, dict) or not (
            run.get("head_sha") == commit_sha
            and run.get("head_branch") == "main"
            and run.get("event") == "push"
            and run.get("path") == ".github/workflows/ci.yml"
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
        ):
            continue
        run_id = run.get("id")
        if type(run_id) is not int or run_id <= 0:
            continue
        jobs_url = f"{base}/actions/runs/{run_id}/jobs?per_page=100&filter=latest"
        jobs = get_json(jobs_url, token).get("jobs")
        if not isinstance(jobs, list):
            raise ValueError("GitHub Actions did not return a job list")
        completed = {
            job.get("name")
            for job in jobs
            if isinstance(job, dict)
            and job.get("status") == "completed"
            and job.get("conclusion") == "success"
        }
        if _REQUIRED_JOBS.issubset(completed):
            return True
    return False


def main() -> int:
    try:
        if not verify_main_ci(
            os.environ.get("GITHUB_REPOSITORY", ""),
            os.environ.get("GITHUB_SHA", ""),
            os.environ.get("GH_TOKEN", ""),
        ):
            raise RuntimeError("No successful exact-SHA main 4-platform CI run")
        print("Release CI gate PASS: exact main SHA has Ubuntu/Windows Python 3.11/3.13 success")
        return 0
    except Exception as exc:
        print(f"Release CI gate BLOCKED: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
