"""Pipeline runner — high-level entry point for the full AutoMedia pipeline.

Orchestrates configuration loading, project creation, gate construction,
execution, and MD5 recording.
"""

from __future__ import annotations

import os
import time
import warnings
from dataclasses import asdict
from typing import Any, Literal, cast

from structlog import get_logger

from automedia.core.config_loader import load_config
from automedia.core.project import Project
from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate, GateRegistry, _registry
from automedia.hooks.md5_tracker import get_pipeline_md5, record_md5, verify_md5
from automedia.hooks.protocol import GateHook
from automedia.manifests.brand_profile_schema import BrandProfile, load_brand_profile
from automedia.pipelines.gate_engine import (
    AssetInfo,
    GateEngine,
    GateLogEntry,
    PipelineProgress,
    PipelineResult,
)
from automedia.pipelines.language_config import resolve_language_config

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Gate name lists per mode
# ---------------------------------------------------------------------------

_AUTO_GATE_NAMES: list[str] = [
    "pre-gate",
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "V0",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "V7",
    "L1",
    "L2",
    "L3",
    "L4",
]

_TEXT_ONLY_GATE_NAMES: list[str] = [
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "L1",
    "L2",
    "L3",
    "L4",
]

_VIDEO_ONLY_GATE_NAMES: list[str] = [
    "V0",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "V7",
    "L1",
    "L2",
    "L3",
    "L4",
]

_QA_ONLY_GATE_NAMES: list[str] = [
    "G0",
    "G2",
    "G3",
    "V1",
    "V6",
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


def _collect_assets(gate_context: GateContext | dict[str, Any]) -> list[AssetInfo]:
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


def _verify_resume_integrity(
    project_dir: str,
    resume_from: str,
    gate_names_in_mode: list[str],
) -> None:
    """Verify MD5 of all gate outputs before *resume_from*.

    Reads the pipeline_md5.json and checks every gate recorded before
    the resume point.  Mismatches are logged as warnings — the pipeline
    will regenerate those outputs anyway.
    """
    try:
        resume_idx = gate_names_in_mode.index(resume_from)
    except ValueError:
        return

    prior_gates = gate_names_in_mode[:resume_idx]
    if not prior_gates:
        return

    data = get_pipeline_md5(project_dir)
    gates_record = data.get("gates", {})

    for gate_name in prior_gates:
        record = gates_record.get(gate_name)
        if record is None:
            continue

        file_path = record.get("file_path", "")
        if not file_path:
            continue

        try:
            md5_ok = verify_md5(project_dir, gate_name, file_path)
        except (OSError, FileNotFoundError):
            md5_ok = False

        if not md5_ok:
            log.warning(
                "pipeline.resume.md5_mismatch",
                gate_name=gate_name,
                file_path=file_path,
                hint="The file has been modified or is missing since the original pipeline run. "
                     "The resumed pipeline will regenerate this output.",
            )


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
            except (OSError, FileNotFoundError) as exc:
                log.warning(
                    "pipeline.md5_record_failed",
                    gate_name=gate_name,
                    output_path=output_path,
                    error=str(exc),
                )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_full_pipeline(
    topic: str,
    brand: str,
    *,
    hooks: list[GateHook] | None = None,
    mode: str = "auto",
    decision_mode: str = "build",
    resume_from: str | None = None,
    config_dir: str | None = None,
    tenant_id: str = "default",
    default_lang: str | None = None,
    force_provenance: bool = False,
    progress: PipelineProgress | None = None,
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
    decision_mode:
        **DEPRECATED** — kept for backward compatibility only.
        No longer consumed by any gate and will be removed in a
        future version.
    resume_from:
        Gate name to resume from (skip preceding gates).  ``None`` runs
        from the beginning.
    config_dir:
        Explicit path to the project-level ``.automedia/`` config
        directory.
    tenant_id:
        Tenant / namespace identifier.
    default_lang:
        Default language for the pipeline (e.g. ``"zh"``, ``"en"``).
        ``None`` resolves to ``"zh"``.  The value is injected into
        ``gate_context["lang_config"]`` for downstream gates.
    force_provenance:
        Deprecated.  Kept for backward compatibility — no longer used.
    progress:
        Optional progress tracker.  When provided, ``GateEngine.run()``
        emits ``GateProgressEvent`` entries for each gate so agents
        polling via MCP can observe execution in real time.

    Returns
    -------
    PipelineResult
        Structured result with status, logs, and asset metadata.
        On unexpected errors the result has ``status="failed"`` and
        ``error`` is populated instead of raising.
    """
    start = time.monotonic()

    if decision_mode is not None and decision_mode != "build":
        warnings.warn(
            "decision_mode is deprecated and will be removed in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        log.warning("decision_mode parameter is deprecated, ignoring value: %s", decision_mode)

    log.info("pipeline.start", topic=topic, brand=brand, mode=mode, tenant_id=tenant_id)

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
            raise ValueError(f"Unknown pipeline mode {mode!r}. Choose from: {list(_MODE_MAP)}")

        # Apply resume_from — find index and slice
        if resume_from is not None:
            try:
                idx = gate_names.index(resume_from)
                gate_names = gate_names[idx:]
            except ValueError:
                raise ValueError(
                    f"resume_from gate {resume_from!r} not found in mode {mode!r} gate list"
                ) from None

        # 3.5 Verify previous gate outputs when resuming
        if resume_from is not None:
            _verify_resume_integrity(project.project_dir, resume_from, _MODE_MAP.get(mode, []))

        gates = _build_gates_from_names(gate_names)
        log.info("pipeline.gates_constructed", gate_count=len(gates), gate_names=gate_names)

        # 4. Instantiate engine
        engine = GateEngine(gates, hooks=hooks)

        # 4.5 Resolve language configuration
        brand_profile: BrandProfile | None = None
        brand_profile_path = os.path.join(project.project_dir, "brand-profile.yaml")
        try:
            brand_profile = load_brand_profile(brand_profile_path)
        except (FileNotFoundError, ValueError):
            brand_profile = None

        lang_config = resolve_language_config(
            brand_profile=brand_profile,
            default_lang=default_lang,
        )

        # 5. Build initial context
        gate_context = GateContext(
            topic=topic,
            brand=brand,
            project_id=project.project_id,
            project_dir=project.project_dir,
            config=config,
            tenant_id=tenant_id,
            lang_config=lang_config,
            mode=config.get("mode", "auto"),
            force_provenance=force_provenance,
            brand_profile=asdict(brand_profile) if brand_profile is not None else None,
        )

        # 5.5 Content fallback guard (Issue #14)
        #      When CW is not in the gate list (video_only / qa_only modes),
        #      content stays empty.  Inject a placeholder so downstream gates
        #      and pipeline consumers don't see blank content.
        if "CW" not in gate_names and not gate_context.get("content", "").strip():
            placeholder = f"[content skipped in {mode} mode]"
            gate_context["content"] = placeholder
            gate_context["draft"] = placeholder
            log.info("pipeline.content_placeholder", mode=mode, placeholder=placeholder)

        # 6. Execute
        success, results = engine.run(gate_context, progress=progress)

        # 7. Collect assets
        assets = _collect_assets(gate_context)

        # 8. Record MD5s
        _record_gate_md5s(project.project_dir, results)

        # 9. Build gate log
        gates_log = _build_gates_log(results)

        end = time.monotonic()

        status = "success" if success else "partial"
        log.info(
            "pipeline.complete",
            status=status, duration_s=end - start,
            project_id=project.project_id,
        )

        return PipelineResult(
            status=cast(Literal["success", "failed", "partial"], status),
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
        log.error(
            "pipeline.failed",
            error=str(exc), duration_s=end - start,
            topic=topic, brand=brand,
        )
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
