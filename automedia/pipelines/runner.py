"""Pipeline runner — high-level entry point for the full AutoMedia pipeline.

Orchestrates configuration loading, project creation, gate construction,
execution, and MD5 recording.
"""

from __future__ import annotations

import time
from typing import Any

from automedia.core.config_loader import load_config
from automedia.core.project import Project
from automedia.gates.base import BaseGate, GateRegistry, _registry
from automedia.hooks.md5_tracker import record_md5
from automedia.hooks.protocol import GateHook
from automedia.pipelines.gate_engine import (
    AssetInfo,
    GateEngine,
    GateLogEntry,
    PipelineResult,
)


# ---------------------------------------------------------------------------
# Gate name lists per mode
# ---------------------------------------------------------------------------

_AUTO_GATE_NAMES: list[str] = [
    "pre-gate",
    "CW",
    "G0", "G1", "G2", "G3", "G4", "G5",
    "V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7",
    "L1", "L2", "L3",
]

_TEXT_ONLY_GATE_NAMES: list[str] = [
    "CW",
    "G0", "G1", "G2", "G3", "G4", "G5",
    "L1", "L2", "L3",
]

_VIDEO_ONLY_GATE_NAMES: list[str] = [
    "V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7",
    "L1", "L2", "L3",
]

_QA_ONLY_GATE_NAMES: list[str] = [
    "G0", "G2", "G3", "V1", "V6",
]

_MODE_MAP: dict[str, list[str]] = {
    "auto": _AUTO_GATE_NAMES,
    "text_only": _TEXT_ONLY_GATE_NAMES,
    "video_only": _VIDEO_ONLY_GATE_NAMES,
    "qa_only": _QA_ONLY_GATE_NAMES,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_assets(gate_context: dict[str, Any]) -> list[AssetInfo]:
    """Extract ``AssetInfo`` items from the gate context after execution."""
    assets: list[AssetInfo] = []
    for key in ("output_files", "assets"):
        items = gate_context.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    assets.append(
                        AssetInfo(
                            type=item.get("type", ""),
                            path=item.get("path", ""),
                            platform=item.get("platform", ""),
                            md5=item.get("md5", ""),
                        )
                    )
                elif isinstance(item, AssetInfo):
                    assets.append(item)
    return assets


def _record_gate_md5s(
    project_dir: str,
    gate_results: list[dict[str, Any]],
) -> None:
    """Record MD5 for each gate result that includes ``output_path``."""
    for result in gate_results:
        output_path = result.get("output_path")
        gate_name = result.get("gate", "")
        if output_path and gate_name:
            try:
                record_md5(project_dir, gate_name, output_path)
            except (OSError, FileNotFoundError):
                # Non-fatal: asset may not exist on disk yet
                pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_full_pipeline(
    topic: str,
    brand: str,
    *,
    hooks: list[GateHook] | None = None,
    mode: str = "auto",
    resume_from: str | None = None,
    config_dir: str | None = None,
    tenant_id: str = "default",
) -> PipelineResult:
    """Execute the full AutoMedia production pipeline.

    Parameters
    ----------
    topic:
        Content topic / subject.
    brand:
        Brand identifier.
    hooks:
        Optional lifecycle hooks.
    mode:
        Pipeline execution mode — ``"auto"``, ``"text_only"``,
        ``"video_only"``, or ``"qa_only"``.
    resume_from:
        Gate name to resume from (skip preceding gates).  ``None`` runs
        from the beginning.
    config_dir:
        Explicit path to the project-level ``.automedia/`` config
        directory.
    tenant_id:
        Tenant / namespace identifier.

    Returns
    -------
    PipelineResult
        Structured result with status, logs, and asset metadata.
        On unexpected errors the result has ``status="failed"`` and
        ``error`` is populated instead of raising.
    """
    start = time.monotonic()

    try:
        # 1. Load configuration
        config = load_config(config_dir=config_dir)

        # 2. Create project
        project = Project.init(topic, brand, tenant_id=tenant_id)

        # 3. Build gate list
        #    Ensure gates module is imported so all gates are registered
        import automedia.gates  # noqa: F401

        gate_names = _MODE_MAP.get(mode)
        if gate_names is None:
            raise ValueError(
                f"Unknown pipeline mode {mode!r}. "
                f"Choose from: {list(_MODE_MAP)}"
            )

        # Apply resume_from — find index and slice
        if resume_from is not None:
            try:
                idx = gate_names.index(resume_from)
                gate_names = gate_names[idx:]
            except ValueError:
                raise ValueError(
                    f"resume_from gate {resume_from!r} not found in "
                    f"mode {mode!r} gate list"
                )

        gates = _build_gates_from_names(gate_names)

        # 4. Instantiate engine
        engine = GateEngine(gates, hooks=hooks)

        # 5. Build initial context
        gate_context: dict[str, Any] = {
            "topic": topic,
            "brand": brand,
            "project_id": project.project_id,
            "project_dir": project.project_dir,
            "config": config,
            "tenant_id": tenant_id,
        }

        # 6. Execute
        success, results = engine.run(gate_context)

        # 7. Collect assets
        assets = _collect_assets(gate_context)

        # 8. Record MD5s
        _record_gate_md5s(project.project_dir, results)

        # 9. Build gate log
        gates_log = _build_gates_log(results)

        end = time.monotonic()

        status: str = "success" if success else "partial"

        return PipelineResult(
            status=status,
            project_id=project.project_id,
            project_dir=project.project_dir,
            topic=topic,
            brand=brand,
            assets=assets,
            gates_log=gates_log,
            start_time=start,
            end_time=end,
            total_duration_s=end - start,
        )

    except Exception as exc:
        end = time.monotonic()
        return PipelineResult(
            status="failed",
            topic=topic,
            brand=brand,
            start_time=start,
            end_time=end,
            total_duration_s=end - start,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Internal helpers used by run_full_pipeline
# ---------------------------------------------------------------------------


def _build_gates_from_names(
    names: list[str],
    registry: GateRegistry | None = None,
) -> list[BaseGate]:
    """Instantiate gates by name from the registry."""
    reg = registry if registry is not None else _registry
    return [reg.get(n)() for n in names]


def _build_gates_log(results: list[dict[str, Any]]) -> list[GateLogEntry]:
    """Convert raw gate result dicts into :class:`GateLogEntry` items."""
    entries: list[GateLogEntry] = []
    for r in results:
        passed = r.get("passed", True)
        entries.append(
            GateLogEntry(
                gate_name=r.get("gate", "unknown"),
                status="passed" if passed else "failed",
                duration_s=r.get("duration_s", 0.0),
                error=r.get("error"),
            )
        )
    return entries
