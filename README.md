# Simpul

**Simpul** (formerly **SubagentBridge**) is a native-first, safety-gated Model Context Protocol (MCP) subagent supervisor for development workflows, with Google Antigravity IDE as a target host. The Python package, import namespace, CLI and existing environment variable prefix remain `subagentbridge` / `SUBAGENTBRIDGE_*` for compatibility.

> **Release status — 23 October 2026:** Simpul is in supervised development. No general-availability or production-security certification is claimed. This default `main` branch is an older imported baseline, **not** the current release-candidate implementation. Do not interpret the development features below as working in `main`.

## Where the current work lives

| GitHub reference | Scope | Publication state |
| --- | --- | --- |
| [`main`](https://github.com/rzqllh/SubagentBridge/tree/main) | Imported baseline and public project information | Default branch; historical code |
| [PR #2](https://github.com/rzqllh/SubagentBridge/pull/2) · `feat/00-baseline-recovery` | PR-00 safety lockdown and baseline recovery | Open, not merged into `main` |
| [PR #3](https://github.com/rzqllh/SubagentBridge/pull/3) · `integrate/roadmap-v4-verified` | Roadmap implementation candidate, version `1.0.0rc1` | Open; targets PR #2's branch; **not published as a release** |

The PR #3 candidate contains implementations and tests for immutable run/task contracts, SQLite audit/budget persistence, policy classification, a human approval broker, supervised executor, role coordination, local 9Router client, skills registry, QA evidence checks and an MCP interface. Those components do **not** amount to a verified end-to-end unattended coding agent.

## Current operating boundaries

- `AUTONOMY: OFF` — no unattended privileged operations.
- `RISK_ACCEPTED_SAME_IDENTITY` (D-01) — supervised same-user execution **is not an OS security sandbox**.
- `CHAT_APPROVAL` (D-03) — no model-issued Allow Once; never treat a chat instruction as authenticated cross-user approval.
- 9Router transport in the candidate is restricted to a local loopback origin; live authenticated completion was not established in the latest review (HTTP 401 observed).
- E01–E21 have a candidate test matrix, but E18's same-user adversary scenario needs stronger independent evidence; E22 checkout-root containment and E23 real pinned remote checkout remain unverified.
- Independent release QA, branch merge and publishing are still outstanding.

See [the project status and evidence limitations](docs/SIMPUL_STATUS.md) before deploying or relying on security claims.

## Try the development candidate (not `main`)

Requires Python 3.11+ and Git. Checkout the exact reviewed candidate commit rather than assuming the default branch already contains the implementation:

```powershell
git clone https://github.com/rzqllh/SubagentBridge.git
cd SubagentBridge
git checkout 44d70b5f05836a867978dcadb166bd1122943a3b
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe -m subagentbridge.server
```

The final command starts an MCP stdio server; it is not an interactive shell. Do not treat a passing local suite as proof of E18/E22/E23 or live Antigravity/9Router readiness.

For integration details, follow the [candidate branch documentation](https://github.com/rzqllh/SubagentBridge/tree/integrate/roadmap-v4-verified/docs) rather than the historical `main` API design notes.

## License and attribution

[MIT license](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md).
