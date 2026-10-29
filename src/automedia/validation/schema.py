"""Closed-field schema for agent-tester validation scenarios.

Parsing is strict: unknown keys and wrong types raise :class:`SchemaError`
naming the offending field — load-time rejection is loud by design (guide §2.4).

AutoMedia deviations from ``scenarios/STANDARDS.md``:
``intent`` (scenario) and ``check``/``standard`` (step) are REQUIRED; step
``kind`` is closed to {"tool", "cli", "file"} (no HTTP adapter —
``requires_http`` stays a schema-only inert flag); ``error_boundary`` is
supported at BOTH levels (scenario: what the coverage audit reads; step:
marks boundary probes); the expect block is closed to the keys declared by
:class:`Expect`.

Artifact expect design (W1-T6 ``expects.py`` must follow this):
``artifact_exists: <path>`` (path string; the artifact must exist);
``artifact_size_min: <int>`` (minimum size in bytes; it applies to the path
named in ``artifact_exists`` of the SAME expect block — rejected without it);
``artifact_nonempty: <path>`` (path string; must exist and be non-empty).

Timeout contract: ``timeout_seconds`` per step defaults to ``None``, meaning
the engine applies the project ceiling :data:`DEFAULT_TIMEOUT_SECONDS`
(guide §2.2 per-step timeout + §2.4 project default ceiling; skeleton 180.0).

File-kind steps: ``command`` carries the artifact path to inspect (the closed
field set has no dedicated ``path``; ``command`` is the string call spec).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from automedia.validation.schema_parse import (
    SchemaError,
    _expect_any_dict,
    _expect_bool,
    _expect_enum,
    _expect_int,
    _expect_number,
    _expect_str,
    _expect_str_list,
    _expect_str_or_bool,
    _parse_items,
    _reject_unknown,
)

DEFAULT_TIMEOUT_SECONDS: float = 180.0
"""Project-level timeout ceiling in seconds; applied when a step omits
``timeout_seconds`` (guide §2.4: "project default ceiling")."""

STEP_KINDS: tuple[str, ...] = ("tool", "cli", "file")
"""Closed set of step surfaces. HTTP is deliberately absent (no HTTP adapter)."""

USER_LEVELS: tuple[str, ...] = ("L0", "L1", "L2", "L3", "L4", "L5")
"""Closed user-level enum (gap T-10): L0 Unconfigured agent · L1 LLM-configured
agent · L2 Platform-credentialed publisher · L3 Director/human reviewer ·
L4 Multi-tenant/enterprise operator · L5 Localized/non-English user.  A
scenario declares exactly one level so ``validate coverage --by-level`` can
render the stage×user matrix from data instead of auditor judgment."""

ARTIFACT_CHECK_FIELDS: tuple[str, ...] = ("path", "required")
"""Closed field set of one ``collect_artifacts`` entry (guide §2.2/§4)."""

FIXTURES: tuple[str, ...] = ("pipeline_control", "paused_engine", "hitl_pause")
"""Closed set of in-process state fixtures a scenario may declare (T-05).

The engine seeds the same runtime state ``run_pipeline`` creates so the
control/approval MCP tools' success branches are provable deterministically
(a static scenario cannot address the random runtime project id).  See
``automedia.validation.fixtures``."""


@dataclass(frozen=True)
class ArtifactCheck:
    """One entry of a step's ``collect_artifacts`` list (guide §2.2/§4)."""

    path: str
    required: bool = True

    @classmethod
    def from_dict(cls, data: object, where: str = "artifact_check") -> ArtifactCheck:
        """Parse an artifact dict; unknown keys and wrong types raise :class:`SchemaError`."""
        data = _reject_unknown(data, ARTIFACT_CHECK_FIELDS, where)
        if "path" not in data:
            raise SchemaError(f"{where}: missing required field 'path'")
        return cls(
            path=_expect_str(data["path"], f"{where}.path"),
            required=_expect_bool(data.get("required", True), f"{where}.required"),
        )


MEDIA_EXPECT_FIELDS: tuple[str, ...] = (
    "min_count",
    "min_width",
    "min_height",
    "same_size",
    "min_duration_s",
    "max_duration_s",
    "min_bitrate_kbps",
    "decodable",
    "non_uniform",
    "codec",
)
"""Closed field set of a ``media`` expect block (Phase 1.1).

``min_count``/``same_size`` count and compare the multi-file set named by
``artifact_glob``; ``min_width``/``min_height`` apply to image and video
frames; ``min_duration_s``/``max_duration_s``/``min_bitrate_kbps``/``codec``
apply to audio/video streams; ``decodable`` requires a successful ``ffprobe``
parse; ``non_uniform`` rejects flat image fills.  There is no ``max_count``: a
set's upper bound is not part of the Phase 1.1 contract.
"""

TEXT_EXPECT_FIELDS: tuple[str, ...] = (
    "min_paragraphs",
    "min_chars",
    "min_headings",
    "has_heading",
)
"""Closed field set of a ``text`` expect block (Phase 1.1)."""

SUBTITLE_EXPECT_FIELDS: tuple[str, ...] = ("min_cues", "monotonic", "within")
"""Closed field set of a ``subtitle`` expect block (Phase 1.1)."""

COVERAGE_EXPECT_FIELDS: tuple[str, ...] = ("keywords", "min_ratio", "over")
"""Closed field set of a ``keyword_coverage`` expect block (Phase 1.1)."""

TEXT_SIMILARITY_EXPECT_FIELDS: tuple[str, ...] = ("reference", "min_ratio", "over")
"""Closed field set of a ``text_similarity`` expect block."""


@dataclass(frozen=True)
class MediaExpect:
    """Structural media assertions (Phase 1.1).

    ``min_count``/``same_size`` address the multi-file set named by
    ``artifact_glob``; width/height grade image or video frames; duration,
    bitrate, codec, and ``decodable`` grade audio/video streams;
    ``non_uniform`` rejects a flat image fill.  Every field is optional and
    absent fields are not evaluated.
    """

    min_count: int | None = None
    min_width: int | None = None
    min_height: int | None = None
    same_size: bool | None = None
    min_duration_s: float | None = None
    max_duration_s: float | None = None
    min_bitrate_kbps: float | None = None
    decodable: bool | None = None
    non_uniform: bool | None = None
    codec: str | None = None

    @classmethod
    def from_dict(cls, data: object, where: str = "media") -> MediaExpect:
        """Parse a media block; unknown keys and wrong types raise :class:`SchemaError`."""
        data = _reject_unknown(data, MEDIA_EXPECT_FIELDS, where)
        prefix = f"{where}."
        ints = ("min_count", "min_width", "min_height")
        numbers = ("min_duration_s", "max_duration_s", "min_bitrate_kbps")
        kwargs: dict[str, Any] = {}
        for name in ints:
            if name in data:
                value = _expect_int(data[name], prefix + name)
                if value < 0:
                    raise SchemaError(f"{prefix}{name} must be >= 0")
                kwargs[name] = value
        for name in numbers:
            if name in data:
                amount = float(_expect_number(data[name], prefix + name))
                if amount < 0:
                    raise SchemaError(f"{prefix}{name} must be >= 0")
                kwargs[name] = amount
        for name in ("same_size", "decodable", "non_uniform"):
            if name in data:
                kwargs[name] = _expect_bool(data[name], prefix + name)
        if "codec" in data:
            codec = _expect_str(data["codec"], prefix + "codec")
            if not codec.strip():
                raise SchemaError(prefix + "codec must be a non-empty string")
            kwargs["codec"] = codec
        return cls(**kwargs)


@dataclass(frozen=True)
class TextExpect:
    """Structural text/Markdown assertions (Phase 1.1): paragraph count,
    character count, heading count/presence, measured by ``probe_text``."""

    min_paragraphs: int | None = None
    min_chars: int | None = None
    min_headings: int | None = None
    has_heading: bool | None = None

    @classmethod
    def from_dict(cls, data: object, where: str = "text") -> TextExpect:
        """Parse a text block; unknown keys and wrong types raise :class:`SchemaError`."""
        data = _reject_unknown(data, TEXT_EXPECT_FIELDS, where)
        prefix = f"{where}."
        kwargs: dict[str, Any] = {}
        for name in ("min_paragraphs", "min_chars", "min_headings"):
            if name in data:
                value = _expect_int(data[name], prefix + name)
                if value < 0:
                    raise SchemaError(f"{prefix}{name} must be >= 0")
                kwargs[name] = value
        if "has_heading" in data:
            kwargs["has_heading"] = _expect_bool(data["has_heading"], prefix + "has_heading")
        return cls(**kwargs)


@dataclass(frozen=True)
class SubtitleExpect:
    """SRT assertions (Phase 1.1): cue count, timing monotonicity, and the
    ``within`` media path whose duration bounds the last cue's end."""

    min_cues: int | None = None
    monotonic: bool | None = None
    within: str | None = None

    @classmethod
    def from_dict(cls, data: object, where: str = "subtitle") -> SubtitleExpect:
        """Parse a subtitle block; unknown keys and wrong types raise :class:`SchemaError`."""
        data = _reject_unknown(data, SUBTITLE_EXPECT_FIELDS, where)
        prefix = f"{where}."
        kwargs: dict[str, Any] = {}
        if "min_cues" in data:
            value = _expect_int(data["min_cues"], prefix + "min_cues")
            if value < 0:
                raise SchemaError(prefix + "min_cues must be >= 0")
            kwargs["min_cues"] = value
        if "monotonic" in data:
            kwargs["monotonic"] = _expect_bool(data["monotonic"], prefix + "monotonic")
        if "within" in data:
            kwargs["within"] = _expect_str(data["within"], prefix + "within")
        return cls(**kwargs)


@dataclass(frozen=True)
class CoverageExpect:
    """Keyword coverage assertions (Phase 1.1): every keyword in ``keywords``
    must appear in the concatenated text of ``over`` (default: the block's
    ``artifact_exists`` path) at ``min_ratio`` (default 1.0)."""

    keywords: list[str]
    min_ratio: float = 1.0
    over: list[str] | None = None

    @classmethod
    def from_dict(cls, data: object, where: str = "keyword_coverage") -> CoverageExpect:
        """Parse a coverage block; unknown keys, wrong types, and empty keyword
        lists raise :class:`SchemaError`."""
        data = _reject_unknown(data, COVERAGE_EXPECT_FIELDS, where)
        prefix = f"{where}."
        if "keywords" not in data:
            raise SchemaError(f"{where}: missing required field 'keywords'")
        keywords = _expect_str_list(data["keywords"], prefix + "keywords")
        if not keywords:
            raise SchemaError(prefix + "keywords must not be empty")
        for index, keyword in enumerate(keywords):
            if not keyword.strip():
                raise SchemaError(f"{prefix}keywords[{index}]: must be a non-empty string")
        min_ratio = 1.0
        if "min_ratio" in data:
            min_ratio = float(_expect_number(data["min_ratio"], prefix + "min_ratio"))
            if not 0 <= min_ratio <= 1:
                raise SchemaError(prefix + "min_ratio must satisfy 0 <= min_ratio <= 1")
        over = None
        if "over" in data:
            over = _expect_str_list(data["over"], prefix + "over")
            if not over:
                raise SchemaError(prefix + "over must not be empty")
            for index, path in enumerate(over):
                if not path.strip():
                    raise SchemaError(f"{prefix}over[{index}]: must be a non-empty string")
        return cls(keywords=keywords, min_ratio=min_ratio, over=over)


def _expect_artifact_glob(value: object, where: str) -> str:
    """Validate an ``artifact_glob`` locator: non-empty relative glob pattern."""
    pattern = _expect_str(value, where)
    if not pattern.strip():
        raise SchemaError(f"{where}: must be a non-empty string")
    candidate = Path(pattern)
    if candidate.is_absolute():
        raise SchemaError(f"{where}: must be relative, not absolute ({pattern!r})")
    if ".." in candidate.parts:
        raise SchemaError(f"{where}: must not contain '..' ({pattern!r})")
    if "*" not in pattern and "?" not in pattern:
        raise SchemaError(f"{where}: must contain '*' or '?' ({pattern!r})")
    return pattern


_EXPECT_PARSE: tuple[tuple[str, Callable[[object, str], Any]], ...] = (
    ("success", _expect_bool),
    ("data_has", _expect_str_list),
    ("exit_code", _expect_int),
    ("stdout_has", _expect_str_list),
    ("stderr_has", _expect_str_list),
    ("artifact_exists", _expect_str),
    ("artifact_nonempty", _expect_str),
    ("gate_records_pass", _expect_bool),
    ("output_has", _expect_str_list),
    ("min_score", _expect_number),
    ("score_state", _expect_str_list),
    ("error_expected", _expect_bool),
    ("error_code_has", _expect_str_list),
    ("recovery_has", _expect_str_list),
    ("trace_id", _expect_str_or_bool),
    ("artifact_glob", _expect_artifact_glob),
)
"""Field-name → type-parser map for the simple (non-cross-validated) expect keys."""


@dataclass(frozen=True)
class TextSimilarityExpect:
    """Character-bigram similarity between produced text and a reference.

    The candidate text (the concatenation of ``over``, default: the block's
    ``artifact_exists`` path) is compared with ``reference`` after stripping
    punctuation and whitespace; ``min_ratio`` is the required Dice coefficient.
    Bigrams are used so the metric works for unsegmented Chinese without a
    tokenizer, and OCR/ASR letter substitutions show up as a low ratio.
    """

    reference: str
    min_ratio: float
    over: list[str] | None = None

    @classmethod
    def from_dict(cls, data: object, where: str = "text_similarity") -> TextSimilarityExpect:
        """Parse a similarity block; unknown keys and bad values raise :class:`SchemaError`."""
        data = _reject_unknown(data, TEXT_SIMILARITY_EXPECT_FIELDS, where)
        prefix = f"{where}."
        if "reference" not in data:
            raise SchemaError(f"{where}: missing required field 'reference'")
        reference = _expect_str(data["reference"], prefix + "reference")
        if not reference.strip():
            raise SchemaError(prefix + "reference must be a non-empty path")
        if "min_ratio" not in data:
            raise SchemaError(f"{where}: missing required field 'min_ratio'")
        min_ratio = float(_expect_number(data["min_ratio"], prefix + "min_ratio"))
        if not 0 <= min_ratio <= 1:
            raise SchemaError(prefix + "min_ratio must satisfy 0 <= min_ratio <= 1")
        over = None
        if "over" in data:
            over = _expect_str_list(data["over"], prefix + "over")
            if not over:
                raise SchemaError(prefix + "over must not be empty")
            for index, path in enumerate(over):
                if not path.strip():
                    raise SchemaError(f"{prefix}over[{index}]: must be a non-empty string")
        return cls(reference=reference, min_ratio=min_ratio, over=over)


@dataclass(frozen=True)
class Expect:
    """Conjoined assertions for one step (guide §2.3).  Every assertion present
    in the block must hold; absent fields are not evaluated."""

    success: bool | None = None
    data_has: list[str] | None = None
    exit_code: int | None = None
    stdout_has: list[str] | None = None
    stderr_has: list[str] | None = None
    artifact_exists: str | None = None
    artifact_size_min: int | None = None
    artifact_nonempty: str | None = None
    gate_records_pass: bool | None = None
    output_has: list[str] | None = None
    min_score: float | None = None
    score_state: list[str] | None = None
    error_expected: bool | None = None
    error_code_has: list[str] | None = None
    recovery_has: list[str] | None = None
    trace_id: str | bool | None = None
    artifact_glob: str | None = None
    media: MediaExpect | None = None
    text: TextExpect | None = None
    subtitle: SubtitleExpect | None = None
    keyword_coverage: CoverageExpect | None = None
    text_similarity: TextSimilarityExpect | None = None

    @classmethod
    def from_dict(cls, data: object, where: str = "expect") -> Expect:
        """Parse an expect block; unknown keys and wrong types raise :class:`SchemaError`."""
        data = _reject_unknown(data, EXPECT_KEYS, where)
        prefix = f"{where}."
        kwargs: dict[str, Any] = {}
        for name, parse in _EXPECT_PARSE:
            if name in data:
                kwargs[name] = parse(data[name], prefix + name)
        if "artifact_size_min" in data:
            if "artifact_exists" not in data:
                raise SchemaError(
                    prefix + "artifact_size_min requires 'artifact_exists' (its path)"
                )
            size = _expect_int(data["artifact_size_min"], prefix + "artifact_size_min")
            if size < 0:
                raise SchemaError(prefix + "artifact_size_min must be >= 0")
            kwargs["artifact_size_min"] = size
        kwargs["media"] = (
            MediaExpect.from_dict(data["media"], prefix + "media") if "media" in data else None
        )
        kwargs["text"] = (
            TextExpect.from_dict(data["text"], prefix + "text") if "text" in data else None
        )
        kwargs["subtitle"] = (
            SubtitleExpect.from_dict(data["subtitle"], prefix + "subtitle")
            if "subtitle" in data
            else None
        )
        kwargs["keyword_coverage"] = (
            CoverageExpect.from_dict(data["keyword_coverage"], prefix + "keyword_coverage")
            if "keyword_coverage" in data
            else None
        )
        kwargs["text_similarity"] = (
            TextSimilarityExpect.from_dict(data["text_similarity"], prefix + "text_similarity")
            if "text_similarity" in data
            else None
        )
        if "artifact_exists" in data and "artifact_glob" in data:
            raise SchemaError(
                prefix + "artifact_exists and artifact_glob are mutually exclusive "
                "(a single-file locator vs a multi-file set)"
            )
        if kwargs["media"] is not None:
            if "artifact_exists" not in data and "artifact_glob" not in data:
                raise SchemaError(
                    prefix + "media requires 'artifact_exists' (single file) or "
                    "'artifact_glob' (multi-file set)"
                )
            if kwargs["media"].same_size is True and "artifact_glob" not in data:
                raise SchemaError(prefix + "media.same_size=True requires 'artifact_glob'")
            if kwargs["media"].min_count is not None and "artifact_glob" not in data:
                raise SchemaError(
                    prefix + "media.min_count requires 'artifact_glob' (it counts a multi-file set)"
                )
            min_duration = kwargs["media"].min_duration_s
            max_duration = kwargs["media"].max_duration_s
            if (
                min_duration is not None
                and max_duration is not None
                and max_duration < min_duration
            ):
                raise SchemaError(
                    prefix + "media.max_duration_s must be >= media.min_duration_s "
                    f"({max_duration} < {min_duration})"
                )
        return cls(**kwargs)

    def is_empty(self) -> bool:
        """True when the block declares no assertion at all (T-02)."""
        return all(getattr(self, name) is None for name in EXPECT_KEYS)


@dataclass(frozen=True)
class Step:
    """One real call plus its expect block (guide §2.2)."""

    name: str
    kind: str
    check: str
    standard: str
    expect: Expect
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    command: str | None = None
    timeout_seconds: float | None = None
    error_boundary: bool = False
    recovery_steps: list[Step] = field(default_factory=list)
    collect_artifacts: list[ArtifactCheck] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: object, where: str = "step") -> Step:
        """Parse a step dict; unknown keys and wrong types raise :class:`SchemaError`."""
        data = _reject_unknown(data, STEP_FIELDS, where)
        for key in ("name", "kind", "check", "standard", "expect"):
            if key not in data:
                raise SchemaError(f"{where}: missing required field {key!r}")
        prefix = f"{where}."
        kind = _expect_str(data["kind"], prefix + "kind")
        if kind not in STEP_KINDS:
            raise SchemaError(
                prefix + f"kind: unknown kind {kind!r}; supported: {list(STEP_KINDS)}"
            )
        tool = _expect_str(data["tool"], prefix + "tool") if "tool" in data else None
        arguments = (
            _expect_any_dict(data["arguments"], prefix + "arguments")
            if "arguments" in data
            else None
        )
        command = _expect_str(data["command"], prefix + "command") if "command" in data else None
        if kind == "tool":
            if tool is None:
                raise SchemaError(f"{where}: kind 'tool' requires 'tool'")
            if arguments is None:
                raise SchemaError(f"{where}: kind 'tool' requires 'arguments' (empty dict ok)")
            if command is not None:
                raise SchemaError(f"{where}: kind 'tool' must not carry 'command'")
        else:  # kind was already validated to be "cli" or "file"
            if command is None:
                raise SchemaError(
                    f"{where}: kind {kind!r} requires 'command' ('file' = artifact path)"
                )
            if tool is not None:
                raise SchemaError(f"{where}: kind {kind!r} must not carry 'tool'")
        timeout_seconds = None
        if "timeout_seconds" in data:
            timeout_seconds = float(
                _expect_number(data["timeout_seconds"], prefix + "timeout_seconds")
            )
            if timeout_seconds <= 0:
                raise SchemaError(prefix + "timeout_seconds must be > 0")
        return cls(
            name=_expect_str(data["name"], prefix + "name"),
            kind=kind,
            check=_expect_str(data["check"], prefix + "check"),
            standard=_expect_str(data["standard"], prefix + "standard"),
            expect=Expect.from_dict(data["expect"], prefix + "expect"),
            tool=tool,
            arguments=arguments,
            command=command,
            timeout_seconds=timeout_seconds,
            error_boundary=_expect_bool(
                data.get("error_boundary", False), prefix + "error_boundary"
            ),
            recovery_steps=_parse_items(
                data.get("recovery_steps", []), prefix + "recovery_steps", Step.from_dict
            ),
            collect_artifacts=_parse_items(
                data.get("collect_artifacts", []),
                prefix + "collect_artifacts",
                ArtifactCheck.from_dict,
            ),
        )


def _expect_declarative_list(value: object, where: str) -> list[str]:
    """Parse a scenario-header list of non-empty, unique names.

    ``proves_gates``/``proves_modes`` are declarative coverage metadata
    (issue #78): each element must be a non-empty string, and no name may
    repeat — a scenario proves a gate or mode once, or not at all.
    """
    items = _expect_str_list(value, where)
    for index, item in enumerate(items):
        if not item.strip():
            raise SchemaError(f"{where}[{index}]: expected a non-empty name, got {item!r}")
    dupes = sorted({item for item in set(items) if items.count(item) > 1})
    if dupes:
        raise SchemaError(f"{where}: duplicate name(s) {dupes!r} (each must be unique)")
    return items


@dataclass(frozen=True)
class Scenario:
    """A declarative script of real calls against the live system (guide §2.1)."""

    name: str
    description: str
    intent: str
    steps: list[Step]
    user_level: str = "L0"
    category: str = "general"
    requires_env: list[str] = field(default_factory=list)
    requires_http: bool = False
    requires_real_llm: bool = False
    requires_real_adapter: bool = False
    min_passing: int | None = None
    pass_ratio: float | None = None
    regression: bool = False
    regression_issue: str | None = None
    error_boundary: bool = False
    hard: bool = False
    cleanup_steps: list[Step] = field(default_factory=list)
    # Declarative coverage metadata (issue #78): which gates and pipeline
    # modes the scenario proves.  Purely declarative — the coverage audit
    # consumes them; the engine ignores them.
    proves_gates: list[str] = field(default_factory=list)
    proves_modes: list[str] = field(default_factory=list)
    # In-process state fixtures seeded around the primary steps (T-05).
    fixtures: list[str] = field(default_factory=list)
    # Harness/registration scenario (T-09), not a product-surface scenario.
    meta: bool = False

    @classmethod
    def from_dict(cls, data: object) -> Scenario:
        """Parse a scenario dict; unknown keys and wrong types raise :class:`SchemaError`."""
        data = _reject_unknown(data, SCENARIO_FIELDS, "scenario")
        for key in ("name", "description", "intent", "steps", "user_level"):
            if key not in data:
                raise SchemaError(f"scenario: missing required field {key!r}")
        prefix = "scenario."
        steps = _parse_items(data["steps"], prefix + "steps", Step.from_dict)
        if not steps:
            raise SchemaError("scenario.steps must not be empty (a declaration, not a proof)")
        min_passing = None
        if "min_passing" in data:
            min_passing = _expect_int(data["min_passing"], prefix + "min_passing")
            if min_passing < 1:
                raise SchemaError(prefix + "min_passing must be >= 1")
        pass_ratio = None
        if "pass_ratio" in data:
            pass_ratio = float(_expect_number(data["pass_ratio"], prefix + "pass_ratio"))
            if not 0 < pass_ratio <= 1:
                raise SchemaError(prefix + "pass_ratio must satisfy 0 < pass_ratio <= 1")
        regression = _expect_bool(data.get("regression", False), prefix + "regression")
        regression_issue = (
            _expect_str(data["regression_issue"], prefix + "regression_issue")
            if "regression_issue" in data
            else None
        )
        if regression and not regression_issue:
            raise SchemaError(
                "scenario: regression=True requires 'regression_issue' (bug reference)"
            )
        fixtures = _expect_str_list(data.get("fixtures", []), prefix + "fixtures")
        for index, fixture_name in enumerate(fixtures):
            if fixture_name not in FIXTURES:
                raise SchemaError(
                    f"{prefix}fixtures[{index}]: unknown fixture {fixture_name!r}; "
                    f"known: {list(FIXTURES)}"
                )
        return cls(
            name=_expect_str(data["name"], prefix + "name"),
            description=_expect_str(data["description"], prefix + "description"),
            intent=_expect_str(data["intent"], prefix + "intent"),
            user_level=_expect_enum(data["user_level"], USER_LEVELS, prefix + "user_level"),
            category=_expect_str(data.get("category", "general"), prefix + "category"),
            requires_env=_expect_str_list(data.get("requires_env", []), prefix + "requires_env"),
            requires_http=_expect_bool(data.get("requires_http", False), prefix + "requires_http"),
            requires_real_llm=_expect_bool(
                data.get("requires_real_llm", False), prefix + "requires_real_llm"
            ),
            requires_real_adapter=_expect_bool(
                data.get("requires_real_adapter", False), prefix + "requires_real_adapter"
            ),
            min_passing=min_passing,
            pass_ratio=pass_ratio,
            regression=regression,
            regression_issue=regression_issue,
            error_boundary=_expect_bool(
                data.get("error_boundary", False), prefix + "error_boundary"
            ),
            hard=_expect_bool(data.get("hard", False), prefix + "hard"),
            steps=steps,
            cleanup_steps=_parse_items(
                data.get("cleanup_steps", []), prefix + "cleanup_steps", Step.from_dict
            ),
            proves_gates=_expect_declarative_list(
                data.get("proves_gates", []), prefix + "proves_gates"
            ),
            proves_modes=_expect_declarative_list(
                data.get("proves_modes", []), prefix + "proves_modes"
            ),
            fixtures=fixtures,
            meta=_expect_bool(data.get("meta", False), prefix + "meta"),
        )


# Closed field sets, derived from the dataclasses so the constants can never
# drift from the declarations (guide §2.4: "the closed field set above is the
# complete surface of a scenario file").
SCENARIO_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(Scenario))
"""Closed field set of a scenario file (guide §2.1 + plan AutoMedia additions)."""

STEP_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(Step))
"""Closed field set of a step (guide §2.2 + plan AutoMedia additions)."""

EXPECT_KEYS: tuple[str, ...] = tuple(f.name for f in fields(Expect))
"""Closed assertion set of an expect block (plan Scope IN line 128)."""
