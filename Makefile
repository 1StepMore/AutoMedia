.PHONY: install install-dev install-mcp test test-coverage test-e2e \
        lint lint-fix typecheck mcp clean pre-commit doctor

# =============================================================================
# AutoMedia — Development Makefile
# =============================================================================
# Targets mirror CI workflow (.github/workflows/ci.yml) and pre-commit hooks
# (.pre-commit-config.yaml).  Run `make <target>` from the repo root.

# ---- Installation ----------------------------------------------------------

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

install-mcp:
	pip install -e ".[mcp]"

# ---- Testing ---------------------------------------------------------------

test:
	python -m pytest -q --tb=short

test-coverage:
	python -m pytest --cov=src/automedia

test-e2e:
	python -m pytest tests/test_e2e/ -v

# ---- Code Quality ----------------------------------------------------------

lint:
	ruff check .

lint-fix:
	ruff check . --fix

typecheck:
	mypy src/automedia/ --ignore-missing-imports

# ---- MCP Server ------------------------------------------------------------

mcp:
	python -m automedia.mcp.server

# ---- Utilities -------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache *.egg-info

pre-commit:
	pre-commit run --all-files

doctor:
	python -c "from automedia.core.doctor import Doctor; Doctor().check()"
