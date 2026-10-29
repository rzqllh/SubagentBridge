# SubagentBridge: Developer Contribution Guide

Thank you for contributing to SubagentBridge. All contributors must follow the core engineering disciplines and governing policies.

---

## 1. Governing Policies

- Changes must preserve the documented security invariants and the operator approval boundary. See [Security](SECURITY.md) and [Invariants](INVARIANTS.md).
- Model-generated instructions cannot grant permissions. Review security-sensitive changes with the project owner.
- **Evidence First:** Never claim code works, tests pass, or bugs are fixed without executing actual commands and observing the results.
- **Discussion vs Execution Gate:** Implementation must be explicitly authorized. Do not opportunistically expand scope or refactor unrelated components.

---

## 2. Code Quality and Preflight Checks

Before submitting pull requests:
1. Format and lint check:
   ```bash
   python -m ruff check subagentbridge tests
   python -m mypy subagentbridge
   python -m bandit -r subagentbridge
   ```
2. Run the full unit and integration test suite:
   ```bash
   python -m unittest discover -s tests -p "test_*.py"
   ```
3. Run the acceptance matrix suite:
   ```bash
   python -m unittest tests/test_acceptance_matrix_e01_e21.py
   ```

---

## 3. Pull Request Guidelines

- Scoped PRs: Focus on one cohesive deliverable at a time.
- No Force Pushing: Never rewrite shared branch history.
- Preserve QA Gates: Never delete, skip, or weaken QA tests to force a green test suite.
- Human Review: All pull request merges remain human-authorized.
