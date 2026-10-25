# Simpul — Stacked Merge Tracking and Verification Status

This document records the exact branch ancestry, PR numbers, commit SHAs, QA status, and merge state across all roadmap execution phases.

## Durable Stacked Merge Table

| Phase | Branch | Parent Branch | Target PR Base | PR Number | HEAD Commit SHA | Tree SHA | Local QA Status | CI Status | Merge State |
|---|---|---|---|---|---|---|---|---|---|
| **P00** | `feat/00-baseline-recovery` | `main` | `main` | [#2](https://github.com/rzqllh/SubagentBridge/pull/2) | `19b7fb0a230ab955fb4229b5fd9ac9c0bd37d052` | `e97b37d351336140608fa8ffb738947f15433a59` | **VERIFIED** | **PASS** (39886264082) | **MERGED** (`4bc26c2`) |
| **P01** | `integrate/roadmap-v4-verified` | `feat/00-baseline-recovery` | `feat/00-baseline-recovery` | [#3](https://github.com/rzqllh/SubagentBridge/pull/3) | `badf7f3f8e22b228c33a97fae731a11d8d2727bc` | `297adca730f266b7eb4ea0f16cc7118768fea1df` | **VERIFIED** | **PASS** (39890611732) | **MERGED** (`1fcaaca`) |
| **P02** | `simpul/02-durable-control-plane` | `integrate/roadmap-v4-verified` | `integrate/roadmap-v4-verified` | [#4](https://github.com/rzqllh/SubagentBridge/pull/4) | `4eb450e83911c9648129e398135aa636967824a8` | `01195a16ac5b9607df11267be5081fb1e47650d5` | **VERIFIED** | **PASS** (39891716924) | **MERGED** (`5ad42b8`) |
| **P03** | `simpul/03-native-execution` | `simpul/02-durable-control-plane` | `simpul/02-durable-control-plane` | [#5](https://github.com/rzqllh/SubagentBridge/pull/5) | `94ddbfe396c3e2c4f12ece674e96ef7417941f9d` | `1df77d03114c53bf7bf26fdd57170dc25a3604f8` | **VERIFIED** | **PASS** (39893495436) | **MERGED** (`05d4fa7`) |
| **P04** | `simpul/04-router-skills` | `simpul/03-native-execution` | `simpul/03-native-execution` | [#6](https://github.com/rzqllh/SubagentBridge/pull/6) | `d0b8836a81e953557d013b39445ac71d0dcf41c2` | `e3ca56dea1eabd0a14a12b6d29b97653cc0a655b` | **VERIFIED** | **PASS** (39895436639) | **MERGED** (`46c9b2f`) |
| **P05** | `simpul/05-antigravity-qa` | `simpul/04-router-skills` | `simpul/04-router-skills` | [#7](https://github.com/rzqllh/SubagentBridge/pull/7) | `50cbb9bfde1c70f2ccd44dee6cb6be3581af39ea` | `a6b2797a770765c50b4f45b1079f5f38f2214119` | **VERIFIED** | **PASS** (39896262605) | **MERGED** (`586662f`) |
| **P06** | `simpul/06-release-hardening` | `simpul/05-antigravity-qa` | `simpul/05-antigravity-qa` | [#8](https://github.com/rzqllh/SubagentBridge/pull/8) | `8d2b019da8e6027ae4531804f5eef148286a117b` | `5c42ea6be4941181af29a93c99a395cc26c0436c` | **VERIFIED** | **PASS** (39897017005) | **MERGED** (`953c0f5`, tag `v1.0.0`) |
| **P07** | `simpul/07-corrective-audit` | `main` | `main` | Unmerged Local | `5f69393ce4f7312d542d23d852f046b3d4ffe7bd` | `88c67a42` | **VERIFIED** | Local verification | Retained in worktree |
| **S01** | `simpul/08-sprint1-verification` | `main` (`953c0f5`) | `main` | Active Sprint | In progress | In progress | **IN_PROGRESS** | Local test discovery | Active Working Branch |

## Merge Policy & Invariants
1. Implementation commits are never made directly to `main`.
2. Every phase has an isolated Git worktree under `<repo>/.worktrees/`.
3. Stacked PRs target their immediate predecessor until the predecessor is merged, after which they are retargeted to `main` with full regression re-verification.
4. No force-pushes or history erasure; ancestry is preserved non-destructively.
