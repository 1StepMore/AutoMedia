"""Deterministic in-process fixture seam for control/approval MCP tools (T-05).

The seven control/approval MCP tools (``pause_pipeline``, ``resume_pipeline``,
``cancel_pipeline``, ``retry_gate``, ``skip_gate``, ``approve_gate``,
``reject_gate``) act on runtime state that ``run_pipeline`` creates under a
``uuid4`` project id.  A static YAML scenario has no output interpolation
(``automedia.validation.engine`` dispatches fixed ``arguments``), so it can
never address the live run's id — the honest contract is the ``NOT_FOUND``
boundary probe.  To prove each surface's success branch deterministically, a
scenario may declare a ``fixtures:`` entry; the engine then seeds the SAME
in-process state ``run_pipeline``/``run_full_pipeline`` create — a
``PipelineProgress`` in the tracker and a paused engine in the engine
registry — under the fixed ids below, and calls the REAL tool through the
REAL MCP dispatcher.  The fixture provides state only; the tool's own lookup,
mutation, and success envelope are the evidence.

This is a harness seam, not a product behaviour: no fixture code ships in the
MCP tools, and a scenario that does not declare a fixture never sees this
state (so the boundary probes and ``get_pending_approvals`` stay untouched).

Lifecycle: :func:`apply_fixtures` is a context manager — the engine enters it
around the primary steps and it always tears the seeded state back out, so
one scenario's fixture can never leak into the next.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from automedia.validation.schema import FIXTURES as FIXTURE_NAMES

PIPELINE_CONTROL_ID: str = "valctrlpipeline1"
"""Fixed tracker id seeded by the ``pipeline_control`` fixture."""

PAUSED_ENGINE_ID: str = "valctrlengine1"
"""Fixed engine-registry id seeded by the ``paused_engine`` fixture."""

APPROVAL_GATE_NAME: str = "H0"
"""Gate name the ``paused_engine`` fixture leaves awaiting approval."""

HITL_PIPELINE_ID: str = "valctrlhitl01"
"""Fixed project id of the live H0 pipeline seeded by ``hitl_pause``."""

HITL_MARKER_ENV_VAR: str = "AUTOMEDIA_HITL_MARKER_PATH"
"""Env var that redirects the live-HITL run-completion marker (issue #17).

The ``hitl_pause`` fixture exports a UNIQUE per-run marker path through this
var for the lifetime of the fixture, so a marker written by another run,
session, or parallel pytest worker can never be read by this run's assertion.
Every reader must resolve through :func:`resolve_hitl_marker_path`, never the
module constant directly.
"""

HITL_MARKER_PATH: str = "/tmp/automedia/hitl-live/decision.json"  # noqa: S108  # nosec B108 — synthetic isolated scratch
"""Default live-HITL marker path, used when :data:`HITL_MARKER_ENV_VAR` is unset."""

HITL_MARKER_ROOT: str = "/tmp/automedia/hitl-live"  # noqa: S108  # nosec B108 — synthetic isolated scratch
"""Parent directory for the fixture's per-run marker dirs."""


def resolve_hitl_marker_path() -> Path:
    """Resolve the live-HITL marker path: env override, else the default.

    The env var wins when set (the ``hitl_pause`` fixture sets it to a unique
    per-run path); otherwise the committed :data:`HITL_MARKER_PATH` is the
    documented fallback.  Readers must use this helper so the fixture and its
    assertions can never disagree about where the marker lives.
    """
    override = os.environ.get(HITL_MARKER_ENV_VAR)
    return Path(override) if override else Path(HITL_MARKER_PATH)


class PausedEngineFixture:
    """A minimal paused-engine double exposing the GateEngine surface the
    director-mode approval tools consume (``resume`` +
    ``list_pending_approvals``).

    Using a fixture double rather than a concrete :class:`~automedia.gates.base
    .BaseGate` subclass is deliberate: a production-module gate subclass would
    auto-register in the global ``GateRegistry`` and break the RL7 feature-tier
    parity assertions (``tests/test_features.py``).  The tools under test only
    call the two methods below, so the double is the narrowest faithful seam.
    """

    def __init__(self, gate_name: str) -> None:
        self._gate_name = gate_name
        self._pending = True
        self._lock = threading.Lock()
        self.last_decision: dict[str, Any] | None = None

    def resume(
        self,
        gate_name: str,
        approved: bool = True,
        modifications: dict[str, Any] | None = None,
    ) -> None:
        """Unblock the paused gate; raise ``KeyError`` for the wrong gate."""
        with self._lock:
            if not self._pending or gate_name != self._gate_name:
                raise KeyError(
                    f"No gate awaiting approval: {gate_name!r}. "
                    f"Active waiters: {{{self._gate_name!r}}}"
                )
            self._pending = False
            self.last_decision = {"approved": approved, "modifications": modifications or {}}

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        """Pending gates, mirroring ``GateEngine.list_pending_approvals``."""
        with self._lock:
            if not self._pending:
                return []
            return [{"gate_name": self._gate_name, "status": "awaiting_approval"}]


def _seed_pipeline_control() -> dict[str, Any]:
    """Seed a real ``PipelineProgress`` under the fixed control id."""
    from automedia.mcp._state import _lock, _pipeline_tracker
    from automedia.pipelines.gate_types import PipelineProgress

    progress = PipelineProgress(project_id=PIPELINE_CONTROL_ID)
    progress.set_gate_names(["G0", "G1", "V0"])
    # Record G0 as completed so a pause/resume scenario can prove the
    # runtime gate checkpoint survives the cycle (no restart): ``gates_done``
    # must still hold G0 after resume.
    progress.on_gate_start("G0")
    progress.on_gate_end("G0", True, 0.0)
    with _lock:
        _pipeline_tracker[PIPELINE_CONTROL_ID] = progress
    return {"id": PIPELINE_CONTROL_ID, "progress": progress}


def _seed_paused_engine() -> dict[str, Any]:
    """Register a paused-engine fixture under the fixed engine id."""
    from automedia.pipelines.gate_engine import register_engine

    engine = PausedEngineFixture(APPROVAL_GATE_NAME)
    register_engine(PAUSED_ENGINE_ID, engine)  # type: ignore[arg-type]  # fixture double
    return {"id": PAUSED_ENGINE_ID, "engine": engine}


class LiveHITLFixture:
    """A REAL H0-paused :class:`GateEngine` running in a daemon thread.

    ``review_decision`` (gap R-03) resolves live HITL waiters through the
    in-process ``_hitl_waiters`` registry, so this harness starts the SAME
    pause path a ``run_pipeline`` daemon thread uses and lets the real tool
    approve or reject it.  The engine is registered under the fixed id too,
    so a pending-approvals scenario can observe the paused gate.  The
    harness writes a run-completion marker the scenarios assert on:
    ``ok`` (engine outcome) and ``approved`` (the human decision).
    """

    def __init__(self, project_id: str = HITL_PIPELINE_ID) -> None:
        from automedia.gates.h0_human_review import H0HumanReviewGate
        from automedia.pipelines.gate_engine import GateEngine, register_engine
        from automedia.pipelines.gate_types import PipelineProgress

        self.project_id = project_id
        # Unique per-run marker dir (issue #17): a fixed global path let one
        # run's marker satisfy the next run's assertion.  The env var carries
        # this path to the CLI step's subprocess; teardown restores/deletes it.
        self._marker = Path(HITL_MARKER_ROOT) / uuid.uuid4().hex / "decision.json"
        self._marker.parent.mkdir(parents=True, exist_ok=True)
        self._previous_marker_env: str | None = os.environ.get(HITL_MARKER_ENV_VAR)
        os.environ[HITL_MARKER_ENV_VAR] = str(self._marker)
        self.engine = GateEngine([H0HumanReviewGate()])
        self.progress = PipelineProgress(project_id=project_id)
        self._state: dict[str, Any] = {"done": False, "ok": None, "approved": None}
        register_engine(project_id, self.engine)
        self._thread = threading.Thread(target=self._run, daemon=True, name="validation-live-hitl")
        self._thread.start()
        self._wait_until_paused()

    def _run(self) -> None:
        try:
            outcome = self.engine.run(
                {"topic": "validation-live-hitl", "skip_review": False},
                progress=self.progress,
            )
        except Exception as exc:
            self._state.update(done=True, error=repr(exc))
        else:
            ok, results = outcome if isinstance(outcome, tuple) else (None, [])
            approved = results[0].get("_hitl_approved") if results else None
            self._state.update(done=True, ok=ok, approved=approved)
        _write_marker_atomic(
            self._marker,
            {
                "ok": self._state.get("ok"),
                "approved": self._state.get("approved"),
                "error": self._state.get("error"),
            },
        )

    def _wait_until_paused(self, timeout: float = 10.0) -> None:
        from automedia.pipelines.gate_types import _hitl_lock, _hitl_waiters

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with _hitl_lock:
                if _hitl_waiters.get(self.project_id) is not None:
                    return
            if self._state["done"]:
                raise RuntimeError("live HITL pipeline finished without pausing at H0")
            time.sleep(0.05)
        raise TimeoutError("live HITL pipeline never paused at H0")

    def teardown(self) -> None:
        from automedia.pipelines.gate_engine import unregister_engine
        from automedia.pipelines.gate_types import _hitl_lock, _hitl_waiters

        with _hitl_lock:
            pending = _hitl_waiters.get(self.project_id) is not None
        if pending and not self._state["done"]:
            with suppress(Exception):
                self.progress.reject_hitl()
        self._thread.join(timeout=10)
        with _hitl_lock:
            _hitl_waiters.pop(self.project_id, None)
        unregister_engine(self.project_id)
        if self._previous_marker_env is None:
            os.environ.pop(HITL_MARKER_ENV_VAR, None)
        else:
            os.environ[HITL_MARKER_ENV_VAR] = self._previous_marker_env
        with suppress(OSError):
            shutil.rmtree(self._marker.parent)


def _write_marker_atomic(marker: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``marker`` atomically.

    ``Path.write_text`` truncates the destination before writing, so a
    concurrent reader can observe an empty file.  Write to a temp file in the
    same directory, flush + fsync it, then ``os.replace`` it onto the final
    path: the reader sees either the old file or the complete new one, never
    a truncated one.
    """
    data = json.dumps(payload)
    fd, tmp_name = tempfile.mkstemp(dir=str(marker.parent), prefix=marker.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, marker)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def _seed_hitl_pause() -> dict[str, Any]:
    """Seed the live H0-paused pipeline harness under the fixed id."""
    return {"kind": "hitl", "harness": LiveHITLFixture()}


_SEEDERS = {
    "pipeline_control": _seed_pipeline_control,
    "paused_engine": _seed_paused_engine,
    "hitl_pause": _seed_hitl_pause,
}


def _teardown(seeded: Sequence[dict[str, Any]]) -> None:
    """Remove every seeded fixture (tracker entries + engine registrations)."""
    from automedia.mcp._state import _lock, _pipeline_tracker
    from automedia.pipelines.gate_engine import unregister_engine

    for entry in seeded:
        if entry.get("kind") == "hitl":
            entry["harness"].teardown()
            continue
        if "progress" in entry:
            with _lock:
                _pipeline_tracker.pop(entry["id"], None)
        if "engine" in entry:
            unregister_engine(entry["id"])


@contextmanager
def apply_fixtures(names: Sequence[str]) -> Iterator[None]:
    """Seed the declared fixtures, yield, then always tear them down.

    Unknown names raise ``ValueError`` loudly (the schema already rejects
    them; this is the engine-side belt-and-braces).
    """
    seeded: list[dict[str, Any]] = []
    try:
        for name in names:
            seeder = _SEEDERS.get(name)
            if seeder is None:
                raise ValueError(f"unknown validation fixture {name!r}; known: {FIXTURE_NAMES}")
            seeded.append(seeder())
        yield
    finally:
        _teardown(seeded)
