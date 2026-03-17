# Engineering Charter

Scope
- This repository follows a strict Python ^3.12 stack with Poetry 2.3.2.
- All contributions must pass formatting, linting, security checks, and tests locally and in CI.

Stack and Tooling
- Runtime: Python ^3.12 via pyenv
- Package/Env: Poetry 2.3.2
- Formatting: Black
- Linting: Ruff (as linter and import sorter)
- Types: mypy (strict-ish)
- Security: Bandit
- Tests: pytest + pytest-cov (coverage >= 80%)
- Git Hooks: pre-commit (mandatory)

Non-negotiables
- No secrets in the repo. Secret-scanning runs pre-commit and in CI.
- Code must type-check (mypy) and lint cleanly (ruff, black --check), and pass bandit.
- Coverage must stay >= 80% on PRs; raise thresholds as the project matures.

Commands
- make fmt   → format code (Black + Ruff --fix)
- make lint  → run Ruff, Black --check, mypy, Bandit
- make test  → run pytest with coverage gates
- make run   → run app entrypoint (adjust to your package)

CI
- GitHub Actions runs pre-commit, lint, bandit, mypy, and tests on pushes and PRs.

Directory Layout
- src/<package_name>/
- tests/
- configs at repo root: pyproject.toml, mypy.ini, ruff.toml, pytest.ini, .pre-commit-config.yaml

Review & PRs
- Keep PRs small and focused. Include rationale, screenshots/logs for behavior changes.
- Link tasks and update the task progress log upon merges.
