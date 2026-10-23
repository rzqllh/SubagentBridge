# Simpul — Stacked Merge Tracking and Verification Status

This document records the exact branch ancestry, PR numbers, commit SHAs, QA status, and merge state across all roadmap execution phases.

## Durable Stacked Merge Table

| Phase | Branch | Parent Branch | Target PR Base | PR Number | HEAD Commit SHA | Tree SHA | Local QA Status | CI Status | Merge State |
|---|---|---|---|---|---|---|---|---|---|
| **P00** | `feat/00-baseline-recovery` | `main` | `main` | [#2](https://github.com/rzqllh/SubagentBridge/pull/2) | `19b7fb0a230ab955fb4229b5fd9ac9c0bd37d052` | `e97b37d351336140608fa8ffb738947f15433a59` | **VERIFIED** | **PASS** (39886264082) | MERGEABLE |
| **P01** | `integrate/roadmap-v4-verified` | `feat/00-baseline-recovery` | `feat/00-baseline-recovery` | [#3](https://github.com/rzqllh/SubagentBridge/pull/3) | `badf7f3f8e22b228c33a97fae731a11d8d2727bc` | `297adca730f266b7eb4ea0f16cc7118768fea1df` | **VERIFIED** | **PASS** (39890611732) | STACKED |
| **P02** | `simpul/02-durable-control-plane` | `integrate/roadmap-v4-verified` | `integrate/roadmap-v4-verified` | TBD | Pending commit | Pending | **VERIFIED** | Pending push | STACKED |
| **P03** | `simpul/03-native-execution` | `simpul/02-durable-control-plane` | `simpul/02-durable-control-plane` | TBD | TBD | TBD | QUEUED | QUEUED | QUEUED |
| **P04** | `simpul/04-router-skills` | `simpul/03-native-execution` | `simpul/03-native-execution` | TBD | TBD | TBD | QUEUED | QUEUED | QUEUED |
| **P05** | `simpul/05-antigravity-qa` | `simpul/04-router-skills` | `simpul/04-router-skills` | TBD | TBD | TBD | QUEUED | QUEUED | QUEUED |
| **P06** | `simpul/06-release-hardening` | `simpul/05-antigravity-qa` | `simpul/05-antigravity-qa` | TBD | TBD | TBD | QUEUED | QUEUED | QUEUED |

## Merge Policy & Invariants
1. Implementation commits are never made directly to `main`.
2. Every phase has an isolated Git worktree under `<repo>/.worktrees/`.
3. Stacked PRs target their immediate predecessor until the predecessor is merged, after which they are retargeted to `main` with full regression re-verification.
4. No force-pushes or history erasure; ancestry is preserved non-destructively.
