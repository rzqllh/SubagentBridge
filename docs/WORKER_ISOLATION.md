# Worker Identity and Environment Boundary

**State:** Defense-in-depth implemented; **E18 remains BLOCKED** for enterprise-grade hostile-worker isolation. This is a security-control guide, not evidence of an independently assessed operating-system sandbox.

## Supervised default: `inherited`

The trusted `WorkerProcessController` launches a Python child under the caller's same OS account. It now passes only an explicit allowlist of noncredential OS environment variables and the trusted Simpul package directory, with Python `-P` safe-path and `PYTHONNOUSERSITE=1`. Variables such as `OPENAI_API_KEY`, `GITHUB_TOKEN`, `AWS_SECRET_ACCESS_KEY`, `SSH_AUTH_SOCK` and arbitrary `PYTHONPATH` are not propagated. This prevents accidental *environment inheritance*, **not** file-system access by a same-user child: a child with the supervisor's OS permissions can still open readable files, other processes, sockets and secrets.

An external harness relying on a provider token in its environment must NOT turn on unfiltered inheritance as a workaround. Provision scoped credentials through an independently mediated service/token broker with explicit audit, access policy and rotation.

## Experimental opt-in: Linux `dedicated_user`

The trusted supervisor may instantiate:

```python
from subagentbridge.execution.worker_isolation import WorkerIsolationPolicy
from subagentbridge.execution.worker_process import WorkerProcessController

policy = WorkerIsolationPolicy(mode="dedicated_user", uid=12345, gid=12345)
controller = WorkerProcessController(store=store, isolation_policy=policy)
```

This is a Python API example, not an MCP-callable tool or production deployment recommendation. Configure the actual UID/GID for a **dedicated** worker account in your organization. The controller must have privileges to set both identities (currently a Linux root process is required); `subprocess.Popen(user=..., group=..., extra_groups=[])` drops process credentials before executing the child. The controller verifies the actual effective UID/GID from the OS via psutil, not merely the worker's claimed handshake. There is **no fallback** to same-user execution if validation, code-directory checks, privilege drop, handshake, or process start fails.

Prerequisites: a protected, readable (but worker-nonwritable) Simpul runtime installation including its parent path; separately ACLed workspaces writable only as appropriate; a configured worker account with a valid home directory and positive non-root primary group. A supervisor running as root is a **major privileged attack surface** and is not recommended outside a controlled dedicated service design. Use hardened privilege delegation and security review before deploying.

On Windows this mode is intentionally **unsupported and fail-closed** pending verified restricted-token or independently authenticated dedicated-account process launch support. This work does not claim Windows E18 acceptance.

## Still missing for enterprise E18

- A supported and independently tested Windows worker privilege boundary.
- Enforced network egress, syscall, process, storage and secret boundaries for hostile workloads; a separate UID alone does not block all forms of data exfiltration.
- A robust credential broker and independently authenticated out-of-band human approval.
- Windows/Linux adversarial negative E2E evidence that a hostile worker cannot read supervisor credentials or modify sibling/parent workspaces.
- Restart, crash and forensic audit guarantees under the target isolation backend.

## Acceptance evidence

`tests/test_worker_isolation_boundary.py` covers allowlisted environment construction, actual worker execution proving credential env values are not inherited, unprivileged/non-Linux fail-closed policy behavior, permission checks, and the default governance mode.

Passing these tests is **not** proof of hostile-worker confinement. Track the remaining security work in [E18 Issue #21](https://github.com/rzqllh/SubagentBridge/issues/21), [Human Approval Issue #22](https://github.com/rzqllh/SubagentBridge/issues/22), and [Enterprise Readiness](ENTERPRISE_READINESS.md).
