# Simpul — compatibility and limitations

Public product name: Simpul. Technical identifiers remain `rzqllh/SubagentBridge`, `subagentbridge` and `SUBAGENTBRIDGE_*`.

| Capability | 1.1.0 supervised beta status |
| --- | --- |
| Windows / Linux | Matrix CI on Python 3.11 and 3.13; this is not an OS security audit |
| Python 3.12 | Package metadata supports it; not separately covered in the 4-job matrix |
| MCP stdio | Implemented; host configuration and live integration need local verification |
| Native worker subprocesses | Implemented with process IDs, pipes, deadlines and interruption |
| Multi-harness registry | Capability declarations exist; external CLI end-to-end behaviors must be verified per host |
| SQLite continuity | WAL persistence, migration backup, checkpoint/task recovery with explicit at-least-once ambiguity |
| Same-user worker sandbox | **Not available** — E18 BLOCKED (RISK_ACCEPTED_SAME_IDENTITY) |
| Authenticated human UI | No production out-of-band UI; test broker fixtures do not establish real human origin |
| Autonomy | OFF; privileged operations require human supervision |
| Release publication | Check GitHub Releases for actual published tag; branch metadata alone does not publish |

The former `orca_*` SQL names are compatibility views, read-only for SQL; native Python writes use `simpul_*`. See [migration](public/MIGRATION.md), [architecture](public/ARCHITECTURE.md), and [security](public/SECURITY.md).
