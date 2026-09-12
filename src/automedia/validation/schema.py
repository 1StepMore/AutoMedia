"""Closed-field schema for agent-tester validation scenarios.

Parsing is strict: unknown keys and wrong types raise :class:`SchemaError`
naming the offending field — load-time rejection is loud by design (guide §2.4).

AutoMedia deviations from ``docs/agent-tester-validation-guide.md`` §2:
``intent`` (scenario) and ``check``/``standard`` (step) are REQUIRED; step
``kind`` is closed to {"tool", "cli", "file"} (no HTTP adapter —
``requires_http`` stays a schema-only inert flag); ``error_boundary`` is
supported at BOTH levels (scenario: what the coverage audit reads; step:
marks boundary probes); the expect block is closed to the 9 keys below.

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
from typing import Any

from automedia.validation.schema_parse import (
    SchemaError,
    _expect_any_dict,
    _expect_bool,
    _expect_int,
    _expect_number,
    _expect_str,
    _expect_str_list,
    _parse_items,
    _reject_unknown,
)

DEFAULT_TIMEOUT_SECONDS: float = 180.0
"""Project-level timeout ceiling in seconds; applied when a step omits
``timeout_seconds`` (guide §2.4: "project default ceiling")."""

STEP_KINDS: tuple[str, ...] = ("tool", "cli", "file")
"""Closed set of step surfaces. HTTP is deliberately absent (no HTTP adapter)."""

ARTIFACT_CHECK_FIELDS: tuple[str, ...] = ("path", "required")
"""Closed field set of one ``collect_artifacts`` entry (guide §2.2/§4)."""


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
)
"""Field-name → type-parser map for the simple (non-cross-validated) expect keys."""


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
    category: str = "general"
    requires_env: list[str] = field(default_factory=list)
    requires_http: bool = False
    requires_real_llm: bool = False
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

    @classmethod
    def from_dict(cls, data: object) -> Scenario:
        """Parse a scenario dict; unknown keys and wrong types raise :class:`SchemaError`."""
        data = _reject_unknown(data, SCENARIO_FIELDS, "scenario")
        for key in ("name", "description", "intent", "steps"):
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
        return cls(
            name=_expect_str(data["name"], prefix + "name"),
            description=_expect_str(data["description"], prefix + "description"),
            intent=_expect_str(data["intent"], prefix + "intent"),
            category=_expect_str(data.get("category", "general"), prefix + "category"),
            requires_env=_expect_str_list(data.get("requires_env", []), prefix + "requires_env"),
            requires_http=_expect_bool(data.get("requires_http", False), prefix + "requires_http"),
            requires_real_llm=_expect_bool(
                data.get("requires_real_llm", False), prefix + "requires_real_llm"
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
