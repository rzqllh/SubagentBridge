# Simpul support and release status

Published release: [v1.1.4](https://github.com/rzqllh/SubagentBridge/releases/tag/v1.1.4), dated 28 October 2026. The release contains wheel and source-distribution assets with checksums. Current `main` may include later development; compare the intended commit with the release tag before relying on a source capability.

## Supported use

Simpul coordinates supervised coding work through MCP. Antigravity IDE is the primary intended host. The Python package and MCP technical identity remain `subagentbridge`.

Native lead/worker sessions, task queues, local persistence, worktrees, and adapters exist in source. Their scope and proof levels are described in the [capabilities reference](public/PARITY_AND_ROADMAP.md). Read the [installation guide](public/GETTING_STARTED.md) for the published version.

## Security boundary

| Area | Current limit |
| --- | --- |
| Autonomy | `AUTONOMY: OFF`; operator authorization is required |
| E18 worker containment | BLOCKED for hostile-worker isolation; default workers share the supervisor OS identity |
| Independent operator identity | Production WebAuthn/OIDC authentication remains an open requirement |
| IDE integration | Protocol and subprocess tests are separate from real packaged-IDE acceptance |
| Verification | Source tests are not live-host evidence or enterprise certification |
| Recovery | Ambiguous external side effects require operator reconciliation before replay |

The [security policy](public/SECURITY.md) and [enterprise deployment requirements](ENTERPRISE_READINESS.md) describe these limits. Current issues [#21](https://github.com/rzqllh/SubagentBridge/issues/21), [#22](https://github.com/rzqllh/SubagentBridge/issues/22), and [#23](https://github.com/rzqllh/SubagentBridge/issues/23) track the related enterprise gates.

## Release requirements

A release candidate needs passing checks on its exact source commit, a package inventory and license review, independent review appropriate to its scope, and an explicit operator decision. Broader safety claims also require real containment and authenticated human-approval evidence.

The [release workflow](../.github/workflows/release.yml) verifies the release branch/version, exact tested `main`, package checks, and signed provenance before publishing. [Release attestation](RELEASE_ATTESTATION.md) explains consumer verification. This page does not authorize or perform a release.

## Further reading

[Public documentation](public/README.md) provides installation and usage. [Compatibility](COMPATIBILITY_LIMITATIONS.md), [worker isolation](WORKER_ISOLATION.md), and [incident handling](OPERATIONAL_INCIDENT_RUNBOOK.md) are technical references for operators.
