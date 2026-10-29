# Simpul v1.1.4 : Compatibility and limitations

**Published:** [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4), 28 October 2026 · [main CI 4/4 PASS](https://github.com/rzqllh/SubagentBridge/actions/runs/40622640492). Public name: Simpul; technical distribution/module/MCP server: `subagentbridge`.

| Platform / capability | Grounded scope |
|---|---|
| Windows and Ubuntu/Linux | CI-tested Python 3.11 and Python 3.13 on both OS families; not all local host versions verified |
| Python 3.12 | Declared supported in packaging, but not included in the exact four-job CI matrix |
| Antigravity IDE | Primary intended MCP host using `mcp_config.json`; MCP stdio/subprocess tests exist, but **real IDE-specific installed-version acceptance is not independently certified** |
| Antigravity / Codex / Claude Code / Pi harnesses | Capability-declared adapters and selected tests; not automatic behavioral or feature parity for arbitrary installed CLIs |
| Orca/Cindy | Independently implemented native Python lead/worker patterns; legacy Orca naming/shims remain, no required external Orca installation |
| 9Router | Configurable local loopback text transport; valid upstream credentials and live model capability depend on your configured environment |
| Published artifacts | Wheel, source archive, SHA256 sums, and signed GitHub build attestations verified in the release workflow; not a production vulnerability certificate |

## Known operating limits

1. **`AUTONOMY: OFF`**: SIMPUL is not an unrestricted automatic multi-agent coding fleet. Privileged commands stay gated; `submit_goal` alone does not authorize arbitrary filesystem writes, dependency installation or network operations.
2. **E18 (#21): BLOCKED**: default workers and supervisor still share an OS user. Different PIDs and Git worktrees are *not* a hostile-worker sandbox; strict worker-identity mode refuses unsupported configurations.
3. **Human operator (#22): BLOCKED**: opt-in action-specific decision-verifier APIs exist but no production WebAuthn/OIDC trusted UI or independently verified operator origin is included. A model tool call or chat reply cannot approve itself.
4. **Recovery (#23): PARTIAL**: SQLite checkpoint reconciliation handles bounded scenarios but cannot guarantee exactly-once arbitrary external side effects after abrupt crashes. Avoid blind retry.
5. **Host and upstream parity: PARTIAL**: Cindy/Orca core concepts are a roadmap target, not a feature-by-feature promise. Antigravity IDE interaction and specific host permissions must be tested in your installed version.
6. **Local configuration**: server reads `SUBAGENTBRIDGE_DB_PATH`, `SUBAGENTBRIDGE_PRODUCTION_DB`, `NINE_ROUTER_BASE_URL`/`SUBAGENTBRIDGE_ROUTER_URL` and `NINE_ROUTER_API_KEY`/`SUBAGENTBRIDGE_ROUTER_KEY` per [configuration](CONFIGURATION.md); never commit credentials.

**Start here:** [Antigravity installation and safe first use](public/GETTING_STARTED.md), [parity roadmap](public/PARITY_AND_ROADMAP.md), [MCP API](API_REFERENCE.md), [security](public/SECURITY.md), [enterprise gates](ENTERPRISE_READINESS.md).
