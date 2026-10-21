# SubagentBridge: Installation and Quick Start Guide

This guide describes how to install, configure, and run SubagentBridge on Windows (primary target) and Linux environments.

---

## 1. Prerequisites

- Operating System: Windows 10/11 (64-bit) or modern Linux (Ubuntu 22.04+).
- Python: Version 3.11, 3.12, or 3.13.
- Git: Installed and available in PATH.
- Local 9Router (optional for live model routing): running on `http://127.0.0.1:8080` (loopback only).

---

## 2. Installation from Source

Clone the repository and set up a virtual environment:

### Windows (PowerShell)
```powershell
# Clone the repository
git clone https://github.com/rzqllh/SubagentBridge.git
Set-Location SubagentBridge

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Upgrade build tooling and install in editable mode
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

### Linux / macOS (Bash)
```bash
# Clone the repository
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip and install
pip install --upgrade pip setuptools wheel
pip install -e .
```

---

## 3. Verifying the Installation

Run the complete test suite to confirm all domain contracts, durable SQLite ledgers, model routing table, and acceptance matrix tests pass cleanly:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Expected output:
```text
Ran 250 tests in ~2.5s
OK (skipped=4)
```

*(The 4 skipped tests represent optional external Orca CLI probes and remote network endpoints that are disabled by default for zero-egress security).*

---

## 4. Running the MCP Server

SubagentBridge exposes a standard Model Context Protocol (MCP) server over standard input/output (`stdio`).

Start the server using Python:

```powershell
python -m subagentbridge.server
```

You can customize runtime behavior using environment variables:
- `SUBAGENTBRIDGE_DB_PATH`: Path to the SQLite database (default: `subagentbridge.db`).
- `SUBAGENTBRIDGE_BROKER_SECRET`: Secret token used for out-of-band human approvals.
- `SUBAGENTBRIDGE_ROUTER_URL`: Base URL for local 9Router (default: `http://127.0.0.1:8080/v1`).
- `SUBAGENTBRIDGE_WORKSPACE_ROOT`: Root path for supervised execution boundaries.

---

## 5. Security Posture Notice

- `AUTONOMY: OFF` is enforced. Unattended privileged system modifications are rejected.
- Confinement mode: `RISK_ACCEPTED_SAME_IDENTITY` (D-01 Phase A).
- Gate mode: `CHAT_APPROVAL` (D-03).
- Model transport: Loopback `127.0.0.1` only (D-02). Zero external egress is initiated.
