# PR-04b Windows confinement spike — UNVERIFIED

No Windows confined worker was launched or tested in this local Linux staging run.
Candidates requiring separately authorized prototypes: Windows separate user with
restricted token and ACL denial of broker/secrets; AppContainer capability profile;
Hyper-V/Windows containers with controlled mounts; dedicated VM. Process Job
Objects support lifecycle management but **do not provide security isolation**.
Same-user/desktop code can access or impersonate interactive broker state.
Current `SupervisedReadOnlyExecutor` uses subprocess with an allowlist and scrubbed
environment solely for approved read-only inspection; it is NOT a sandbox.
D-01 and D-03 remain human decisions. AG-1 stays OFF. Do not expose this
candidate as a tool to uncontrolled workers.
