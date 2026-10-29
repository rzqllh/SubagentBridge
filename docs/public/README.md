# Simpul documentation

Simpul is a supervised coding-task coordinator. Start with [installation and first use](GETTING_STARTED.md), then read the security boundary before enabling worker execution.

The published release is [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4). Current source can include later changes; a document describing source does not prove those changes are in the published artifact.

## For users

| Need | Guide |
| --- | --- |
| Install and connect Antigravity IDE | [Getting started](GETTING_STARTED.md) |
| Understand supported capabilities | [Capabilities and roadmap](PARITY_AND_ROADMAP.md) |
| Understand data and execution risks | [Security](SECURITY.md) |
| Upgrade from older identifiers | [Migration](MIGRATION.md) |
| Check release changes | [Release notes](RELEASE_NOTES.md) and [current status](../SIMPUL_STATUS.md) |
| Diagnose a problem | [Troubleshooting](../TROUBLESHOOTING_FAQ.md) |

## For developers and operators

- [Architecture overview](ARCHITECTURE.md) and [implementation architecture](../ARCHITECTURE.md)
- [MCP integration](../MCP_INTEGRATION.md), [API reference](../API_REFERENCE.md), and [configuration](../CONFIGURATION.md)
- [Approval model](../SECURITY_APPROVAL_MODEL.md), [worker isolation](../WORKER_ISOLATION.md), and [security invariants](../INVARIANTS.md)
- [Operational incidents](../OPERATIONAL_INCIDENT_RUNBOOK.md) and [recovery](../PERSISTENCE_RECOVERY.md)
- [Testing](../TESTING_QA_GUIDE.md), [contributing](../CONTRIBUTING.md), and [release provenance](../RELEASE_ATTESTATION.md)
- [Organizational deployment requirements](../ENTERPRISE_READINESS.md)

Worker processes are not a hostile-code sandbox. E18 and independent human authentication remain open security boundaries. Read the linked limitations rather than treating a green source test as enterprise certification.
