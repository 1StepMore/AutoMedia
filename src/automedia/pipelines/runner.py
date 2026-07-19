"""Pipeline runner — high-level entry point for the full AutoMedia pipeline.

Orchestrates configuration loading, project creation, gate construction,
execution, and MD5 recording.
"""

from __future__ import annotations

import os
import shutil
import time
import warnings
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

from structlog import get_logger

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
    "H0",
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
    "H0",
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

_IMAGE_CAROUSEL_GATE_NAMES: list[str] = [
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

_TEXT_WITH_COVER_GATE_NAMES: list[str] = [
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "H0",
    "L1",
    "L2",
    "L3",
    "L4",
]

_SOCIAL_THREAD_GATE_NAMES: list[str] = [
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

_SHORT_VIDEO_GATE_NAMES: list[str] = [
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
    "H0",
    "L1",
    "L2",
    "L3",
    "L4",
]

_MODE_MAP: dict[str, list[str]] = {
    "auto": _AUTO_GATE_NAMES,
    "text_only": _TEXT_ONLY_GATE_NAMES,
    "text_with_cover": _TEXT_WITH_COVER_GATE_NAMES,
    "video_only": _VIDEO_ONLY_GATE_NAMES,
    "qa_only": _QA_ONLY_GATE_NAMES,
    "image-carousel": _IMAGE_CAROUSEL_GATE_NAMES,
    "social-thread": _SOCIAL_THREAD_GATE_NAMES,
    "short-video": _SHORT_VIDEO_GATE_NAMES,
}

# Lifecycle gates — these are required and cannot be excluded via modifiers
_LIFECYCLE_GATE_NAMES: list[str] = ["L1", "L2", "L3", "L4"]

# Valid modes tuple — shared reference for CLI/MCP/SDK validation
VALID_MODES: tuple[str, ...] = tuple(_MODE_MAP)

# Platform → content-category mapping for auto-deriving pipeline mode.
# Used by _derive_mode_from_platforms() when mode is not explicitly set.
_PLATFORM_CATEGORIES: dict[str, str] = {
    "wechat": "text-first",
    "zhihu": "text-first",
    "xiaohongshu": "mixed-social",
    "feishu": "notification-only",
    "youtube": "video-first",
    "twitter": "text-first",
    "bilibili": "video-first",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _derive_mode_from_platforms(platforms: list[str]) -> str:
    """Derive pipeline mode from a brand's platform list.

    Returns ``"auto"`` when any platform is ``"mixed-social"``,
    ``"text_only"`` when all platforms are ``"text-first"`` or
    ``"notification-only"``, or ``""`` when *platforms* is empty.
    ``"text_with_cover"`` must be set explicitly (not auto-derived).

    Unknown platform names are treated as ``"text-first"``.
    """
    if not platforms:
        return ""

    has_multimedia = any(
        _PLATFORM_CATEGORIES.get(p, "text-first") in ("mixed-social", "video-first")
        for p in platforms
    )

    return "auto" if has_multimedia else "text_only"


def _check_hyperframes(mode: str) -> bool:
    """Check if the HyperFrames CLI tool is available on the system.

    HyperFrames is an external CLI tool for video rendering. This check
    looks for the ``hyperframes`` command in ``PATH``.

    Unlike the pre-flight check pattern, this function **never raises**:
    it returns a boolean flag that video gates (V0-V7) consume to decide
    whether to skip or degrade gracefully.  This separation ensures that
    pipeline tests mocking the GateEngine do not fail solely because
    HyperFrames is absent from the test environment.

    Returns ``True`` when the command is found, ``False`` otherwise.
    """
    try:
        available = shutil.which("hyperframes") is not None
    except Exception:
        available = False

    return available


def _collect_assets(gate_context: GateContext | dict[str, Any]) -> list[AssetInfo]:
    """Extract ``AssetInfo`` items from the gate context after execution."""
    from automedia.pipelines.gate_engine import AssetInfo

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
    from automedia.hooks.md5_tracker import get_pipeline_md5, verify_md5

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
    from automedia.hooks.md5_tracker import record_md5

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
# Gate modifier schema + validation (Wave 1)
# ---------------------------------------------------------------------------


def validate_gate_modifiers(
    modifiers: dict[str, Any],
    base_gates: list[str],
    registry: GateRegistry | None = None,
) -> list[str]:
    """Validate and apply gate include/exclude/override_failure_mode modifiers.

    Parameters
    ----------
    modifiers:
        Dict with optional keys: ``include`` (list[str] — gates to add),
        ``exclude`` (list[str] — gates to remove),
        ``override_failure_mode`` (dict[str, str] — gate -> new failure mode).
    base_gates:
        The base gate name list for the current pipeline mode.
    registry:
        Gate registry instance.  Defaults to module-level ``_registry``.

    Returns
    -------
    list[str]
        Modified gate name list after applying includes and excludes.

    Raises
    ------
    ValueError
        If any referenced gate is not registered, CW is excluded,
        or a lifecycle gate (L1–L4) is excluded.
    """
    from automedia.gates.base import _registry

    reg = registry if registry is not None else _registry

    include_names: list[str] = modifiers.get("include", [])
    exclude_names: list[str] = modifiers.get("exclude", [])
    override_fm: dict[str, str] = modifiers.get("override_failure_mode", {})

    all_referenced: set[str] = set(include_names) | set(exclude_names) | set(override_fm.keys())

    # -- Validate all referenced gates exist in the registry --
    for name in all_referenced:
        if name not in reg:
            available = reg.list()
            raise ValueError(
                f"Gate {name!r} is not registered. Available gates: {sorted(available)}"
            )

    # -- CW is required for content generation --
    if "CW" in exclude_names:
        raise ValueError("Gate 'CW' cannot be excluded — required for content generation")

    # -- Lifecycle gates (L1–L4) cannot be excluded --
    for name in _LIFECYCLE_GATE_NAMES:
        if name in exclude_names:
            raise ValueError(f"Gate {name!r} is a lifecycle gate and cannot be excluded")

    # -- Warn if excluding a stop-mode gate --
    for name in exclude_names:
        try:
            gate_cls = reg.get(name)
            failure_mode = getattr(gate_cls, "_failure_mode", "")
            if failure_mode == "stop":
                log.warning(
                    "pipeline.gate_exclude.stop_mode",
                    gate_name=name,
                    hint="Excluding a stop-mode gate means the pipeline will not halt "
                    "on failures in this gate.",
                )
        except KeyError:
            pass  # Already validated above

    # -- Apply includes and excludes --
    result = [g for g in base_gates if g not in exclude_names]
    for name in include_names:
        if name not in result:
            result.append(name)

    return result


def _compose_gate_list(
    mode: str,
    platform_config: dict[str, Any] | None = None,
) -> list[str]:
    """Compose the gate list for a pipeline mode, applying platform modifiers.

    Starts from ``_MODE_MAP[mode]``, then applies gate modifiers from
    *platform_config* (if present).

    Parameters
    ----------
    mode:
        Pipeline mode string (e.g. ``"auto"``, ``"text_only"``).
    platform_config:
        Optional platform configuration dict.  When it contains a ``"gates"``
        key, the value is treated as gate modifiers and passed to
        :func:`validate_gate_modifiers`.

    Returns
    -------
    list[str]
        Final gate name list.

    Raises
    ------
    ValueError
        If *mode* is unknown or gate modifier validation fails.
    """
    base = _MODE_MAP.get(mode)
    if base is None:
        raise ValueError(f"Unknown pipeline mode {mode!r}. Choose from: {list(_MODE_MAP)}")

    if platform_config and "gates" in platform_config:
        return validate_gate_modifiers(platform_config["gates"], list(base))

    return list(base)


def _collect_platform_gate_modifiers(
    brand_profile_dict: dict[str, Any],
    platforms: list[str],
) -> dict[str, Any] | None:
    """Collect gate modifiers from *platforms*, merging with union semantics.

    For each platform, checks whether the brand profile (converted to a
    dict via :func:`dataclasses.asdict`) contains a per-platform gate
    configuration.  When found, include/exclude/override_failure_mode
    entries are merged across all platforms:

    * **Include** — union: a gate is added if *any* platform requests it.
    * **Exclude** — union: a gate is removed if *any* platform excludes it.
      (The actual exclude logic is applied by downstream
      :func:`validate_gate_modifiers` — lifecycle and CW guards still hold.)
    * **override_failure_mode** — last platform wins for conflicting keys.

    Currently the ``BrandProfile`` dataclass stores ``platforms`` as a
    ``list[str]``, so there is no per-platform gate configuration to
    extract.  This function is primarily forward-compatible — it returns
    ``None`` (no-op) for the current schema and will activate when richer
    per-platform configs are introduced.

    Parameters
    ----------
    brand_profile_dict:
        Brand profile as a dict (e.g. ``asdict(brand_profile)``).
    platforms:
        List of platform name strings.

    Returns
    -------
    dict[str, Any] or None
        Merged modifiers dict with ``include``, ``exclude``, and/or
        ``override_failure_mode`` keys, or ``None`` if no platform has
        gate modifiers.
    """
    platforms_value = brand_profile_dict.get("platforms", [])

    # Current schema: platforms is list[str] — no per-platform gate config.
    if isinstance(platforms_value, list):
        return None

    # Future richer format: platforms is a dict with per-platform config.
    if isinstance(platforms_value, dict):
        combined: dict[str, set[str]] = {"include": set(), "exclude": set()}
        override_fm: dict[str, str] = {}
        has_modifiers = False

        for platform in platforms:
            p_config = platforms_value.get(platform, {})
            if not isinstance(p_config, dict):
                continue
            gates_cfg = p_config.get("gates", {})
            if not isinstance(gates_cfg, dict):
                continue

            inc = gates_cfg.get("include", [])
            if isinstance(inc, list):
                combined["include"].update(inc)
                if inc:
                    has_modifiers = True

            exc = gates_cfg.get("exclude", [])
            if isinstance(exc, list):
                combined["exclude"].update(exc)
                if exc:
                    has_modifiers = True

            ofm = gates_cfg.get("override_failure_mode", {})
            if isinstance(ofm, dict):
                override_fm.update(ofm)
                if ofm:
                    has_modifiers = True

        if not has_modifiers:
            return None

        result: dict[str, Any] = {}
        if combined["include"]:
            result["include"] = list(combined["include"])
        if combined["exclude"]:
            result["exclude"] = list(combined["exclude"])
        if override_fm:
            result["override_failure_mode"] = override_fm
        return result

    return None  # Unknown type — no modifiers.


def _filter_gates_for_platform(
    gate_names: list[str],
    platforms: list[str],
    brand_profile: BrandProfile | None = None,
) -> list[str]:
    """Filter *gate_names* based on per-platform gate requirements.

    Union semantics for includes — a gate is kept if *any* platform
    needs it.  Intersection for excludes — a gate is removed only if
    *all* platforms exclude it.

    Like :func:`_collect_platform_gate_modifiers`, this is a forward-
    compatible hook.  With the current ``BrandProfile.platforms`` schema
    (``list[str]``) it is a no-op that returns a copy of *gate_names*.

    Parameters
    ----------
    gate_names:
        The current list of gate names.
    platforms:
        List of target platform names.
    brand_profile:
        Optional brand profile for per-platform gate config lookup.

    Returns
    -------
    list[str]
        Filtered gate name list.
    """
    if not platforms or brand_profile is None:
        return list(gate_names)

    brand_dict = asdict(brand_profile)
    platforms_value = brand_dict.get("platforms", [])

    # Current schema — no per-platform gate config → pass-through.
    if not isinstance(platforms_value, dict):
        return list(gate_names)

    # Future richer format: collect per-platform includes/excludes.
    all_includes: set[str] = set()
    all_excludes: set[str] = set()

    for platform in platforms:
        p_config = platforms_value.get(platform, {})
        if not isinstance(p_config, dict):
            continue
        gates_cfg = p_config.get("gates", {})
        if not isinstance(gates_cfg, dict):
            continue

        inc = gates_cfg.get("include", [])
        if isinstance(inc, list):
            all_includes.update(inc)

        exc = gates_cfg.get("exclude", [])
        if isinstance(exc, list):
            all_excludes.update(exc)

    # Union for includes, intersection for excludes.
    gate_set = set(gate_names) | all_includes
    if all_excludes:
        gate_set -= all_excludes

    return [g for g in gate_names if g in gate_set]


# ---------------------------------------------------------------------------
# Workflow config merge
# ---------------------------------------------------------------------------


def _merge_workflow_config(workflow: Workflow, brand_profile: dict[str, Any]) -> dict[str, Any]:
    """Merge workflow overrides into a brand profile dict.

    Workflow is a higher-priority config layer that sits between explicit
    overrides and brand config.  The following fields are overridden:

    * ``platforms`` — replaced entirely when the workflow specifies them.
    * ``mode`` — noted but *not* applied here (applied by the caller via
      direct assignment to the ``mode`` variable).
    * ``gates`` — stored under ``brand_profile["workflow_gates"]`` so that
      downstream gate composition logic can consume them.
    * ``prompts`` — stored under ``brand_profile["workflow_prompts"]`` so
      that the prompt directory override can be injected into the gate
      context.
    * ``media`` — deep-merged into ``brand_profile["media"]``.

    Parameters
    ----------
    workflow:
        The loaded workflow instance.
    brand_profile:
        The brand profile as a plain dict (e.g. from ``asdict()``).

    Returns
    -------
    dict[str, Any]
        A new dict with workflow overrides applied.  The original
        *brand_profile* is not mutated.
    """
    result = dict(brand_profile)  # shallow copy — safe for scalar/list replacement

    # Platforms — full replacement (when workflow specifies non-empty list)
    if workflow.platforms:
        result["platforms"] = list(workflow.platforms)

    # Gates — store for downstream consumption by gate modifiers
    if workflow.gates is not None:
        result["workflow_gates"] = dict(workflow.gates)

    # Prompts — store directory path for later injection into gate context
    if workflow.prompts is not None:
        result["workflow_prompts"] = dict(workflow.prompts)

    # Media specs — deep-merge into existing media config
    if workflow.media is not None:
        from automedia.core.config_loader import deep_merge

        existing_media = result.get("media", {})
        if isinstance(existing_media, dict):
            result["media"] = deep_merge(existing_media, workflow.media)
        else:
            result["media"] = dict(workflow.media)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_full_pipeline(
    topic: str,
    brand: str,
    *,
    hooks: list[GateHook] | None = None,
    mode: str = "auto",
    workflow: str | None = None,
    decision_mode: str = "build",
    resume_from: str | None = None,
    config_dir: str | None = None,
    tenant_id: str = "default",
    default_lang: str | None = None,
    force_provenance: bool = False,
    director: bool = False,
    progress: PipelineProgress | None = None,
    source_path: str = "",
    source_url: str = "",
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
        ``"text_with_cover"``, ``"video_only"``, ``"qa_only"``,
        ``"image-carousel"``, ``"social-thread"``, or ``"short-video"``.
        When a *workflow* is provided and specifies a ``mode``, that value
        overrides this parameter.
    workflow:
        Optional named workflow to apply.  When provided, workflow config
        (mode, platforms, gates, prompts, media) is merged over the brand
        profile as a higher-priority config layer.
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
    director:
        When ``True``, enables director mode: sets
        ``pause_on_approval=True`` on the gate engine and uses the
        ``director`` HITL preset so that gates with
        ``requires_approval`` pause for external approve/reject calls.
        Default: ``False`` (backward compatible).
    progress:
        Optional progress tracker.  When provided, ``GateEngine.run()``
        emits ``GateProgressEvent`` entries for each gate so agents
        polling via MCP can observe execution in real time.
    source_path:
        Path to a source document (``.md``, ``.txt``, or ``.pdf``).
        Content is loaded and injected into
        ``gate_context["source_content"]`` for downstream gates.
        Falls back gracefully on error.
    source_url:
        URL to fetch source content from.  Content is loaded and
        injected into ``gate_context["source_content"]``.  Falls back
        gracefully on error.

    Returns
    -------
    PipelineResult
        Structured result with status, logs, and asset metadata.
        On unexpected errors the result has ``status="failed"`` and
        ``error`` is populated instead of raising.
    """
    from automedia.core.config_loader import load_config
    from automedia.core.llm_client import get_usage_summary, reset_usage_tracking
    from automedia.core.logging import bind_correlation_id
    from automedia.core.project import Project
    from automedia.core.workflow import WorkflowLoader
    from automedia.engines import resolve_engine
    from automedia.engines.base import BaseVideoEngine
    from automedia.engines.errors import (
        EngineExecutionError,
        EngineNotFoundError,
        EngineUnavailableError,
    )
    from automedia.gates._context import GateContext
    from automedia.hitl import HITLConfig
    from automedia.hooks.cost_tracker import CostTracker
    from automedia.hooks.pipeline_history import PipelineHistoryHook
    from automedia.manifests.brand_profile_schema import (
        BrandProfile,
        load_brand_profile,
        load_brand_profiles,
    )
    from automedia.pipelines.gate_engine import GateEngine, PipelineResult
    from automedia.pipelines.image_pipeline import ImagePipeline
    from automedia.pipelines.language_config import resolve_language_config

    start = time.monotonic()
    correlation_id = bind_correlation_id()

    # Reset token usage tracking for this pipeline run
    reset_usage_tracking()

    if decision_mode is not None and decision_mode != "build":
        warnings.warn(
            "decision_mode is deprecated and will be removed in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        log.warning("decision_mode parameter is deprecated, ignoring value: %s", decision_mode)

    try:
        # 1. Load configuration
        config = load_config(config_dir=config_dir)

        # 2. Create project
        project = Project.init(topic, brand, tenant_id=tenant_id)

        # 2.5 Resolve brand profile from multi-brand config or fallback
        brand_profile: BrandProfile | None = None
        profiles = load_brand_profiles()
        if brand in profiles:
            brand_profile = profiles[brand]
        else:
            brand_profile_path = os.path.join(project.project_dir, "brand-profile.yaml")
            try:
                brand_profile = load_brand_profile(brand_profile_path)
            except (FileNotFoundError, ValueError):
                brand_profile = None

        # 2.75 Derive pipeline mode from brand platforms when not explicitly set
        if mode == "auto" and brand_profile is not None and brand_profile.platforms:
            derived = _derive_mode_from_platforms(brand_profile.platforms)
            if derived:
                mode = derived
                log.info(
                    "pipeline.mode_derived",
                    mode=mode,
                    platforms=brand_profile.platforms,
                )

        # 2.8 Workflow resolution — merge workflow config over brand config
        #     Workflow is a higher-priority config layer (between explicit
        #     overrides and brand config).  It can override mode, platforms,
        #     gates, prompts, and media specs.
        workflow_obj: Workflow | None = None
        if workflow is not None:
            try:
                workflow_loader = WorkflowLoader()
                workflow_obj = workflow_loader.load(workflow)
                log.info(
                    "pipeline.workflow.loaded",
                    workflow=workflow,
                    mode=workflow_obj.mode,
                    platforms=workflow_obj.platforms,
                )
            except (FileNotFoundError, ValueError) as exc:
                log.warning(
                    "pipeline.workflow.load_failed",
                    workflow=workflow,
                    error=str(exc),
                    hint="Pipeline will continue without workflow overrides.",
                )

        # 2.9 Apply workflow config overrides to brand profile
        if workflow_obj is not None and brand_profile is not None:
            brand_dict = _merge_workflow_config(workflow_obj, asdict(brand_profile))
            # Rebuild brand_profile from merged dict
            try:
                brand_profile = BrandProfile(**brand_dict)
            except (TypeError, ValueError) as exc:
                log.warning(
                    "pipeline.workflow.merge_failed",
                    workflow=workflow,
                    error=str(exc),
                    hint="Workflow merge produced invalid brand profile. "
                    "Falling back to original brand config.",
                )

            # Workflow mode overrides the pipeline mode
            mode = workflow_obj.mode
            log.info(
                "pipeline.workflow.mode_override",
                workflow=workflow,
                mode=mode,
            )

        log.info("pipeline.start", topic=topic, brand=brand, mode=mode, tenant_id=tenant_id)

        # 3. Build gate list
        #    Ensure gates module is imported so all gates are registered
        import automedia.gates  # noqa: F401

        gate_names = _compose_gate_list(mode, platform_config=None)

        # 3.1 Apply per-platform gate modifiers from brand profile
        if brand_profile is not None and brand_profile.platforms:
            brand_dict = asdict(brand_profile)
            combined_gate_config = _collect_platform_gate_modifiers(
                brand_dict, list(brand_profile.platforms)
            )
            if combined_gate_config:
                gate_names = _compose_gate_list(mode, {"gates": combined_gate_config})
                log.info(
                    "pipeline.gate_modifiers_applied",
                    platform_count=len(brand_profile.platforms),
                    gate_count=len(gate_names),
                )

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
        if progress is not None:
            progress.set_gate_names([g.gate_name for g in gates])
        log.info("pipeline.gates_constructed", gate_count=len(gates), gate_names=gate_names)

        # 3.75 Inject CostTracker + PipelineHistory hooks
        cost_tracker = CostTracker(project.project_dir)
        history_hook = PipelineHistoryHook()
        all_hooks: list[GateHook] = list(hooks) if hooks else []
        all_hooks.append(cost_tracker)
        all_hooks.append(history_hook)

        # 4. Instantiate engine
        engine = GateEngine(gates, hooks=all_hooks, pause_on_approval=director)
        # Register in global registry for MCP approve/reject tools
        from automedia.pipelines.gate_engine import register_engine

        register_engine(project.project_id, engine)

        lang_config = resolve_language_config(
            brand_profile=brand_profile,
            default_lang=default_lang,
        )

        # 4.75 Load HITL config and inject into context
        try:
            hitl_cfg = HITLConfig(preset_name="director" if director else "automated")
            hitl_config = {
                "enabled_nodes": [n for n in hitl_cfg.list_nodes() if n.get("autoset") == "human"],
                "default_executor": "agent",
                "timeout_s": 86400,  # 24 hours
            }
        except Exception:
            log.warning(
                "pipeline.hitl_config_failed", hint="HITL config unavailable, using empty fallback"
            )
            hitl_config = {
                "enabled_nodes": [],
                "default_executor": "agent",
                "timeout_s": 86400,
            }

        # 5. Build initial context (including correlation_id for distributed tracing)
        gate_context = GateContext(
            topic=topic,
            brand=brand,
            project_id=project.project_id,
            project_dir=project.project_dir,
            config=config,
            tenant_id=tenant_id,
            lang_config=lang_config,
            mode=mode,
            force_provenance=force_provenance,
            brand_profile=asdict(brand_profile) if brand_profile is not None else None,
            correlation_id=correlation_id,
        )

        # 5.1 Inject brand platforms into context for downstream gates
        gate_context["brand_platforms"] = (
            list(brand_profile.platforms) if brand_profile is not None else []
        )

        # 5.1.5 Inject media specs into context for downstream gates
        gate_context["media_specs"] = {}
        if brand_profile is not None and brand_profile.platforms:
            from automedia.core.media_spec import resolve_media_specs

            gate_context["media_specs"] = resolve_media_specs(
                asdict(brand_profile), list(brand_profile.platforms)
            )

        # 4.76 Inject HITL config into context
        gate_context["hitl_config"] = hitl_config
        gate_context["hitl_preset"] = "director" if director else "automated"

        # 4.77 HyperFrames availability detection
        #      Sets a boolean flag; video gates (V0-V7) use it to decide
        #      whether to skip or degrade gracefully.  Never blocks the
        #      pipeline — that decision belongs inside the gate chain.
        #      Also checks the video engine (includes FFmpeg fallback).
        hyperframes_available = _check_hyperframes(mode=mode)
        video_engine_available: bool = False
        try:
            resolve_engine("video", config)
            video_engine_available = True
        except (EngineNotFoundError, EngineExecutionError, EngineUnavailableError):
            pass
        gate_context["hyperframes_available"] = hyperframes_available or video_engine_available
        if gate_context["hyperframes_available"]:
            log.info("pipeline.hyperframes.check", available=True)
        elif mode in ("auto", "video_only"):
            log.warning(
                "pipeline.hyperframes.missing_video_mode",
                mode=mode,
                hint="Install: npm install -g hyperframes. Video gates will be skipped.",
            )
        else:
            log.info(
                "pipeline.hyperframes.skip",
                mode=mode,
                reason="hyperframes not required for this mode",
            )

        # 5.2 Source material loading
        if source_path or source_url:
            material = _resolve_source_material(source_path=source_path, source_url=source_url)
            if material is None:
                log.info(
                    "pipeline.source_material.empty",
                    hint="Both source_path and source_url are empty — skipping",
                )
            elif "error" in material:
                log.warning(
                    "pipeline.source_material.failed",
                    error=material["error"],
                    hint="Falling back to LLM-only mode",
                )
                gate_context["source_content"] = ""
            else:
                gate_context["source_content"] = material["content"]
                gate_context["source_material"] = material
                log.info(
                    "pipeline.source_material.loaded",
                    type=material.get("type"),
                    path=material.get("path"),
                    content_len=len(material["content"]),
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

        # 5.6 Inject content format hint for social-thread / short-video mode
        if mode == "social-thread":
            gate_context["content_format"] = "social_thread"
            log.info("pipeline.content_format", format="social_thread")
        if mode == "short-video":
            gate_context["content_format"] = "short_video"
            log.info("pipeline.content_format", format="short_video")

        # 6. Execute
        try:
            success, results = engine.run(gate_context, progress=progress)
        finally:
            from automedia.pipelines.gate_engine import unregister_engine

            unregister_engine(project.project_id)

        # 6.5 Generate carousel images for image-carousel mode
        carousel_images: list[str] = []
        if mode == "image-carousel":
            try:
                pipeline = ImagePipeline(config=config)
                content = gate_context.get("content", topic)
                project_dir_str = str(project.project_dir)
                carousel_images = pipeline.generate_body_images(
                    topic=content or topic,
                    project_dir=project_dir_str,
                    count=4,
                    brand=brand,
                )
                gate_context["carousel_images"] = carousel_images
                log.info(
                    "pipeline.carousel_images_generated",
                    count=len(carousel_images),
                )
            except Exception as exc:
                log.warning(
                    "pipeline.carousel_images_failed",
                    error=str(exc),
                    hint="Carousel image generation failed — continuing without images",
                )

        # 6.6 Generate cover image for text_with_cover mode
        cover_image: str = ""
        if mode == "text_with_cover":
            try:
                pipeline = ImagePipeline(config=config)
                project_dir_str = (
                    project.project_dir
                    if isinstance(project.project_dir, str)
                    else str(project.project_dir)
                )
                cover_image = pipeline.generate_single_cover(
                    topic=topic,
                    brand=brand,
                    project_dir=project_dir_str,
                )
                gate_context["cover_image"] = cover_image
                log.info("pipeline.cover_image_generated", path=cover_image)
            except Exception as exc:
                log.warning(
                    "pipeline.cover_image_failed",
                    error=str(exc),
                    hint="Cover image generation failed — continuing without cover",
                )

        # 6.5 Video production — produce MP4 from accumulated assets
        video_path: str = ""
        if mode in ("auto", "video_only", "short-video"):
            video_assets = _collect_video_assets(gate_context, project)
            if video_assets:
                try:
                    video_engine = cast(BaseVideoEngine, resolve_engine("video", config))
                    video_path = video_engine.render(
                        video_assets,
                        os.path.join(project.project_dir, "03_video", "output.mp4"),
                    )
                    gate_context["video_path"] = video_path
                    log.info("pipeline.video_produced", path=video_path)
                except (EngineExecutionError, EngineNotFoundError) as exc:
                    log.warning("pipeline.video_production_failed", error=str(exc))
                except Exception as exc:
                    log.warning("pipeline.video_production_unexpected_error", error=str(exc))

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
            status=status,
            duration_s=end - start,
            project_id=project.project_id,
        )

        usage_summary = get_usage_summary()

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
            usage=usage_summary,
            workflow=workflow or "",
        )

    except Exception as exc:
        end = time.monotonic()
        usage_summary = get_usage_summary()
        log.error(
            "pipeline.failed",
            error=str(exc),
            duration_s=end - start,
            topic=topic,
            brand=brand,
        )
        return PipelineResult(
            status="failed",
            topic=topic,
            brand=brand,
            start_time=start,
            end_time=end,
            total_duration_s=end - start,
            error=str(exc),
            usage=usage_summary,
            workflow=workflow or "",
        )


# ---------------------------------------------------------------------------
# Internal helpers used by run_full_pipeline
# ---------------------------------------------------------------------------


def _resolve_source_material(
    source_path: str = "",
    source_url: str = "",
) -> dict[str, Any] | None:
    """Load source material from a file path and/or URL.

    Returns a dict with ``"content"``, ``"type"``, ``"path"`` keys on
    success, a dict with ``"error"`` on failure, or ``None`` when both
    parameters are empty.

    Supported file types: ``.md``, ``.txt``, ``.pdf`` (via OPPAdapter).
    If *source_path* is a directory, it is scanned for the first
    readable document (sorted alphabetically).
    """
    if not source_path and not source_url:
        return None

    contents: list[str] = []
    warnings_: list[str] = []
    result_type: str = ""
    result_path: str = ""

    # --- File path ---
    if source_path:
        path = Path(source_path)
        try:
            if path.is_dir():
                readable = sorted(
                    p
                    for p in path.iterdir()
                    if p.is_file() and p.suffix.lower() in (".md", ".txt", ".pdf")
                )
                if not readable:
                    return {"error": "Source directory contains no readable documents"}
                path = readable[0]

            if not path.exists():
                warnings_.append(f"Source path not found: {source_path}")
            else:
                ext = path.suffix.lower()
                if ext == ".md":
                    content = path.read_text(encoding="utf-8")
                    result_type = "md"
                elif ext == ".txt":
                    content = path.read_text(encoding="utf-8")
                    result_type = "txt"
                elif ext == ".pdf":
                    from automedia.omni.opp_adapter import OPPAdapter

                    adapter = OPPAdapter()
                    opp_result = adapter.extract(str(path))
                    content = opp_result.md_content
                    result_type = "pdf"
                else:
                    warnings_.append(f"Unsupported file type: {ext}")
                    content = None

                if content is not None:
                    contents.append(content)
                    result_path = str(path.resolve())
        except Exception as exc:
            warnings_.append(str(exc))

    # --- URL ---
    if source_url:
        try:
            import urllib.request

            with urllib.request.urlopen(source_url, timeout=30) as resp:  # noqa: S310  # source_url is user-provided config value
                content = resp.read().decode("utf-8")
            contents.append(content)
            if not result_type:
                result_type = "url"
            if not result_path:
                result_path = source_url
        except Exception as exc:
            warnings_.append(f"Failed to fetch URL: {exc}")

    if not contents:
        return {"error": "; ".join(warnings_) if warnings_ else "No content could be loaded"}

    result: dict[str, Any] = {
        "content": "\n\n".join(contents),
        "type": result_type,
        "path": result_path,
    }
    if warnings_:
        result["warnings"] = warnings_
    return result


def _build_gates_from_names(
    names: list[str],
    registry: GateRegistry | None = None,
) -> list[BaseGate]:
    """Instantiate gates by name from the registry."""
    from automedia.gates.base import _registry

    reg = registry if registry is not None else _registry
    return [reg.get(n)() for n in names]


def _build_gates_log(results: list[dict[str, Any]]) -> list[GateLogEntry]:
    """Convert raw gate result dicts into :class:`GateLogEntry` items."""
    from automedia.pipelines.gate_engine import GateLogEntry

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


def _collect_video_assets(
    gate_context: GateContext | dict[str, Any], project: Project
) -> dict[str, Any]:
    """Collect video assets from gate_context into HyperFramesVideoEngine format."""
    # Gather images from gate_context (covers, body)
    images = []
    # Check for cover images
    cover_image = gate_context.get("cover_image", "")
    if cover_image and os.path.isfile(cover_image):
        images.append(cover_image)
    # Check for carousel/body images
    carousel_images = gate_context.get("carousel_images", [])
    images.extend(carousel_images)
    # Check for fallback frame
    fallback_frame = gate_context.get("fallback_frame", "")
    if fallback_frame and os.path.isfile(fallback_frame):
        images.append(fallback_frame)

    audio_path = gate_context.get("audio_path", "")
    subtitles_path = gate_context.get("subtitles_path", "")
    content = gate_context.get("content", "")

    # Only return if we have at least images + audio (minimum for video)
    if not images or not audio_path:
        return {}

    return {
        "images": images,
        "audio": audio_path,
        "subtitles": subtitles_path or "",
        "template_dir": "",  # empty string = use shipped default hyperframes templates
        "content": content,
    }
