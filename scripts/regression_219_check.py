#!/usr/bin/env python3
"""Regression check for issue #219: G0 unsourced-number rewrite + halt.

Issue #219: the G0 fact-check gate halted a whole track the moment generated
copy contained an unsourced number (e.g. 「点击率高 30%」), the downstream
gates never ran, and the failure was not diagnosable.  The fix makes G0:

1. emit a structured failure reason (which sentence / number / citation is
   missing) on the failing gate result;
2. emit exactly ONE rewrite (``modified_content``) on the first failing
   attempt;
3. let the pipeline CONTINUE when that rewrite passes;
4. HALT after exactly one rewrite when it still fails, with the structured
   reason persisted somewhere readable (gate history / diff record).

This driver exercises the REAL ``G0FactCheck`` gate inside the REAL
``GateEngine`` with the LLM mocked at the lowest shared seam
(``automedia.core.llm_client._structured_completion_with_fallback``); no
network calls are made.  A tiny downstream sentinel gate records whether the
pipeline reached past G0.

Two modes (``REG219_MODE``):

* ``pass`` (default) — the rewrite fixes the copy, the re-check passes, the
  pipeline continues to the sentinel.  Guards: structured reason, one rewrite,
  pipeline continued.
* ``fail`` — the rewrite does not fix it, the pipeline must halt before the
  sentinel and persist the structured reason.  Guards: structured reason, one
  rewrite, halt + persisted reason.

On full success it prints ``REG219_G0_UNSOURCED_REWRITE_OK`` (pass mode) or
``REG219_G0_UNSOURCED_HALT_OK`` (fail mode) and exits 0.  On any missing
guard it prints one or more ``REG219_<GUARD>_MISSING`` lines and exits
non-zero.  Frozen guard names:

* ``REG219_STRUCTURED_REASON_MISSING``
* ``REG219_REWRITE_NOT_EMITTED``
* ``REG219_PIPELINE_DID_NOT_CONTINUE``
* ``REG219_HALT_REASON_NOT_PERSISTED``

Pre-fix, G0 is ``failure_mode="stop"``: it halts immediately with no rewrite
and no structured reason, so BOTH modes fail the guards — that failure is the
honest RED this script exists to capture.  Synthetic data only; scratch state
lives under ``/tmp/automedia/reg219-*``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    # Run against the working tree, never a site-packages copy.
    sys.path.insert(0, str(_SRC))

# -- Frozen sentinels / guard names (do not rename) ------------------------
_SENTINEL_REWRITE_OK = "REG219_G0_UNSOURCED_REWRITE_OK"
_SENTINEL_HALT_OK = "REG219_G0_UNSOURCED_HALT_OK"

_GUARD_STRUCTURED = "REG219_STRUCTURED_REASON_MISSING"
_GUARD_REWRITE = "REG219_REWRITE_NOT_EMITTED"
_GUARD_CONTINUE = "REG219_PIPELINE_DID_NOT_CONTINUE"
_GUARD_HALT = "REG219_HALT_REASON_NOT_PERSISTED"

# -- Synthetic fixtures ----------------------------------------------------
_ORIGINAL_CONTENT = "据我们的渠道观察，这款产品的点击率高 30%，整体转化表现稳定。\n"
"""Generated copy carrying an unsourced figure (30%)."""

_REWRITTEN_CONTENT = "据我们的渠道观察，这款产品的点击率表现良好，整体转化表现稳定。\n"
"""What a correct rewrite looks like (the unsourced figure is gone)."""

_SOURCE_DATA: dict[str, Any] = {
    "url": "https://example.com/source-article",
    "published_date": "2024-06-01T00:00:00",
    "key_numbers": {"revenue": "42"},  # deliberately does NOT contain 30%
    "entities": [],
    "quotes": [],
}
"""Source material that contains no support for the 30% figure."""


class _SentinelGate:
    """Downstream sentinel: records whether execution reached past G0.

    Duck-typed to the ``gate_name`` / ``failure_mode`` / ``execute`` surface
    the engine consumes (mirrors ``tests/test_gate_retry.py::_FakeGate``) so
    it never pollutes the global gate registry.
    """

    def __init__(self) -> None:
        self.ran = False

    @property
    def gate_name(self) -> str:
        return "G99"

    @property
    def failure_mode(self) -> str:
        return "stop"

    def execute(self, gate_context: Any) -> dict[str, Any]:  # noqa: ANN401
        self.ran = True
        return {"passed": True, "gate": "G99"}


def _diag(message: str) -> None:
    """Emit a diagnostic on stderr so stdout stays contract-clean."""
    print(message, file=sys.stderr)


def _coerce_rewrite_response(model: Any, content: str) -> Any:  # noqa: ANN401
    """Best-effort instance of an unknown structured rewrite model.

    Only used when the post-fix G0 asks the LLM for a *structured* rewrite
    (the G1/G2 precedent is a deterministic local rewrite, which never reaches
    this branch).  Fills the content-bearing field with *content* and boolean
    fields with ``True`` so the caller receives a usable instance.
    """
    fields = getattr(model, "model_fields", None)
    if not isinstance(fields, dict):
        return content
    kwargs: dict[str, Any] = {}
    for name, field in fields.items():
        low = name.lower()
        if any(key in low for key in ("content", "rewrite", "text", "body", "draft")):
            kwargs[name] = content
        elif getattr(field, "annotation", None) is bool:
            kwargs[name] = True
    try:
        return model(**kwargs)
    except Exception:
        try:
            return model.model_construct(**kwargs)
        except Exception:  # last-resort coercion, never crash
            return content


def _persisted_reason(project_dir: Path) -> str | None:
    """Return a readable G0 failure reason persisted under *project_dir*.

    Inspects the two engine-native persistence surfaces:

    * ``.automedia/history.db`` — the ``PipelineHistoryHook`` rows
      (``G0:completed`` / ``G0:failed``) carry the result's ``error``;
    * ``.automedia/gate_diffs/*.json`` — the engine's rewrite diff records
      carry ``gate`` / ``error`` / ``reasons``.

    Returns ``None`` when nothing readable persisted (pre-fix: only a
    ``G0:started`` row exists, with no reason field).
    """
    try:
        from automedia.hooks.pipeline_history import _read_history

        for row in _read_history(str(project_dir)):
            action = str(row.get("action", ""))
            if not action.startswith("G0:"):
                continue
            try:
                meta = json.loads(row.get("metadata_json") or "{}")
            except ValueError:
                meta = {}
            error = meta.get("error")
            if isinstance(error, str) and error.strip():
                return f"history.db {action}: {error}"
            if meta.get("passed") is False and meta.get("status") != "started":
                return f"history.db {action}: gate reported failure"
    except Exception as exc:  # persistence probe is best-effort
        _diag(f"reg219: history.db probe failed: {type(exc).__name__}: {exc}")

    for path in sorted(project_dir.rglob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows = rec if isinstance(rec, list) else [rec]
        for row in rows:
            if not isinstance(row, dict) or row.get("gate") != "G0":
                continue
            error = row.get("error")
            if isinstance(error, str) and error.strip():
                return f"{path.name}: {error}"
            if row.get("reasons"):
                return f"{path.name}: reasons present"
    return None


def _build_context(project_dir: Path, draft: Path) -> dict[str, Any]:
    """Minimal real gate_context for G0 (content + source material + draft)."""
    return {
        "topic": "渠道观察",
        "content": _ORIGINAL_CONTENT,
        "source_data": _SOURCE_DATA,
        "project_dir": str(project_dir),
        "output_files": [{"type": "article", "path": str(draft), "md5": ""}],
        "config": {"enable_llm": True},
        "project_id": "reg219",
    }


def _run_engine(
    project_dir: Path,
    mode: str,
) -> tuple[list[dict[str, Any]], _SentinelGate, bool, str | None]:
    """Run the real G0 + sentinel through the real GateEngine.

    Returns ``(g0_attempts, sentinel, success, run_error)`` where
    *g0_attempts* is every result the real G0 returned (one per attempt).
    """
    from automedia.gates.fact_check import G0FactCheck
    from automedia.gates.llm_helpers import G0CheckResult
    from automedia.hooks.pipeline_history import PipelineHistoryHook
    from automedia.pipelines.gate_engine import GateEngine

    attempts: list[dict[str, Any]] = []
    check_calls = {"n": 0}

    def _fake_structured(
        prompt: str,
        *,
        response_format: type[Any],
        **_kwargs: object,
    ) -> object:
        """Call-order dispatcher for the mocked structured-completion seam.

        The first G0 check returns a FAILING verdict; a second check
        (the post-rewrite re-check) returns PASS in ``pass`` mode or FAIL in
        ``fail`` mode.  Any non-``G0CheckResult`` request is treated as the
        (optional) structured rewrite request.
        """
        if response_format is G0CheckResult:
            check_calls["n"] += 1
            if check_calls["n"] == 1:
                return G0CheckResult(
                    passed=False,
                    issues=[
                        "unsourced number '30%' in sentence: 「点击率高 30%」 — "
                        "no citation in the source material",
                    ],
                    confidence=0.2,
                )
            if mode == "pass":
                return G0CheckResult(passed=True, issues=[], confidence=0.95)
            return G0CheckResult(
                passed=False,
                issues=["unsourced number '30%' still present after the rewrite"],
                confidence=0.2,
            )
        return _coerce_rewrite_response(response_format, _REWRITTEN_CONTENT)

    g0 = G0FactCheck()
    _original_execute: Callable[[Any], dict[str, Any]] = g0.execute

    def _recording_execute(gate_context: Any) -> dict[str, Any]:  # noqa: ANN401
        result = _original_execute(gate_context)
        attempts.append(dict(result))
        return result

    g0.execute = _recording_execute  # type: ignore[method-assign]  # recording wrapper is behaviour-preserving

    sentinel = _SentinelGate()
    hook = PipelineHistoryHook()
    engine = GateEngine(
        [g0, sentinel],
        hooks=[hook],
        # Exactly one quality retry => at most one rewrite (issue #219 (b)).
        max_quality_retries=1,
        # No CW gate exists here; disable level-2 regeneration so only G0's
        # own rewrite path is exercised.
        max_regenerations=0,
    )

    draft_dir = project_dir / "01_content" / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft = draft_dir / "20260101_000000_draft.md"
    draft.write_text(_ORIGINAL_CONTENT, encoding="utf-8")

    gate_context = _build_context(project_dir, draft)

    success = False
    run_error: str | None = None
    with (
        patch(
            "automedia.core.llm_client._structured_completion_with_fallback",
            side_effect=_fake_structured,
        ),
        patch("automedia.core.llm_client._is_fake_mode", return_value=False),
        # No-network safety net: any unpatched provider path sees no providers
        # and raises immediately instead of dialling out.
        patch("automedia.core.llm_client._iter_provider_specs", return_value=[]),
    ):
        try:
            success, _results = engine.run(gate_context)
        except Exception as exc:  # a crash is reported, never hidden
            run_error = f"{type(exc).__name__}: {exc}"

    return attempts, sentinel, success, run_error


def main() -> int:
    mode = os.environ.get("REG219_MODE", "pass").strip().lower()
    if mode not in ("pass", "fail"):
        print(f"REG219_BAD_MODE: REG219_MODE must be 'pass' or 'fail', got {mode!r}")
        return 2

    # Determinism: a stray fake-LLM env var would bypass the patched seam.
    os.environ.pop("AUTOMEDIA_FAKE_LLM", None)

    work_root = Path("/tmp/automedia")  # noqa: S108 — synthetic isolated scratch
    work_root.mkdir(parents=True, exist_ok=True)
    project_dir = Path(tempfile.mkdtemp(prefix="reg219-", dir=str(work_root)))
    try:
        attempts, sentinel, success, run_error = _run_engine(project_dir, mode)

        rewrite_count = sum(1 for r in attempts if str(r.get("modified_content") or "").strip())
        failed_attempts = [r for r in attempts if r.get("passed") is not True]
        structured_reason = any(
            isinstance(r.get("error"), str) and r["error"].strip() for r in failed_attempts
        )
        persisted = _persisted_reason(project_dir)

        _diag(
            f"reg219: mode={mode} g0_attempts={len(attempts)} "
            f"failed_attempts={len(failed_attempts)} rewrite_emissions={rewrite_count} "
            f"sentinel_ran={sentinel.ran} success={success} run_error={run_error!r}"
        )
        for index, result in enumerate(attempts, start=1):
            _diag(
                f"reg219:   attempt {index}: passed={result.get('passed')!r} "
                f"error={result.get('error')!r} "
                f"has_modified_content={bool(str(result.get('modified_content') or '').strip())}"
            )
        _diag(f"reg219: persisted_reason={persisted!r}")

        failures: list[tuple[str, str]] = []

        # Guard 1 — structured failure reason on the failing gate result.
        if not structured_reason:
            failures.append(
                (
                    _GUARD_STRUCTURED,
                    f"no failed G0 attempt carried a non-empty result['error'] "
                    f"(g0_attempts={len(attempts)}, failed={len(failed_attempts)})",
                )
            )

        # Guard 2 — exactly one rewrite emitted.
        if rewrite_count != 1:
            failures.append(
                (
                    _GUARD_REWRITE,
                    f"expected exactly 1 rewrite emission, saw {rewrite_count}",
                )
            )

        if mode == "pass":
            # Guard 3 — pipeline continued past G0 to the sentinel.
            if not sentinel.ran or success is not True:
                failures.append(
                    (
                        _GUARD_CONTINUE,
                        f"pipeline did not continue past G0 "
                        f"(sentinel_ran={sentinel.ran}, success={success})",
                    )
                )
        else:
            # Guard 4 — halted before the sentinel AND reason persisted.
            if sentinel.ran:
                failures.append(
                    (
                        _GUARD_HALT,
                        "downstream sentinel ran — pipeline did not halt after the rewrite",
                    )
                )
            elif persisted is None:
                failures.append(
                    (
                        _GUARD_HALT,
                        "pipeline halted but no structured G0 reason was persisted "
                        "(no readable history/diff record with a reason)",
                    )
                )

        if failures:
            for guard, detail in failures:
                print(f"{guard}: {detail}")
            return 1

        print(_SENTINEL_REWRITE_OK if mode == "pass" else _SENTINEL_HALT_OK)
        return 0
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
