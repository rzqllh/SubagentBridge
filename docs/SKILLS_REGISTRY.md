# SubagentBridge: Skills Registry and Trust Policy

This document details the security model for discovering, loading, and verifying agent skills.

---

## 1. Skill Threat Model

Agent skill definitions (such as prompt instructions, specialized cheatsheets, and workflow guides) represent untrusted text input:
- An attacker or compromised worker might attempt to inject prompt overrides (e.g., "ignore all rules", "bypass approval gates").
- An attacker might modify skill file content after human approval (TOCTOU attacks).
- An attacker might use directory traversal (`../`) or symlinks/junctions to escape the skill directory.

---

## 2. Pinned Hash Policy (`LocalSkillRegistry`)

To neutralize these risks, `LocalSkillRegistry` enforces cryptographic pinning:
- Every approved skill must have its SHA-256 digest pre-registered in a trusted pin map.
- Skills cannot be read using arbitrary paths or relative traversals (`.` or `..` are forbidden).
- Symbolic links and Windows NTFS junctions are strictly forbidden.
- File size is capped at 2 MB (`MAX_SKILL_BYTES = 2 * 1024 * 1024`).

```python
from hashlib import sha256
from subagentbridge.skills.registry import LocalSkillRegistry, SkillIntegrityError

pins = {
    "code_review.md": "3c98b6a3782...",
    "test_design.md": "a82b991cd4e...",
}

registry = LocalSkillRegistry(skills_root_path, pins=pins)

# Safe approved read:
content = registry.read_approved("code_review.md")

# Tampered content or unregistered file raises SkillIntegrityError:
# registry.read_approved("tampered.md") -> SkillIntegrityError
```

---

## 3. Verification

Verified under Scenario E06 in `tests/test_acceptance_matrix_e01_e21.py`:
- Registered skills load successfully.
- Tampered skill files fail closed immediately before content reaches the prompt engine.
