# Signed release provenance — candidate release gate

**Status:** implemented on the candidate branch, NOT proven on a published
release. Main's last published artifact is still v1.1.3. Branch protection,
independent reviewer approvals, isolated build, signed SBOM, and E18 acceptance
remain separate, unresolved requirements.

## Gate order

The `.github/workflows/release.yml` publishing workflow runs ONLY on a
`release/v*` branch that points to the same exact commit as `main` and
whose four-platform push CI is verified by `release/ci_gate.py`.

Before the `gh release create` step, it must:

1. Run the package/parity tests and static checks.
2. Build `dist/*.whl` and `dist/*.tar.gz` in that exact workflow.
3. Generate GitHub/Sigstore build provenance attestations for `dist/*`
   using the SHA-pinned `actions/attest` action with OIDC permissions.
4. Execute `gh attestation verify` on **each** built artifact. An attestation
   creation/verification failure stops publication.
5. Include SHA-256 hashes alongside the wheel and sdist.

This validates build origin and integrity, **not** that the software has no
vulnerabilities or that the source passed independent security review.

## Consumer verification

After downloading release assets to an uncompromised verifier, check:

```bash
sha256sum -c SHA256SUMS.txt
gh attestation verify subagentbridge-<version>-py3-none-any.whl -R rzqllh/SubagentBridge
gh attestation verify subagentbridge-<version>.tar.gz -R rzqllh/SubagentBridge
```

Verify the attestation's repository, workflow identity, event, branch, commit
SHA, and artifact digest against the reviewed release policy; do not accept a
random valid signature as a substitute for the expected source. Use a release
in an expendable environment first.

## Still required

- Set enforced GitHub `main` branch protection / rulesets, mandatory checks
  and an independent review; this requires repository administration access.
- Independently audit and test a **real release execution** and its resulting
  GitHub attestations, not just PR checks. No release is triggered by the PR.
- Generate and sign a dependency-accurate SPDX/CycloneDX SBOM (not an SBOM
  of the CI runner's unrelated packages), and perform restore/rollback drills.
- E18 OS confinement remains BLOCKED, as do genuine production OIDC/WebAuthn
  authentication and end-to-end hostile-worker penetration receipts.

References: GitHub Docs, "Using artifact attestations to establish provenance
for builds"; https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations
