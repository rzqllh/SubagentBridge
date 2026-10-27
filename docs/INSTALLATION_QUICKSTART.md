## Candidate versus published installation (27 October 2026)

`v1.0.0` is the last documented published release. Install it from its tag for stable reproduction. C00–C07 features are still reviewed on `simpul/15-native-naming`; they are **not available on v1.0.0**. To test that candidate, explicitly checkout that branch and run the four-platform CI-equivalent commands shown in [release readiness](simpul/RELEASE_READINESS.md). Back up any legacy SQLite database before testing an upgrade; migration creates a logical pre-migration backup. The MCP stdio entrypoint remains `python -m subagentbridge.server`, not a standalone chat application.

# Simpul — Installation and candidate quick start

Simpul is the public name. The Python distribution and import package remain `subagentbridge`. **The default GitHub branch still contains an older baseline**; this guide applies to the PR #3 development candidate and is not a general-availability release guide.

## Prerequisites

Git and Python 3.11–3.13; Windows is the primary intended host, while Linux is also a supported development target. Python 3.12 is declared in package metadata, but the cited 21 October CI evidence specifically covers 3.11 and 3.13 on Windows and Linux. Host integration is not independently certified.

## Windows (PowerShell)

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout 44d70b5f05836a867978dcadb166bd1122943a3b
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe -m subagentbridge.server
```

## Linux

```bash
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout 44d70b5f05836a867978dcadb166bd1122943a3b
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -m subagentbridge.server
```

The commit is a reviewed **source snapshot**, not a published release. Dependency installation may access PyPI; review dependencies and your network policy before installing. `python -m subagentbridge.server` starts the MCP **stdio** transport; a compatible host must manage it. See [MCP integration](MCP_INTEGRATION.md).

## Verification expectations

The 21 October candidate report records 250 discovered tests (246 pass, 4 skipped) and an E01–E21 unit-test matrix. This is historic evidence from a previously reported environment, **not a guarantee that this checkout will reproduce the count or pass independently today**. Always retain the actual command output and report skipped tests. Local unittest results do not validate E22/E23, same-user E18 containment, live Antigravity execution or live authenticated 9Router calls.

## What starting the server actually does

`submit_goal` registers a run and a pending task in this candidate; it does not automatically execute a PM/Developer/QA workflow. The `_runs`/`_tasks` tracking tables are memory-resident. The default composition root may create SQLite files when invoked, but a persistent audit record is not proof of MCP run-state recovery.

Do not add credentials to `mcp_config.example.json` or enable unattended worker modifications. See [Configuration](CONFIGURATION.md) and [Current status](SIMPUL_STATUS.md).
