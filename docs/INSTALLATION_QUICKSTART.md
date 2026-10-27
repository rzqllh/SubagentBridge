> **Latest release:** [v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1) — `861f040dc12c33da681331e454ef41299f2dc70b` (27 October 2026); all earlier candidate-era notes below are historical. E18 remains BLOCKED.

> **Release verified — 27 October 2026:** [Simpul v1.1.0](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.0) is published from merge commit `a29f0d98957651e482fbae989a906bb09873f329`; candidate CI ran 4/4 successfully, release workflow [40440851542](https://github.com/rzqllh/SubagentBridge/actions/runs/40440851542) succeeded. Historical candidate notes below are not current status. E18 remains BLOCKED (RISK_ACCEPTED_SAME_IDENTITY).

## Install the verified v1.1.1 release (27 October 2026)

[Release v1.1.1](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.1) is published from commit `861f040dc12c33da681331e454ef41299f2dc70b`. For reproducibility, clone the repository and checkout `v1.1.1` explicitly instead of a moving branch. For native SQLite upgrades, preserve generated logical pre-migration backups and verify their integrity before cleanup. Python 3.11–3.13 supported; the MCP stdio entrypoint remains `python -m subagentbridge.server`. E18 OS isolation remains BLOCKED.

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout v1.1.1
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m subagentbridge.server
```


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
