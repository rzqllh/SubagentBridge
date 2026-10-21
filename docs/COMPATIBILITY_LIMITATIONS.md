# SubagentBridge: Compatibility Matrix and Known Limitations

This document defines the verified platforms, supported Python runtimes, and explicit boundaries of SubagentBridge.

---

## 1. Compatibility Matrix

| Component | Supported Version / Platform | Status |
|---|---|---|
| Operating System | Microsoft Windows 10 / 11 (64-bit) | Primary Target, Fully Verified |
| Operating System | Ubuntu 22.04+ / Linux x86_64 | Secondary Target, Verified in CI |
| Python Runtime | Python 3.11, 3.12, 3.13 | Verified (Zero test failures) |
| Antigravity IDE | Antigravity 2.0+ (MCP stdio) | Supported |
| Local 9Router | Version 0.4+ on `127.0.0.1` | Supported (Loopback only) |
| Orca CLI | Optional backend | Opt-in Seam, Disabled by default |

---

## 2. Explicit Boundaries and Non-Goals

1. **AUTONOMY: OFF:** SubagentBridge is not an unconstrained, unsupervised autonomous agent loop. High-risk operations (dependency modifications, git push, credential writes, test mutations) strictly require human approval.
2. **Same-Identity Confinement (Decision D-01):** Phase A execution runs under the same OS identity as the developer (`RISK_ACCEPTED_SAME_IDENTITY`). It does not provide container or VM-level kernel isolation.
3. **Loopback Model Transport (Decision D-02):** SubagentBridge does not initiate external HTTP/HTTPS connections. All model routing flows through the local 9Router loopback proxy.
4. **Chat Approval Broker (Decision D-03):** Human decisions are routed via chat approval or out-of-band high-entropy tokens. Replay protection is enforced.
