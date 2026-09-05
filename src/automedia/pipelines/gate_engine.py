"""Gate engine — sequential pipeline executor with hook dispatch.

Runs an ordered list of :class:`BaseGate` instances, dispatches lifecycle
hooks, and respects each gate's ``failure_mode`` to decide whether to
STOP the pipeline or continue on failure.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import tenacity
from structlog import get_logger

from automedia.exceptions import GateError
from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate
from automedia.hooks.protocol import GateHook
from automedia.pipelines.gate_types import (
    GateErrorResult,  # noqa: F401 — re-exported for backward compatibility
    GateProgressEvent,  # noqa: F401 — re-exported for backward compatibility
    PipelineProgress,
    ProgressData,  # noqa: F401 — re-exported for backward compatibility
    _hitl_lock,  # noqa: F401 — re-exported for backward compatibility
    _hitl_waiters,  # noqa: F401 — re-exported for backward compatibility
)

log = get_logger(__name__)

# Exception categorization for gate error handling.
_PERMANENT_EXCEPTIONS: tuple[type[Exception], ...] = (KeyError, ValueError, TypeError, GateError)
_TRANSIENT_EXCEPTIONS: tuple[type[Exception], ...] = (ConnectionError, TimeoutError)

# Content gates whose failing results may apply ``modified_content`` into the
# main content flow (quality-retry branch).  G1 (humanizer) and G2 (copy
# review) are ``failure_mode="retry"`` gates that emit ``modified_content``
# only when their checks fail.  The explicit allowlist guards the master
# draft in ``01_content/drafts/`` against D-gate/P-gate style platform
# rewrites, which also produce ``modified_content`` but must never clobber
# the main flow.
_CONTENT_GATES_WITH_REWRITE: frozenset[str] = frozenset({"G1", "G2"})

# Per-diff size cap (characters) for gate diff records under
# ``.automedia/gate_diffs/``.  A rewrite larger than this is stored
# truncated with ``"truncated": true`` instead of failing the pipeline.
_GATE_DIFF_MAX_CHARS = 200_000

# ``_hitl_lock`` and ``_hitl_waiters`` live in ``gate_types.py`` and are
# re-exported above for backward compatibility.

# Engine registry for MCP approve/reject tools (director mode).
# Maps ``project_id`` to ``GateEngine``.  Populated by ``run_full_pipeline``
# in ``runner.py`` and consumed by ``approve_gate`` / ``reject_gate`` /
# ``get_pending_approvals`` in ``tools.py``.
_engine_registry: dict[str, GateEngine] = {}
_engine_registry_lock = threading.Lock()


def get_registered_engine(project_id: str) -> GateEngine | None:
    with _engine_registry_lock:
        return _engine_registry.get(project_id)


def register_engine(project_id: str, engine: GateEngine) -> None:
    with _engine_registry_lock:
        _engine_registry[project_id] = engine


def unregister_engine(project_id: str) -> None:
    with _engine_registry_lock:
        _engine_registry.pop(project_id, None)


def list_registered_engines() -> dict[str, GateEngine]:
    with _engine_registry_lock:
        return dict(_engine_registry)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AssetInfo:
    """Metadata about a produced asset file."""

    type: str
    path: str
    platform: str = ""
    md5: str = ""


@dataclass
class GateLogEntry:
    """Log entry for a single gate execution."""

    gate_name: str
    status: Literal["passed", "failed", "error"]
    duration_s: float
    error: str | None = None


@dataclass
class PipelineResult:
    """Result of a full pipeline execution.

    ``affected_downstream`` is failure-localization metadata: when a gate
    fails, the runner fills it with the gates downstream of the first
    failed gate (restricted to the mode's gate list) — the gates that did
    not run because of the failure. Empty on success. ``error`` is only
    set for pipeline-level (unexpected) errors, never for gate failures.
    """

    status: Literal["success", "failed", "partial"] = "success"
    project_id: str = ""
    project_dir: str = ""
    topic: str = ""
    brand: str = ""
    assets: list[AssetInfo] = field(default_factory=list)
    gates_log: list[GateLogEntry] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0
    total_duration_s: float = 0.0
    error: str | None = None
    affected_downstream: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    workflow: str = ""
    """Name of the workflow used for this pipeline run, if any."""


# GateErrorResult, ProgressData, GateProgressEvent, and PipelineProgress
# are defined in gate_types.py and re-exported via the import above.


# ---------------------------------------------------------------------------
# GateEngine
# ---------------------------------------------------------------------------


class GateEngine:
    """Sequential pipeline executor.

    Parameters
    ----------
    gates:
        Ordered list of :class:`BaseGate` instances to execute.
    hooks:
        Optional list of :class:`GateHook` observers notified at each
        lifecycle event.
    max_retries:
        Maximum retry attempts for gates with ``failure_mode="retry"``
        when a transient exception is raised.  Default: 3.
    retry_delay:
        Base delay in seconds for exponential backoff between retries.
        Actual delay = ``retry_delay * 2 ** (attempt - 1)``.  Default: 1.0.
    max_quality_retries:
        Maximum retry attempts for gates that return ``passed=False``
        with ``failure_mode="retry"`` (level 1 quality-feedback retry).
        The same gate is re-executed with the same content up to this
        many times.  Default: 3.  Set to 0 to disable quality retry.
    max_regenerations:
        Maximum content regeneration attempts when level 1 quality retries
        are exhausted for a gate with ``failure_mode="retry"``.  Each
        regeneration re-runs the CW (content writer) gate with failure
        feedback and executes all gates from CW onward.  Default: 2.
        Set to 0 to disable level 2 regeneration.
    """

    def __init__(
        self,
        gates: list[BaseGate],
        hooks: list[GateHook] | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        max_quality_retries: int = 3,
        max_regenerations: int = 2,
        pause_on_approval: bool = False,
    ) -> None:
        """Initialize the gate engine with an ordered list of gates.

        Args:
            gates: Ordered list of BaseGate instances to execute sequentially.
            hooks: Optional lifecycle observers notified at each gate event.
            max_retries: Max retry attempts for gates with failure_mode="retry".
            retry_delay: Base delay in seconds for exponential backoff.
            max_quality_retries: Max quality retry attempts for gates that
                return ``passed=False`` with ``failure_mode='retry'``.
            max_regenerations: Max content regeneration attempts when level 1
                quality retries are exhausted.  Default: 2.
            pause_on_approval: When ``True``, gates with ``requires_approval``
                in their context will pause after execution and wait for an
                external call to ``resume()``.  Default: ``False`` (backward
                compatible).
        """
        self._gates = list(gates)
        self._hooks: list[GateHook] = list(hooks) if hooks else []
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._max_quality_retries = max_quality_retries
        self._max_regenerations = max_regenerations
        self._pause_on_approval = pause_on_approval
        # Per-gate approval coordination (thread-safe via lock + Event).
        self._approval_events: dict[str, threading.Event] = {}
        self._approval_results: dict[str, dict[str, Any]] = {}
        self._approval_lock = threading.Lock()
        # Per-run gate-diff sequence counters, keyed by gate name
        # (todo 8: <gate>_<seq>.json under .automedia/gate_diffs/).
        self._gate_diff_seq: dict[str, int] = {}
        # Sub-engines created by level-2 regeneration inherit this flag so
        # the outer engine can tell reject-halts from mere retry exhaustion.
        self._hitl_rejected_halt = False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _dispatch_before(self, gate_name: str, context: GateContext | dict[str, Any]) -> None:
        """Notify all registered hooks that *gate_name* is about to run."""
        log.debug("hooks.dispatch_before", gate_name=gate_name, hook_count=len(self._hooks))
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.before_gate(gate_name, ctx)

    def _dispatch_after(
        self, gate_name: str, context: GateContext | dict[str, Any], result: dict[str, Any]
    ) -> None:
        """Notify all registered hooks that *gate_name* completed successfully."""
        log.debug("hooks.dispatch_after", gate_name=gate_name, hook_count=len(self._hooks))
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.after_gate(gate_name, ctx, result)

    def _dispatch_failed(
        self, gate_name: str, context: GateContext | dict[str, Any], error: Exception
    ) -> None:
        """Notify all registered hooks that *gate_name* raised an exception."""
        log.debug(
            "hooks.dispatch_failed",
            gate_name=gate_name,
            error=str(error),
            hook_count=len(self._hooks),
        )
        ctx = context.to_dict() if isinstance(context, GateContext) else context
        for hook in self._hooks:
            hook.on_gate_failed(gate_name, ctx, error)

    def _gate_requires_approval(self, gate_name: str, gate_context: dict[str, Any]) -> bool:
        """Check whether *gate_name* needs approval before continuing.

        Returns ``True`` only when ``pause_on_approval`` is enabled AND
        the gate context indicates this gate requires approval.
        ``requires_approval`` can be a boolean (applies to all gates) or
        a sequence of gate names (applies only to named gates).
        """
        if not self._pause_on_approval:
            return False
        ra = gate_context.get("requires_approval", False)
        if isinstance(ra, list | tuple | set):
            return gate_name in ra
        return bool(ra)

    def _apply_modified_content(
        self,
        gate_name: str,
        gate_context: GateContext | dict[str, Any],
        result: dict[str, Any],
        apply_state: dict[str, Any],
    ) -> None:
        """Apply a failing attempt's ``modified_content`` into the main flow.

        Content gates (G1 humanizer, G2 copy review) emit ``modified_content``
        ONLY when their checks fail (``passed=False``), so the apply point is
        the quality-retry loop — the retry must evaluate the improved text
        instead of the original.  The applied change is also persisted to the
        current draft file registered by CW in ``gate_context["output_files"]``
        (type ``"article"``), so the on-disk draft in ``01_content/drafts/``
        matches what downstream gates consume.

        *apply_state* snapshots the pre-apply content and draft text on the
        first apply so :meth:`_rollback_applied_content` can restore them when
        the gate ultimately fails through all retries — a failed chain must
        never leave a rewrite behind as final content (no partial write).

        md5 consequence: rewriting the draft post-CW invalidates the CW md5
        recorded by the md5 hook (runner ``_record_gate_md5s``).  After
        applying a rewrite we refresh that record so downstream gate md5
        comparisons do not go stale.  We only refresh when a CW record already
        exists — a standalone engine run without md5 state must not gain one
        as a side effect.  Rolling back restores the original draft bytes,
        which restores the original md5 too (re-recorded for symmetry).

        Note: ``after_gate`` hook observers dispatched for the *failing*
        attempt see the pre-apply content — acceptable, hooks observe gate
        events, not the retry-apply handoff.

        Before the rewrite is applied, a per-gate diff record is persisted to
        ``<project_dir>/.automedia/gate_diffs/<gate>_<seq>.json`` (texts only —
        before/after content plus the failing result's per-check reasons; the
        unified diff is computed at render time).  A write failure never fails
        the pipeline.

        An explicit allowlist scopes this to the main content flow so a
        D-gate/P-gate style platform rewrite (which also emits
        ``modified_content``) can never clobber the master draft — and, by the
        same guard, produces no diff record either.
        """
        rewrite = result.get("modified_content")
        if not rewrite or gate_name not in _CONTENT_GATES_WITH_REWRITE:
            return

        before = gate_context.get("content", "")

        if not apply_state:
            apply_state["original_content"] = gate_context.get("content", "")
            apply_state["gate_name"] = gate_name
            draft_path = self._resolve_current_draft(gate_context)
            if draft_path is not None:
                try:
                    with open(draft_path, encoding="utf-8") as fh:
                        apply_state["original_draft"] = fh.read()
                    apply_state["draft_path"] = draft_path
                except OSError as exc:
                    # Cannot snapshot → cannot restore → do not touch the
                    # draft at all; apply into context only.
                    log.warning(
                        "gate.modified_content_draft_unreadable",
                        gate_name=gate_name,
                        draft_path=draft_path,
                        error=str(exc),
                    )

        gate_context["content"] = rewrite
        apply_state["applied"] = True
        try:
            self._write_gate_diff_record(
                gate_name=gate_name,
                gate_context=gate_context,
                before=str(before),
                after=str(rewrite),
                result=result,
                applied=True,
            )
        except Exception as exc:  # noqa: BLE001 — diff capture must never fail the pipeline
            log.warning("gate.diff_record.write_failed", gate_name=gate_name, error=str(exc))
        log.info(
            "gate.modified_content_applied",
            gate_name=gate_name,
            content_length=len(rewrite),
        )

        draft_path = apply_state.get("draft_path")
        if draft_path is None:
            log.warning(
                "gate.modified_content_draft_missing",
                gate_name=gate_name,
                hint="no article output_file registered; context updated only",
            )
            return
        try:
            with open(draft_path, "w", encoding="utf-8") as fh:
                fh.write(rewrite)
        except OSError as exc:
            # Context carries the improved text either way; the pipeline must
            # not fail because the draft rewrite could not be persisted.
            log.error(
                "gate.modified_content_draft_write_failed",
                gate_name=gate_name,
                draft_path=str(draft_path),
                error=str(exc),
            )
            return

        self._refresh_cw_md5(gate_name, gate_context, draft_path)

    def _rollback_applied_content(
        self,
        gate_context: GateContext | dict[str, Any],
        apply_state: dict[str, Any],
        result: dict[str, Any] | None = None,
    ) -> None:
        """Restore context and draft to their pre-apply state.

        Called when a content gate fails through all quality retries (or an
        exception aborts the retry chain): the failed chain's rewrites must
        not survive as final content — the pipeline failure state must match
        the pre-change behavior exactly.

        When *result* carries the final failing attempt's ``modified_content``
        and no diff record was written during the retry chain (i.e. the chain
        aborted before any apply), that would-be rewrite is still recorded
        with ``applied=False`` so the director can see what the gate wanted to
        change — a failed chain never promotes the rewrite, but the record
        preserves it.  When rewrites WERE applied during the chain, the last
        failing attempt's unapplied rewrite is recorded with ``applied=False``
        BEFORE the restore, so the director also sees the final attempt that
        exhausted the budget (and still sees every applied rewrite, whose
        records were written at apply time with ``applied=True``).
        """
        rewrite = (result or {}).get("modified_content")
        if (
            rewrite
            and apply_state.get("gate_name") in _CONTENT_GATES_WITH_REWRITE
            and not apply_state.get("final_attempt_recorded")
        ):
            applied = bool(apply_state.get("applied"))
            try:
                self._write_gate_diff_record(
                    gate_name=str(apply_state.get("gate_name", "")),
                    gate_context=gate_context,
                    before=str(
                        apply_state.get("original_content", "")
                        if not applied
                        else gate_context.get("content", "")
                    ),
                    after=str(rewrite),
                    result=result or {},
                    applied=False,
                )
            except Exception as exc:  # noqa: BLE001 — diff capture must never fail the pipeline
                log.warning(
                    "gate.diff_record.write_failed",
                    gate_name=str(apply_state.get("gate_name", "")),
                    error=str(exc),
                )
            apply_state["final_attempt_recorded"] = True
        if not apply_state.get("applied"):
            return
        gate_context["content"] = apply_state.get("original_content", "")
        draft_path = apply_state.get("draft_path")
        original_draft = apply_state.get("original_draft")
        if draft_path is None or original_draft is None:
            return
        try:
            with open(draft_path, "w", encoding="utf-8") as fh:
                fh.write(original_draft)
        except OSError as exc:
            log.error(
                "gate.modified_content_rollback_failed",
                draft_path=str(draft_path),
                error=str(exc),
            )
            return
        # The restored bytes match the original CW md5 again; re-record in
        # case the apply step refreshed the record with the rewrite's md5.
        self._refresh_cw_md5("CW", gate_context, draft_path)
        apply_state.clear()

    def _next_gate_diff_seq(self, gate_name: str) -> int:
        """Next per-run sequence number for *gate_name*'s diff records."""
        seq = self._gate_diff_seq.get(gate_name, 0) + 1
        self._gate_diff_seq[gate_name] = seq
        return seq

    def _write_gate_diff_record(
        self,
        *,
        gate_name: str,
        gate_context: GateContext | dict[str, Any],
        before: str,
        after: str,
        result: dict[str, Any],
        applied: bool,
    ) -> None:
        """Persist one original-vs-modified diff record for *gate_name*.

        Writes ``<project_dir>/.automedia/gate_diffs/<gate>_<seq>.json`` with
        the pre-change content, the rewrite, the failing result's per-check
        reasons, and the applied flag.          TEXTS ONLY — the unified diff is
        computed at render time, never stored.
        """
        try:
            project_dir = str(gate_context.get("project_dir", "") or "")
            if not project_dir:
                return

            max_chars = _GATE_DIFF_MAX_CHARS
            truncated = len(before) > max_chars or len(after) > max_chars
            if truncated:
                log.warning(
                    "gate.diff_record.truncated",
                    gate_name=gate_name,
                    before_len=len(before),
                    after_len=len(after),
                    max_chars=max_chars,
                )
                before = before[:max_chars]
                after = after[:max_chars]

            record = {
                "gate": gate_name,
                "timestamp": datetime.now(UTC).isoformat(),
                "before": before,
                "after": after,
                "reasons": result.get("checks", []),
                "error": result.get("error"),
                "applied": applied,
                "truncated": truncated,
            }

            diffs_dir = Path(project_dir) / ".automedia" / "gate_diffs"
            diffs_dir.mkdir(parents=True, exist_ok=True)
            seq = self._next_gate_diff_seq(gate_name)
            path = diffs_dir / f"{gate_name}_{seq}.json"
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            log.info(
                "gate.diff_record.written",
                gate_name=gate_name,
                path=str(path),
                applied=applied,
            )
        except Exception as exc:  # noqa: BLE001 — diff capture must never fail the pipeline
            log.warning(
                "gate.diff_record.write_failed",
                gate_name=gate_name,
                error=str(exc),
            )

    @staticmethod
    def _refresh_cw_md5(
        gate_name: str,
        gate_context: GateContext | dict[str, Any],
        draft_path: str,
    ) -> None:
        """Re-record the CW md5 entry for *draft_path* when one already exists.

        Rewriting the draft post-CW invalidates the CW md5 recorded by the
        md5 hook; refreshing keeps downstream comparisons from going stale.
        Guarded: never creates md5 state as a side effect.
        """
        try:
            from automedia.hooks.md5_tracker import get_pipeline_md5, record_md5

            project_dir = gate_context.get("project_dir", "")
            if project_dir and get_pipeline_md5(project_dir).get("gates", {}).get("CW"):
                record_md5(project_dir, "CW", draft_path)
        except (OSError, FileNotFoundError, ValueError) as exc:
            log.warning(
                "gate.modified_content_md5_refresh_failed",
                gate_name=gate_name,
                error=str(exc),
            )

    @staticmethod
    def _resolve_current_draft(
        gate_context: GateContext | dict[str, Any],
    ) -> str | None:
        """Return the current article draft path from ``output_files``.

        CW is the only writer of ``01_content/drafts/`` and registers its
        output as ``{"type": "article", "path": ...}``.  Returns ``None``
        when no article entry exists (e.g. engine runs without CW).
        """
        output_files = gate_context.get("output_files") or []
        if not isinstance(output_files, list):
            return None
        for entry in reversed(output_files):
            if isinstance(entry, dict) and entry.get("type") == "article":
                path = entry.get("path")
                if path:
                    return str(path)
        return None

    # ------------------------------------------------------------------
    # Retry helper
    # ------------------------------------------------------------------

    def _execute_gate_with_retry(
        self,
        gate: BaseGate,
        gate_context: GateContext | dict[str, Any],
        fm: str,
        gate_name: str,
        progress: PipelineProgress | None = None,
    ) -> dict[str, Any]:
        """Execute *gate* with tenacity retry for transient exceptions.

        Only applies when ``fm == "retry"``.  Permanent and unknown
        exceptions are never retried — they propagate immediately.
        """
        if fm != "retry":
            return gate.execute(gate_context)

        _attempt_counter = {"n": 0}

        def _before_sleep(retry_state: tenacity.RetryCallState) -> None:
            """Log retry attempt info and update progress before sleeping."""
            _attempt_counter["n"] += 1
            attempt = _attempt_counter["n"]
            delay = float(retry_state.upcoming_sleep or 0)
            exc = retry_state.outcome.exception() if retry_state.outcome else None
            log.info(
                "gate.retry.attempt",
                gate_name=gate_name,
                attempt=attempt,
                max_retries=self._max_retries,
                delay_s=delay,
                error=str(exc) if exc else "",
            )
            if progress:
                progress.on_gate_end(
                    gate_name,
                    False,
                    0.0,
                    attempt_number=_attempt_counter["n"],
                    retry_level="tenacity",
                )
                progress.on_gate_start(
                    gate_name,
                    attempt_number=_attempt_counter["n"] + 1,
                    retry_level="tenacity",
                )

        retryer = tenacity.Retrying(
            stop=tenacity.stop_after_attempt(self._max_retries),
            wait=tenacity.wait_exponential(multiplier=self._retry_delay),
            retry=tenacity.retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
            before_sleep=_before_sleep,
            reraise=True,
        )
        result = retryer(gate.execute, gate_context)

        if _attempt_counter["n"] > 0:
            result.setdefault("retry_count", _attempt_counter["n"])
        return result

    # ------------------------------------------------------------------
    # Level 2: content regeneration (re-run from CW gate)
    # ------------------------------------------------------------------

    def _handle_level2_regeneration(
        self,
        gate_context: GateContext | dict[str, Any],
        failed_gate_name: str,
        failure_result: dict[str, Any],
        progress: PipelineProgress | None = None,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Level 2 recovery — regenerate content by re-running from CW.

        Increments ``gate_context["_regeneration_count"]`` and, when the
        count is below ``_max_regenerations``, re-runs all gates from the
        CW gate forward with ``gate_context["failure_feedback"]`` set so
        the content writer receives information about what failed.

        When the regeneration budget is exhausted, sets
        ``gate_context["_level2_exhausted"] = True`` for Task 20
        escalation.

        Returns
        -------
        tuple[bool, list[dict]]
            ``(all_ok, results_from_cw)`` where *results_from_cw* covers
            gates from CW through the end of the pipeline.
        """
        _local_max_regen = gate_context.get("max_regenerations", self._max_regenerations)
        current = gate_context.get("_regeneration_count", 0)
        if current >= _local_max_regen:
            gate_context["_level2_exhausted"] = True

            # Populate _escalated_gates for H0 human escalation (Task 20)
            escalated: list[dict[str, Any]] = gate_context.setdefault(  # type: ignore[typeddict-unknown-key]  # _escalated_gates is not a key in GateContext TypedDict
                "_escalated_gates", []
            )
            escalated.append(
                {
                    "gate_name": failed_gate_name,
                    "error": failure_result.get("error", "unknown"),
                    "regeneration_count": current,
                }
            )

            log.warning(
                "engine.level2.exhausted",
                regenerations_attempted=current,
                max_regenerations=_local_max_regen,
                failed_gate=failed_gate_name,
                escalated_gates=list(escalated),
            )
            return False, []

        new_count = current + 1
        gate_context["_regeneration_count"] = new_count

        feedback: dict[str, Any] = {
            "failed_gate": failed_gate_name,
            "error": failure_result.get("error", "unknown"),
            "regeneration_attempt": new_count,
            "max_regenerations": _local_max_regen,
        }
        gate_context["failure_feedback"] = feedback

        log.info(
            "engine.level2.regeneration",
            failed_gate=failed_gate_name,
            attempt=new_count,
            max_regenerations=_local_max_regen,
            error=feedback["error"],
        )

        # Locate the CW gate in the gate list
        cw_idx = -1
        for i, g in enumerate(self._gates):
            if g.gate_name == "CW":
                cw_idx = i
                break

        if cw_idx == -1:
            log.error(
                "engine.level2.no_cw_gate",
                hint="Cannot regenerate without a CW gate in the list",
            )
            return False, []

        # Clear content fields so CW regenerates fresh content
        gate_context["content"] = ""
        gate_context["draft"] = None

        # Build a sub-engine with gates from CW onward and re-run
        sub_gates = self._gates[cw_idx:]
        sub_engine = GateEngine(
            gates=sub_gates,
            hooks=self._hooks,
            max_retries=self._max_retries,
            retry_delay=self._retry_delay,
            max_quality_retries=self._max_quality_retries,
            max_regenerations=_local_max_regen,
        )
        sub_ok, sub_results = sub_engine._run(
            gate_context,
            early_stop=True,
            progress=progress,
        )
        # Propagate a human rejection out of the sub-run: a rejected HITL
        # gate is a director decision, not a recoverable quality failure.
        if sub_engine._hitl_rejected_halt:
            self._hitl_rejected_halt = True

        return sub_ok, sub_results  # type: ignore[return-value]  # sub_engine._run() returns union; cannot narrow on early_stop param

    # ------------------------------------------------------------------
    # Private gate execution loop
    # ------------------------------------------------------------------

    def _run(
        self,
        gate_context: GateContext | dict[str, Any],
        *,
        early_stop: bool = True,
        progress: PipelineProgress | None = None,
    ) -> tuple[bool, list[dict[str, Any]]] | list[dict[str, Any]]:
        """Execute gates sequentially. Returns ``(all_ok, results)`` when
        *early_stop* is ``True``, or just *results* when ``False``."""
        results: list[dict[str, Any]] = []
        all_ok = True
        total_gates = len(self._gates)

        _gate_loop_idx = 0
        while _gate_loop_idx < len(self._gates):
            gate = self._gates[_gate_loop_idx]
            gate_idx = _gate_loop_idx + 1
            gate_name = gate.gate_name
            gate_context["_gate_name"] = gate_name
            gate_context["_quality_retry_count"] = 0  # Reset per gate for quality retry tracking
            # Snapshot/rollback state for modified_content applies in the
            # quality-retry branch (no partial writes on exhausted retries).
            _rewrite_apply_state: dict[str, Any] = {}

            # NEW: Check cancellation
            if progress and progress.is_cancelled():
                log.warning("gate_engine.cancelled", gate_name=gate_name)
                break

            # NEW: Check skip flag
            if progress and progress.consume_skip_gate() == gate_name:
                log.info("gate_engine.skipped", gate_name=gate_name)
                if progress:
                    progress.on_gate_end(gate_name, True, 0.0, detail="skipped via MCP")
                _gate_loop_idx += 1
                continue

            # NEW: Wait if paused (between gates, not during a gate)
            if progress and not progress.wait_if_paused():
                break  # cancelled during pause

            # Backward compatibility: accept "rewrite" → map to "retry"
            fm = gate.failure_mode
            if fm == "rewrite":
                warnings.warn(
                    f"failure_mode='rewrite' is deprecated for gate '{gate_name}', "
                    f"use failure_mode='retry' instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                fm = "retry"

            log.info(
                "gate.start",
                gate_name=gate_name,
                gate_idx=gate_idx,
                total_gates=total_gates,
                failure_mode=fm,
            )

            if progress:
                progress.on_gate_start(gate_name)

            self._dispatch_before(gate_name, gate_context)
            start = time.monotonic()

            try:
                result = self._execute_gate_with_retry(
                    gate,
                    gate_context,
                    fm,
                    gate_name,
                    progress,
                )
                duration = time.monotonic() - start
                result["duration_s"] = duration
                results.append(result)

                # HITL: when gate returns awaiting_hitl, pause for human review
                if result.get("status") == "awaiting_hitl" and progress:
                    timeout_s = result.get("timeout_s", 86400)
                    progress.on_gate_awaiting_hitl(gate_name)
                    hitl_ok = progress.wait_for_hitl(
                        project_dir="",
                        timeout=timeout_s,
                    )
                    result["_hitl_approved"] = hitl_ok
                    if not hitl_ok:
                        # Human rejected: convert to a stop-failure outcome so
                        # the pipeline halts exactly like a failed "stop" gate
                        # (h0_human_review docstring contract).
                        result["passed"] = False
                        result["error"] = (
                            result.get("error") or f"gate {gate_name} rejected by human review"
                        )
                        self._hitl_rejected_halt = True

                passed = result.get("passed", True)
                if progress:
                    progress.on_gate_end(
                        gate_name, passed, duration, detail=result.get("error", "")
                    )

                if passed:
                    all_ok = True
                    log.info("gate.passed", gate_name=gate_name, duration_s=duration)
                    self._dispatch_after(gate_name, gate_context, result)
                else:
                    all_ok = False
                    log.warning(
                        "gate.failed",
                        gate_name=gate_name,
                        duration_s=duration,
                        failure_mode=fm,
                    )
                    if fm == "stop":
                        if early_stop:
                            return False, results
                        return results

                    # Level 1: quality-feedback retry
                    _local_max_quality = gate_context.get(
                        "max_quality_retries", self._max_quality_retries
                    )
                    _quality_attempt = 0
                    while _quality_attempt < _local_max_quality:
                        _quality_attempt += 1
                        gate_context["_quality_retry_count"] = _quality_attempt
                        _remaining = _local_max_quality - _quality_attempt

                        # Apply the previous failing attempt's rewrite BEFORE
                        # the re-execution so the retry evaluates the improved
                        # text (G1/G2 emit modified_content only on failure).
                        self._apply_modified_content(
                            gate_name, gate_context, result, _rewrite_apply_state
                        )

                        log.info(
                            "gate.quality_retry",
                            gate_name=gate_name,
                            attempt=_quality_attempt,
                            max_quality_retries=_local_max_quality,
                            remaining=_remaining,
                            failure_reason=result.get("error", "quality check failed"),
                        )

                        if progress:
                            progress.on_gate_end(
                                gate_name,
                                False,
                                0.0,
                                attempt_number=_quality_attempt,
                                retry_level="quality",
                            )
                            progress.on_gate_start(
                                gate_name,
                                attempt_number=_quality_attempt + 1,
                                retry_level="quality",
                            )

                        start = time.monotonic()
                        try:
                            result = self._execute_gate_with_retry(
                                gate,
                                gate_context,
                                fm,
                                gate_name,
                                progress,
                            )
                            duration = time.monotonic() - start
                            result["duration_s"] = duration
                            result["quality_retry_count"] = _quality_attempt
                            results[-1] = result

                            if result.get("status") == "awaiting_hitl" and progress:
                                timeout_s = result.get("timeout_s", 86400)
                                progress.on_gate_awaiting_hitl(gate_name)
                                hitl_ok = progress.wait_for_hitl(
                                    project_dir="",
                                    timeout=timeout_s,
                                )
                                result["_hitl_approved"] = hitl_ok
                                if not hitl_ok:
                                    result["passed"] = False
                                    result["error"] = (
                                        result.get("error")
                                        or f"gate {gate_name} rejected by human review"
                                    )
                                    self._hitl_rejected_halt = True

                            passed = result.get("passed", True)
                            if progress:
                                progress.on_gate_end(
                                    gate_name,
                                    passed,
                                    duration,
                                    detail=result.get("error", ""),
                                    attempt_number=_quality_attempt,
                                    retry_level="quality",
                                )

                            if passed:
                                all_ok = True
                                log.info(
                                    "gate.passed",
                                    gate_name=gate_name,
                                    duration_s=duration,
                                )
                                self._dispatch_after(gate_name, gate_context, result)
                                break

                            log.warning(
                                "gate.quality_retry.attempt_failed",
                                gate_name=gate_name,
                                attempt=_quality_attempt,
                                remaining=_remaining,
                            )

                        except _PERMANENT_EXCEPTIONS as exc:
                            duration = time.monotonic() - start
                            all_ok = False
                            tb = traceback.format_exc()
                            log.error(
                                "gate.quality_retry.error.permanent",
                                gate_name=gate_name,
                                duration_s=duration,
                                error=str(exc),
                                attempt=_quality_attempt,
                                traceback=tb,
                            )
                            error_result = {
                                "passed": False,
                                "gate": gate_name,
                                "error": str(exc),
                                "duration_s": duration,
                                "quality_retry_count": _quality_attempt,
                            }
                            results[-1] = error_result
                            self._rollback_applied_content(
                                gate_context, _rewrite_apply_state, result
                            )
                            if progress:
                                progress.on_gate_end(
                                    gate_name,
                                    False,
                                    duration,
                                    detail=str(exc),
                                    attempt_number=_quality_attempt,
                                    retry_level="quality",
                                )
                            self._dispatch_failed(gate_name, gate_context, exc)
                            if early_stop:
                                return False, results
                            return results

                        except _TRANSIENT_EXCEPTIONS as exc:
                            duration = time.monotonic() - start
                            all_ok = False
                            tb = traceback.format_exc()
                            log.error(
                                "gate.quality_retry.error.transient",
                                gate_name=gate_name,
                                duration_s=duration,
                                error=str(exc),
                                attempt=_quality_attempt,
                                traceback=tb,
                            )
                            error_result = {
                                "passed": False,
                                "gate": gate_name,
                                "error": str(exc),
                                "duration_s": duration,
                                "retry_count": self._max_retries,
                                "retry_delay_s": self._retry_delay,
                                "quality_retry_count": _quality_attempt,
                            }
                            results[-1] = error_result
                            if progress:
                                progress.on_gate_end(
                                    gate_name,
                                    False,
                                    duration,
                                    detail=str(exc),
                                    attempt_number=_quality_attempt,
                                    retry_level="quality",
                                )
                            self._dispatch_failed(gate_name, gate_context, exc)
                            break

                        except Exception as exc:
                            # Unknown error during quality retry — log, record, and re-raise
                            duration = time.monotonic() - start
                            tb = traceback.format_exc()
                            log.error(
                                "gate.quality_retry.error.unknown",
                                gate_name=gate_name,
                                duration_s=duration,
                                error=str(exc),
                                attempt=_quality_attempt,
                                traceback=tb,
                            )
                            error_result = {
                                "passed": False,
                                "gate": gate_name,
                                "error": str(exc),
                                "duration_s": duration,
                                "quality_retry_count": _quality_attempt,
                            }
                            results[-1] = error_result
                            self._rollback_applied_content(
                                gate_context, _rewrite_apply_state, result
                            )
                            if progress:
                                progress.on_gate_end(
                                    gate_name,
                                    False,
                                    duration,
                                    detail=str(exc),
                                    attempt_number=_quality_attempt,
                                    retry_level="quality",
                                )
                            self._dispatch_failed(gate_name, gate_context, exc)
                            raise

                    if not passed:
                        all_ok = False
                        # Retries exhausted — undo any applied rewrite so the
                        # failed chain leaves no partial write behind.
                        self._rollback_applied_content(gate_context, _rewrite_apply_state, result)
                        if self._hitl_rejected_halt:
                            # A human rejection is terminal — it must not be
                            # consumed by level-2 regeneration retries.
                            if early_stop:
                                return False, results
                            return results
                        level2 = gate_context.get("_level2_handler")
                        if level2:
                            log.info(
                                "gate.quality_retry.level2",
                                gate_name=gate_name,
                                quality_retry_count=_quality_attempt,
                                handler=str(level2),
                            )
                            regen_ok, regen_results = level2(
                                gate_context=gate_context,
                                failed_gate_name=gate_name,
                                failure_result=result,
                                progress=progress,
                            )
                            if regen_results:
                                # Stitch regen results into full result list
                                cw_result_idx = None
                                for i_r, r in enumerate(results):
                                    if r.get("gate") == "CW":
                                        cw_result_idx = i_r
                                        break
                                if cw_result_idx is not None:
                                    results = results[:cw_result_idx] + regen_results
                                else:
                                    results = results + regen_results
                                all_ok = all(r.get("passed", True) for r in regen_results)
                                # When level 2 is exhausted, check if H0
                                # approved the escalation — if so, the
                                # pipeline is successful despite earlier
                                # gate failures.
                                if gate_context.get("_level2_exhausted"):
                                    h0_result = next(
                                        (r for r in regen_results if r.get("gate") == "H0"),
                                        None,
                                    )
                                    if h0_result and h0_result.get("passed"):
                                        all_ok = True
                                if early_stop:
                                    return all_ok, results
                                return results
                        else:
                            log.info(
                                "gate.quality_retry.exhausted",
                                gate_name=gate_name,
                                quality_retry_count=_quality_attempt,
                                max_quality_retries=_local_max_quality,
                            )
                        self._dispatch_after(gate_name, gate_context, result)

            except _PERMANENT_EXCEPTIONS as exc:
                duration = time.monotonic() - start
                all_ok = False
                tb = traceback.format_exc()
                log.error(
                    "gate.error.permanent",
                    gate_name=gate_name,
                    duration_s=duration,
                    error=str(exc),
                    failure_mode=fm,
                    traceback=tb,
                )
                error_result = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                    "duration_s": duration,
                }
                results.append(error_result)
                if progress:
                    progress.on_gate_end(gate_name, False, duration, detail=str(exc))
                self._dispatch_failed(gate_name, gate_context, exc)
                if early_stop:
                    return False, results
                return results

            except _TRANSIENT_EXCEPTIONS as exc:
                duration = time.monotonic() - start
                all_ok = False
                tb = traceback.format_exc()
                log.error(
                    "gate.error.transient",
                    gate_name=gate_name,
                    duration_s=duration,
                    error=str(exc),
                    failure_mode=fm,
                    traceback=tb,
                )
                error_result = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                    "duration_s": duration,
                }
                if fm == "retry":
                    error_result["retry_count"] = self._max_retries
                    error_result["retry_delay_s"] = self._retry_delay
                results.append(error_result)
                if progress:
                    progress.on_gate_end(gate_name, False, duration, detail=str(exc))
                self._dispatch_failed(gate_name, gate_context, exc)
                if fm == "stop":
                    if early_stop:
                        return False, results
                    return results
                # failure_mode == "retry" → transient error, exhausted retries, continue

            except Exception as exc:
                # Unknown error during gate execution — log, record, stop pipeline
                duration = time.monotonic() - start
                all_ok = False
                tb = traceback.format_exc()
                log.error(
                    "gate.error.unknown",
                    gate_name=gate_name,
                    duration_s=duration,
                    error=str(exc),
                    failure_mode=fm,
                    traceback=tb,
                )
                error_result = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                    "duration_s": duration,
                }
                results.append(error_result)
                if progress:
                    progress.on_gate_end(gate_name, False, duration, detail=str(exc))
                self._dispatch_failed(gate_name, gate_context, exc)
                if fm == "stop":
                    if early_stop:
                        return False, results
                    return results
                raise

            # NEW: Check retry flag after gate completes
            if progress:
                retry_target = progress.consume_retry_gate()
                if retry_target == gate_name:
                    log.info("gate_engine.retry", gate_name=gate_name)
                    continue  # _gate_loop_idx unchanged — re-runs same gate

            # NEW: Pause on approval — block until resume() is called
            if self._gate_requires_approval(gate_name, gate_context):
                _approval_evt = threading.Event()
                with self._approval_lock:
                    self._approval_events[gate_name] = _approval_evt
                if progress:
                    progress.on_gate_awaiting_hitl(gate_name, detail="awaiting_approval")
                log.info(
                    "gate_engine.pause_on_approval",
                    gate_name=gate_name,
                    message="Waiting for resume() — gate requires approval",
                )
                _approval_evt.wait()
                with self._approval_lock:
                    _approval = self._approval_results.pop(gate_name, {"approved": True})
                    self._approval_events.pop(gate_name, None)
                result["_approval"] = _approval
                log.info(
                    "gate_engine.resumed",
                    gate_name=gate_name,
                    approved=_approval.get("approved"),
                )

            _gate_loop_idx += 1

        if early_stop:
            return all_ok, results
        return results

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        gate_context: GateContext | dict[str, Any],
        *,
        progress: PipelineProgress | None = None,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Execute all gates sequentially.

        Parameters
        ----------
        gate_context:
            Pipeline context passed from gate to gate.
        progress:
            Optional progress tracker.  When provided, ``GateProgressEvent``
            entries are emitted for each gate (start / end) so that agents
            polling via ``get_pipeline_progress`` can observe execution.

        Returns
        -------
        tuple[bool, list[dict]]
            ``(success, results)`` where *success* is ``True`` when
            every gate passed (or no ``failure_mode="stop"`` gate failed),
            and *results* is the list of per-gate result dicts.
        """
        # Wire level 2 handler when regeneration is enabled
        _local_max_regen = gate_context.get(  # type: ignore[typeddict-unknown-key]  # max_regenerations not a known key in GateContext TypedDict
            "max_regenerations", self._max_regenerations
        )
        if _local_max_regen > 0 and "_level2_handler" not in gate_context:  # type: ignore[operator]  # _local_max_regen is Any from TypedDict.get(); "in" not valid on TypedDict
            gate_context["_level2_handler"] = self._handle_level2_regeneration  # type: ignore[arg-type]  # dynamic key not defined in GateContext TypedDict
        try:
            result = self._run(gate_context, early_stop=True, progress=progress)  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param
        finally:
            if progress:
                progress.mark_finished()
        return result  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param

    def run_with_results(
        self,
        gate_context: GateContext | dict[str, Any],
        *,
        progress: PipelineProgress | None = None,
    ) -> list[dict[str, Any]]:
        """Execute all gates and return per-gate result dicts.

        Unlike :meth:`run`, this always returns the full result list
        regardless of early-stop.
        """
        try:
            result = self._run(gate_context, early_stop=False, progress=progress)  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param
        finally:
            if progress:
                progress.mark_finished()
        return result  # type: ignore[return-value]  # _run() return is union; cannot narrow on early_stop param

    def run_sub_pipeline(
        self,
        gate_names: list[str],
        gate_context: GateContext | dict[str, Any],
        *,
        sub_pipeline_name: str | None = None,
        progress: PipelineProgress | None = None,
    ) -> dict[str, Any]:
        """Run a named sequence of gates as a sub-pipeline within a parent pipeline.

        Looks up each gate by name from the engine's gate list and executes them
        sequentially using :meth:`_execute_gate_with_retry`.  Progress is tracked
        in ``gate_context["sub_pipelines"][name]`` so the parent pipeline and
        hooks can observe sub-pipeline state.

        If a gate with ``failure_mode="stop"`` fails, the sub-pipeline halts
        immediately and returns ``passed=False``.  Gates with
        ``failure_mode="retry"`` are retried via the tenacity wrapper within the
        sub-pipeline context.  Exceptions during gate execution terminate the
        sub-pipeline.

        Parameters
        ----------
        gate_names:
            Ordered list of gate names to execute
            (e.g. ``["D1", "D2", "D3"]``).
        gate_context:
            Pipeline context shared with the parent pipeline.  Sub-pipeline
            state is stored in ``gate_context["sub_pipelines"][name]``.
        sub_pipeline_name:
            Optional identifier for this sub-pipeline.  Defaults to the first
            gate name when not provided.
        progress:
            Optional progress tracker forwarded to individual gate execution.

        Returns
        -------
        dict
            ``{"passed": bool, "gate_results": list[dict], "failed_gate": str | None}``
            where *passed* is ``True`` when every gate completed successfully,
            *gate_results* is a list of per-gate result dicts, and *failed_gate*
            is the name of the first failing gate (or ``None`` when all passed).

        Raises
        ------
        ValueError
            If any gate name in *gate_names* is not found in the engine's
            gate list.
        """
        sp_name = sub_pipeline_name or (gate_names[0] if gate_names else "__unnamed__")

        # Initialize sub-pipeline tracking in context.extra
        sub_pipelines: dict[str, Any] = gate_context.setdefault("sub_pipelines", {})  # type: ignore[typeddict-unknown-key]
        sp_state: dict[str, Any] = sub_pipelines.setdefault(sp_name, {})
        sp_state.update(
            {
                "status": "running",
                "gates_completed": [],
                "current_gate": None,
                "gate_names": list(gate_names),
            }
        )

        # Build name → gate lookup from the engine's gate list
        gate_map: dict[str, BaseGate] = {g.gate_name: g for g in self._gates}
        missing = [n for n in gate_names if n not in gate_map]
        if missing:
            raise ValueError(
                f"Gates not found in engine gate list: {missing}. Available: {list(gate_map)}"
            )

        gate_results: list[dict[str, Any]] = []
        failed_gate: str | None = None

        for gate_name in gate_names:
            gate = gate_map[gate_name]
            sp_state["current_gate"] = gate_name

            # Resolve failure mode (backward compat: "rewrite" → "retry")
            fm = gate.failure_mode
            if fm == "rewrite":
                warnings.warn(
                    f"failure_mode='rewrite' is deprecated for gate '{gate_name}', "
                    f"use failure_mode='retry' instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                fm = "retry"

            log.info(
                "sub_pipeline.gate.start",
                gate_name=gate_name,
                sub_pipeline=sp_name,
                failure_mode=fm,
            )

            start = time.monotonic()
            try:
                result = self._execute_gate_with_retry(
                    gate,
                    gate_context,
                    fm,
                    gate_name,
                    progress,
                )
                duration = time.monotonic() - start
                result["duration_s"] = duration
                gate_results.append(result)

                passed = result.get("passed", True)
                if passed:
                    sp_state["gates_completed"].append(gate_name)
                    log.info(
                        "sub_pipeline.gate.passed",
                        gate_name=gate_name,
                        sub_pipeline=sp_name,
                        duration_s=duration,
                    )
                else:
                    log.warning(
                        "sub_pipeline.gate.failed",
                        gate_name=gate_name,
                        sub_pipeline=sp_name,
                        failure_mode=fm,
                        error=result.get("error", ""),
                        duration_s=duration,
                    )
                    if fm == "stop":
                        failed_gate = gate_name
                        sp_state["status"] = "failed"
                        sp_state["failed_gate"] = gate_name
                        return {
                            "passed": False,
                            "gate_results": gate_results,
                            "failed_gate": failed_gate,
                        }
                    # failure_mode == "retry": tenacity retry already handled
                    # inside _execute_gate_with_retry; continue to next gate.

            except _PERMANENT_EXCEPTIONS as exc:
                duration = time.monotonic() - start
                failed_gate = gate_name
                tb = traceback.format_exc()
                log.error(
                    "sub_pipeline.gate.error.permanent",
                    gate_name=gate_name,
                    sub_pipeline=sp_name,
                    duration_s=duration,
                    error=str(exc),
                    traceback=tb,
                )
                error_result = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                    "duration_s": duration,
                }
                gate_results.append(error_result)
                sp_state["status"] = "failed"
                sp_state["failed_gate"] = gate_name
                return {
                    "passed": False,
                    "gate_results": gate_results,
                    "failed_gate": failed_gate,
                }

            except _TRANSIENT_EXCEPTIONS as exc:
                duration = time.monotonic() - start
                failed_gate = gate_name
                log.error(
                    "sub_pipeline.gate.error.transient",
                    gate_name=gate_name,
                    sub_pipeline=sp_name,
                    duration_s=duration,
                    error=str(exc),
                    failure_mode=fm,
                )
                error_result = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                    "duration_s": duration,
                    "retry_count": self._max_retries,
                    "retry_delay_s": self._retry_delay,
                }
                gate_results.append(error_result)
                # Transient with fm="retry": budget exhausted, continue to
                # next gate (matching _run() behaviour for transient errors).
                if fm == "stop":
                    sp_state["status"] = "failed"
                    sp_state["failed_gate"] = gate_name
                    return {
                        "passed": False,
                        "gate_results": gate_results,
                        "failed_gate": failed_gate,
                    }

            except Exception as exc:
                duration = time.monotonic() - start
                failed_gate = gate_name
                tb = traceback.format_exc()
                log.error(
                    "sub_pipeline.gate.error.unknown",
                    gate_name=gate_name,
                    sub_pipeline=sp_name,
                    duration_s=duration,
                    error=str(exc),
                    traceback=tb,
                )
                error_result = {
                    "passed": False,
                    "gate": gate_name,
                    "error": str(exc),
                    "duration_s": duration,
                }
                gate_results.append(error_result)
                sp_state["status"] = "failed"
                sp_state["failed_gate"] = gate_name
                return {
                    "passed": False,
                    "gate_results": gate_results,
                    "failed_gate": failed_gate,
                }

        sp_state["status"] = "completed"
        sp_state.pop("current_gate", None)
        return {
            "passed": True,
            "gate_results": gate_results,
            "failed_gate": None,
        }

    # ------------------------------------------------------------------
    # Approval pause / resume (director mode)
    # ------------------------------------------------------------------

    def resume(
        self,
        gate_name: str,
        approved: bool = True,
        modifications: dict[str, Any] | None = None,
    ) -> None:
        """Resume a gate paused for approval.

        Unblocks the execution loop when ``pause_on_approval`` is enabled
        and a gate with ``requires_approval`` in its context is waiting.

        Args:
            gate_name: Name of the gate to resume.
            approved: Whether the gate output is approved.
            modifications: Optional modifications to apply to the gate
                result before continuing.

        Raises:
            KeyError: If no gate named *gate_name* is currently awaiting
                approval.
        """
        with self._approval_lock:
            evt = self._approval_events.get(gate_name)
            if evt is None:
                raise KeyError(
                    f"No gate awaiting approval: {gate_name!r}. "
                    f"Active waiters: {set(self._approval_events.keys())}"
                )
            self._approval_results[gate_name] = {
                "approved": approved,
                "modifications": modifications or {},
            }
            evt.set()
        log.info(
            "gate_engine.resume.called",
            gate_name=gate_name,
            approved=approved,
        )

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        """Return metadata for every gate currently awaiting approval.

        Returns
        -------
        list[dict]
            Each entry has ``gate_name`` and ``status`` keys.
            Empty list when no gates are paused for approval.
        """
        with self._approval_lock:
            return [
                {"gate_name": gate_name, "status": "awaiting_approval"}
                for gate_name in self._approval_events
            ]


# Keep a backward-compatible alias so existing ``from ... import Pipeline``
# in __init__.py continues to work.
Pipeline = GateEngine
