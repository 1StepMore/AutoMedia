.PHONY: install install-dev install-mcp test test-coverage test-e2e \
        lint lint-fix typecheck mcp clean workspace-clean pre-commit doctor

# Interpreter for every recipe.  Override it explicitly when the repo venv is
# not the first `python` on PATH, e.g. on Windows native:
#     make doctor PYTHON=.venv_win/Scripts/python.exe
# on WSL / Linux:
#     make doctor PYTHON=.venv/bin/python
# The default stays a bare name so CI and activated-venv shells keep working;
# `python3` is often a Microsoft Store stub on Windows, hence `python` (#536).
PYTHON ?= python

# =============================================================================
# AutoMedia — Development Makefile
# =============================================================================
# Targets mirror CI workflow (.github/workflows/ci.yml) and pre-commit hooks
# (.pre-commit-config.yaml).  Run `make <target>` from the repo root.

# ---- Interpreter guard (issue #536) -----------------------------------------
# Inlined as the first recipe line of every python-driven target: fails fast
# with exit 2 and a clear message when $(PYTHON) cannot import automedia,
# instead of letting the real target die with a bare "No module named
# automedia" from whatever interpreter happens to be first on PATH.
# Deliberately NOT a prerequisite target: tests/test_e2e_collection_guard.py
# pins `test-e2e:` to a bare target line followed by tab recipe lines, so the
# guard must live inside the recipe.  Install targets intentionally get no
# guard — on a fresh clone automedia is not importable yet.
define PY_GUARD
@$(PYTHON) -c "import automedia" 2>/dev/null || ( echo "ERROR: interpreter '$(PYTHON)' cannot import automedia - wrong interpreter on PATH. Activate the repo venv first, or pass it explicitly: make doctor PYTHON=.venv_win/Scripts/python.exe (Windows native) | PYTHON=.venv/bin/python (WSL/Linux)"; exit 2 )
endef

# ---- Installation ----------------------------------------------------------

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

install-mcp:
	$(PYTHON) -m pip install -e ".[mcp]"

# ---- Testing ---------------------------------------------------------------

test:
	$(PY_GUARD)
	$(PYTHON) -m pytest -q --tb=short

test-coverage:
	$(PY_GUARD)
	$(PYTHON) -m pytest --cov=src/automedia

test-e2e:
	$(PY_GUARD)
	$(PYTHON) -m pytest tests/test_e2e/ -v -o addopts=""

# ---- Code Quality ----------------------------------------------------------

lint:
	$(PYTHON) -m ruff check .

lint-fix:
	$(PYTHON) -m ruff check . --fix

typecheck:
	$(PYTHON) -m mypy src/automedia/ --ignore-missing-imports

# ---- MCP Server ------------------------------------------------------------

mcp:
	$(PY_GUARD)
	$(PYTHON) -m automedia.mcp.server

# ---- Utilities -------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache *.egg-info

# Workspace hygiene (issue #288): default dry-run, pass CLEAN=yes to delete.
# Prints every path first; never removes anything git tracks.
workspace-clean:
	./scripts/clean_workspace.sh --dry-run
	@echo ""
	@echo "Run 'make CLEAN=yes workspace-clean' to actually delete."
ifneq ($(CLEAN),)
	./scripts/clean_workspace.sh --yes
endif

pre-commit:
	$(PYTHON) -m pre_commit run --all-files

doctor:
	$(PY_GUARD)
	$(PYTHON) -m automedia doctor
