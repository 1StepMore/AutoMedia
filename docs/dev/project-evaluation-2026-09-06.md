# Project Evaluation — Pain Points

**Date:** 2026-09-06
**Scope:** Full codebase scan across agent-orientation, robustness, code quality, CI/CD, security, documentation, modularity
**Overall Score:** 8.3/10

## P0 — Security & Reliability

1. **No MCP server authentication** — all callers have equal access. Risky if exposed over network. Add token-based or mTLS auth.

2. **156 broad `except Exception` blocks** — especially in `runner.py` (10), `llm_client.py` (9), `gate_engine.py` (6). Masks real bugs, makes debugging harder. Narrow to specific exception types.

3. **No config schema validation on merged output** — `config_loader.py` returns raw dicts. Invalid values silently propagate to runtime failures.

## P1 — Type Safety & Code Quality

4. **Mypy is lenient** — no `strict`, no `disallow_untyped_defs`, no `disallow_any_generics`. Many functions lack type annotations with no enforcement.

5. **Ruff rules are incomplete** — missing `C4` (comprehensions), `PERF` (performance), `RUF` (ruff-specific), `PLR/PLC/PLE` (pylint). Many `noqa` comments reference rules not in the select list (dead weight).

6. **Docstring coverage at 50%** — `interrogate` configured with `fail-under = 50` and `continue-on-error: true` in CI. Not enforced.

## P2 — Architecture & Extensibility

7. **Gate engine complexity** — `gate_engine.py` handles state, pause/resume, retry, director mode. Approaching god-class territory. Consider splitting into state machine + executor + director.

8. **No dynamic plugin system** — adding gates/platforms requires code changes + restart. Could benefit from entry_points or dynamic loading.

9. **Import ordering hacks** — `adapters/__init__.py` uses `# noqa: E402` for initialization-order-dependent imports.

## P3 — Developer Experience

10. **Mypy runs with `continue-on-error: true`** in CI — it's advisory, not blocking. Type errors accumulate silently.

11. **Coverage gate only in CI, not locally** — no `[tool.coverage]` config or `--cov-fail-under` in `pyproject.toml`. Developers don't see coverage locally.

12. **No auto-generated API docs** — no Sphinx/MkDocs setup. Manual docs drift from implementation over time.

## P4 — Testing Gaps

13. **Test matrix enforcement is partial** — pytest only blocks on Python 3.11; 3.12/3.13 failures are `continue-on-error: true`.

14. **Many validation scenarios are `unconfigured`** in CI — require real API keys, limiting agent self-testing coverage.

15. **No mutation testing** — no `mutmut` or similar to verify test quality beyond line coverage.

---

## Quick Wins (can do today)

- #5: Tighten ruff `select` — add `C4`, `PERF`, `RUF`
- #6: Bump `interrogate` `fail-under` to 70
- #11: Add `[tool.coverage]` section to `pyproject.toml`
- #10: Remove `continue-on-error: true` from mypy step in CI

## Medium Effort (1-3 days)

- #2: Narrow `except Exception` to specific types in top offenders
- #4: Enable mypy `strict = true`, fix resulting errors
- #7: Split `gate_engine.py` into state machine + executor + director

## Strategic (1+ week)

- #1: MCP server auth (token or mTLS)
- #3: Pydantic config validation on merged output
- #8: Dynamic plugin system via entry_points
