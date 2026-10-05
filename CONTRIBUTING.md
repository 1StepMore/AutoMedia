# Contributing to AutoMedia

Thank you for your interest in contributing to AutoMedia! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Testing](#testing)
- [Commit Conventions](#commit-conventions)
- [Branch Naming](#branch-naming)
- [Pull Request Workflow](#pull-request-workflow)
- [Adding a New Gate](#adding-a-new-gate)
- [Adding a New CLI Command](#adding-a-new-cli-command)
- [Adding a New Platform Adapter](#adding-a-new-platform-adapter)
- [Adding a New MCP Tool](#adding-a-new-mcp-tool)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Documentation](#documentation)
- [Questions & Support](#questions--support)

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold it. Please report unacceptable behavior to the project maintainers.

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/AutoMedia.git
   cd AutoMedia
   ```
3. **Add the upstream remote:**
   ```bash
   git remote add upstream https://github.com/1StepMore/AutoMedia.git
   ```
4. **Create a virtual environment** and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -e ".[dev]"
   ```
5. **Install pre-commit hooks:**
   ```bash
   pre-commit install
   ```

## Development Setup

### Prerequisites

- Python 3.11+
- pip (latest)

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

This installs all runtime dependencies plus:

- `pytest` and `pytest-cov` for testing
- `ruff` for linting
- `mypy` for type checking
- `pre-commit` for git hooks

## Code Style

AutoMedia uses **ruff** for linting and formatting.

### Ruleset

The following ruff rulesets are enabled:

- **E** — pycodestyle errors
- **F** — pyflakes (logic errors)
- **I** — isort (import ordering)
- **N** — pep8-naming (naming conventions)
- **W** — pycodestyle warnings
- **UP** — pyupgrade (modern Python idioms)

### Configuration

- **Line length:** 100 characters
- **Quotes:** Double quotes for strings
- **Imports:** Grouped in order: standard library, third-party, local; with a blank line between each group

### Running the Linter

```bash
make lint
# or directly:
ruff check .
```

Auto-fix issues where possible:

```bash
ruff check --fix .
```

## Testing

All tests must pass before a pull request is merged.

### Running Tests

```bash
make test
# or directly:
pytest
```

### With Coverage

```bash
make coverage
# or directly:
pytest --cov=src/automedia
```

### Test Categories

Tests are organized with markers:

```bash
pytest -m e2e        # End-to-end tests
pytest -m redline    # Red line enforcement tests
pytest -m slow       # Slow tests (may require external services)
```

### Writing Tests

- Place tests in the `tests/` directory.
- Use synthetic fixtures from `tests/fixtures/synth/` — never use production data.
- Use `tmp_path` for file system isolation.
- Import public API from `automedia/__init__.py`.

### Type Checking

```bash
make typecheck
# or directly:
mypy src/automedia/ --ignore-missing-imports
```

## Commit Conventions

We follow **Conventional Commits**. Every commit message must use one of the following prefixes:

| Prefix     | Usage                                  |
|------------|----------------------------------------|
| `feat:`    | A new feature                          |
| `fix:`     | A bug fix                              |
| `chore:`   | Routine tasks, dependency updates      |
| `docs:`    | Documentation changes                  |
| `refactor:`| Code changes that neither fix nor add  |
| `test:`    | Adding or updating tests               |
| `style:`   | Code style changes (formatting, etc.)  |
| `ci:`      | CI/CD configuration changes            |
| `perf:`    | Performance improvements               |

**Examples:**

```
feat: add topic scoring by engagement metrics
fix: handle empty SRT file in subtitle renderer
docs: update API reference for pipeline runner
refactor: extract config merge logic into dedicated module
test: add tests for gate engine failure modes
```

A scope may be appended in parentheses for additional context:

```
feat(pool): add deduplication by MD5 checksum
fix(gates): resolve V4 failure on missing brand asset
```

### Choosing the type by release scope

release-please decides whether to cut a public release from the commit **type
alone** — the scope in parentheses plays no part. So `fix(ci):` is a `fix`, and
it will force a public release even when the change is pure repo maintenance.
That produces a version bump whose only observable difference is the version
string, which is a release nobody asked for.

**Rule: if the change touches no user-visible path, use a hidden type.**

| Hidden (no release) | Visible (cuts a release) |
|---------------------|-------------------------|
| `chore:` `ci:` `test:` `refactor:` `style:` `build:` | `feat:` `fix:` `perf:` `docs:` `revert:` |

Internal paths are `.github/`, `tests/`, `scripts/`, `docs/dev/`, the
agent-client directories (`.claude/` `.codex/` `.opencode/` `.cursor/`
`.trae/`), `AGENTS.md`, `CONTRIBUTING.md`, `Makefile`,
`.pre-commit-config.yaml`, `.gitignore`, and source-generated artifacts such as
`docs/doc-inventory.md`. Everything else — including `src/**` and hand-written
docs under `docs/user/**` — is user-visible.

```
chore(ci): pin uv so the lock cannot drift        # internal  -> no release
fix(ci): stop the publish workflow racing itself  # internal  -> WRONG, forces one
```

Note that `docs:` is a **visible** type. A change that only adds documents under
`docs/dev/` is internal, so it wants `chore(docs):` or `refactor(docs):`, not
`docs:`.

The `release-scope` CI job enforces the visible-type half of this: an
internal-only change typed as `feat`/`fix`/etc. fails and asks you to retype it.
Two labels exist as explicit overrides — `release:user-visible` (internal paths,
but genuinely user-facing) and `release:skip` (user-visible paths, but the
release should be held). Reach for them rarely, and say why in the PR.

A release-please proposal is exempt from this check: its type is bot-fixed and
its diff spans a whole release interval, so the rule has nothing to judge. The
exemption is identified by content — a `release-please--` head branch, a
`chore(main): release ` title, and the release plumbing files in the diff — not
by the author, so a human PR cannot claim it.

A Dependabot pip PR is exempt too, and for the same reason: it is titled
`chore(deps):`, it cannot retype itself, and its diff is the generated lockfile.
The exemption requires **all four** conditions: the head branch must live in this
repository (`head.repo.full_name` equals the base repo), the head branch must
carry the `dependabot/` prefix (both `dependabot/uv/…` and `dependabot/pip/…` are
in live use), *every* changed path must be `uv.lock`, and the title type must be
hidden. So a fork PR named `dependabot/…`, a Dependabot PR that also touches
`src/**`, and a lockfile-only PR retyped `fix(deps)` are all still judged
normally.

`pyproject.toml` is **not** exempt. It is the install contract and it ships in
the sdist, so a manifest bump really is user-visible: it must be retyped with a
visible type (e.g. `fix(deps):`) by a human. That is the difference between the
lockfile and the manifest, and it is why only `uv.lock` is on the allowlist.

### Signed-off-by and squash merges

The `DCO` check requires a `Signed-off-by` trailer, and it runs on **PR commits**
— that is where the signoff has to be, and where it is enforced.

[ADR-005](docs/adr/ADR-005-issue-driven-commits.md) squash-merges to `main`, and
GitHub's squash does not carry the trailer onto the resulting `main` commit. So a
squash-merged commit on `main` normally has no `Signed-off-by`. **That is expected,
not a defect.**

Do not amend `main` to add it. On a release commit the tag has usually already
been cut and published, and moving a published tag to change a commit message
breaks release immutability for anyone who already installed from it. The tree
and artifacts are unaffected by the message, so there is nothing to gain.

## Branch Naming

Branches must follow a naming convention that mirrors commit types:

| Pattern                     | Example                         |
|-----------------------------|---------------------------------|
| `feat/short-description`    | `feat/add-tts-brand-assets`     |
| `fix/short-description`     | `fix/srt-timing-offset`         |
| `docs/short-description`    | `docs/update-cli-reference`     |
| `refactor/short-description`| `refactor/config-loader`        |
| `chore/short-description`   | `chore/update-dependencies`     |
| `test/short-description`    | `test/gate-engine-coverage`     |

Use hyphens to separate words. Keep descriptions concise but descriptive.

## Pull Request Workflow

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feat/my-feature main
   ```
2. **Make your changes**, committing with conventional commit messages.
3. **Keep your branch up to date**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```
4. **Run the full test suite** before pushing:
   ```bash
   make lint && make typecheck && make test
   ```
5. **Push your branch** and open a Pull Request against `main`.
6. **Ensure CI passes** — all checks must be green.
7. **Respond to review feedback** with additional commits on the same branch.

### PR Requirements

- The PR title should follow conventional commit format.
- Reference related issues in the PR description using `Fixes #issue-number`.
- Update documentation if your change introduces new behavior.
- Add tests for new functionality.

## Adding a New Gate

Gates are quality checkpoints in the AutoMedia pipeline. To add a new gate:

1. **Create a file** in `automedia/gates/` that inherits from `BaseGate`:
   ```python
   from automedia.gates.base import BaseGate

   class MyNewGate(BaseGate):
       _gate_name = "G6"        # Follow naming: G0-G5, V0-V7, L1-L4, D0, pre-gate, CW
        _failure_mode = "stop"   # "stop" or "retry"

       def execute(self, gate_context: dict) -> dict:
           # Your gate logic here
           return {"status": "passed"}
   ```

2. **Add a failure mode entry** in `automedia/gates/failure_modes.py`.

3. **Register in the pipeline** by adding the gate name to the appropriate gate list in `automedia/pipelines/runner.py` (one of `_AUTO_GATE_NAMES`, `_TEXT_ONLY_GATE_NAMES`, `_VIDEO_ONLY_GATE_NAMES`, or `_QA_ONLY_GATE_NAMES`).

4. **Create tests** in `tests/test_gates/`.

See `AGENTS.md` for the complete gate naming convention and pipeline ordering.

## Adding a New CLI Command

1. Create a file in `automedia/cli/commands/`.
2. Define a typer `app` with your command(s).
3. Register in `automedia/cli/app.py` via `app.add_typer()` (for subcommand groups) or `app.command()` (for standalone commands).

## Adding a New Platform Adapter

1. Create an adapter class in `automedia/adapters/` implementing the adapter protocol.
2. Register via `AdapterRegistry.register()`.
3. Or use the MCP tool `register_platform_adapter()`.

## Adding a New MCP Tool

1. Define a module-level handler function in `automedia/mcp/server.py`.
2. Register it inside `create_server()` via the `@mcp.tool()` decorator.

## Pre-commit Hooks

This project uses **pre-commit** to enforce code quality on every commit.

### Install

```bash
pre-commit install
```

### Run Manually

```bash
pre-commit run --all-files
```

### What It Checks

- Ruff linting (E, F, I, N, W, UP rulesets)
- Trailing whitespace
- End-of-file fixer
- YAML/JSON syntax validation
- Large file detection

## Documentation

If your change affects user-facing behavior:

- Update the relevant files in `docs/`
- Add or update CLI command documentation in `docs/user/cli-reference.md`
- Update `AGENTS.md` if adding new gates or changing architecture
- Run `make docs` to verify documentation builds correctly

## Questions & Support

- **GitHub Issues** — for bug reports and feature requests
- **Discussions** — for questions and general support
- **Pull Requests** — for code contributions

Before opening an issue, please search existing issues to avoid duplicates.

---

Thank you for contributing to AutoMedia!
