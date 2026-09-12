"""Scenario loader for the agent-tester validation engine (guide §3.1 phase 1).

The loader is the contract (guide §2.4): a scenario that reaches the executor
was already validated here, and anything that fails validation is rejected at
load time — loudly, naming the file.  Discovery is a recursive glob over the
scenarios directory: dropping a ``*.yaml`` file anywhere in the tree registers
it for the next run (guide §3.1: "the glob is the registration mechanism"),
which is how ``scenarios/regression/*.yaml`` joins with zero registration.

Error contract: every failure is a :class:`LoadError`, a subclass of the W1-T1
:class:`SchemaError` family (a load failure IS a schema-conformance failure,
now with file context).  Malformed YAML messages name ``path:line``; schema
violations name ``path`` plus the offending field from ``Scenario.from_dict``;
unknown standard keys name the scenario and step; duplicate scenario names
list both files.

The standards registry (``automedia.validation.standards``, W1-T3) is imported
lazily inside functions so this module loads before that task lands and so
tests can inject a fixture registry.  When ``standards=None`` the default
registry is resolved from ``STANDARDS.md`` under the same scenarios directory
(env override ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR``); an absent handbook is a
loud :class:`LoadError`, never a silent pass (Momus improvement 3).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import yaml

from automedia.validation.schema import Scenario, SchemaError, Step


class LoadError(SchemaError):
    """A scenario file failed to load: malformed YAML, a schema violation, an
    unknown standard key, a duplicate scenario name, or an absent standards
    handbook.  The message always names the file and, where available, the
    line and the offending field."""


class StandardsRegistryProtocol(Protocol):
    """Structural contract of the standards registry (pinned by W1-T3):
    ``validate_standard`` answers whether a key is known; ``known_keys()``
    lists the known keys.  The loader depends on this shape only, never on
    the module, so tests can pass any conforming object."""

    def validate_standard(self, key: str) -> bool: ...

    def known_keys(self) -> set[str]: ...


def default_scenarios_dir() -> Path:
    """Resolve the scenarios directory.

    ``AUTOMEDIA_VALIDATION_SCENARIOS_DIR``, when set, REPLACES the default
    ``<repo root>/scenarios`` — the swap point for tests and alternate
    scenario libraries.  The default is derived from this module's location:
    ``src/automedia/validation/loader.py`` resolves to the repo root at
    ``parents[3]`` (parents[0]=validation, [1]=automedia, [2]=src, [3]=root).
    """
    override = os.environ.get("AUTOMEDIA_VALIDATION_SCENARIOS_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[3] / "scenarios"


def load_scenarios(
    scenarios_dir: str | Path | None = None,
    standards: StandardsRegistryProtocol | None = None,
) -> list[Scenario]:
    """Load every scenario under ``scenarios_dir`` in deterministic (path)
    order; a missing directory yields an empty list (guide §7.1 phase 0).

    ``scenarios_dir`` defaults to :func:`default_scenarios_dir` (honoring the
    env override).  ``standards`` defaults to the project registry
    (:class:`StandardsRegistry` from ``automedia.validation.standards``,
    loaded from ``STANDARDS.md`); an absent handbook is a loud
    :class:`LoadError`.

    Raises :class:`LoadError` for malformed YAML (``path:line``), schema
    violations, unknown standard keys, and duplicate scenario names.
    """
    root = default_scenarios_dir() if scenarios_dir is None else Path(scenarios_dir)
    registry = _resolve_standards(standards)
    if not root.is_dir():
        return []
    loaded: list[Scenario] = []
    seen: dict[str, Path] = {}
    for path in sorted(root.rglob("*.yaml")):
        scenario = _load_file(path, registry)
        first = seen.get(scenario.name)
        if first is not None:
            raise LoadError(
                f"{path}: duplicate scenario name {scenario.name!r} (already loaded from {first})"
            )
        seen[scenario.name] = path
        loaded.append(scenario)
    return loaded


def _resolve_standards(
    standards: StandardsRegistryProtocol | None,
) -> StandardsRegistryProtocol:
    """Return the injected registry or lazily load the project one (W1-T3),
    then reject any check type the framework cannot grade (T-02)."""
    if standards is not None:
        _reject_unimplemented_check_types(standards, "injected standards registry")
        return standards
    handbook = default_scenarios_dir() / "STANDARDS.md"
    try:
        from automedia.validation.standards import StandardsRegistry

        registry = StandardsRegistry.from_default()
    except ImportError as exc:
        # Transient seam: W1-T3 is built in parallel; tests inject a registry.
        raise LoadError(
            f"standards registry unavailable: automedia.validation.standards is "
            f"missing (W1-T3 not built yet) — cannot read STANDARDS.md at {handbook}; "
            f"run W2-T1 to author the handbook or set "
            f"AUTOMEDIA_VALIDATION_SCENARIOS_DIR, or pass a registry explicitly"
        ) from exc
    except Exception as exc:  # W1-T3 raises its own StandardsError for an
        # absent handbook; the class may not exist in this revision, so the
        # seam is caught broadly and converted into the loader's loud contract.
        raise LoadError(
            f"standards registry unavailable: STANDARDS.md not found at {handbook}; "
            f"run W2-T1 (author the handbook) or set "
            f"AUTOMEDIA_VALIDATION_SCENARIOS_DIR, or pass a registry explicitly; "
            f"detail: {exc}"
        ) from exc
    _reject_unimplemented_check_types(registry, str(handbook))
    return registry


def _reject_unimplemented_check_types(registry: StandardsRegistryProtocol, label: str) -> None:
    """Reject at load any standard whose check type has no registered
    evaluator (T-02).  Registries without the method are left alone."""
    checker = getattr(registry, "unimplemented_check_types", None)
    if not callable(checker):
        return
    unimplemented = sorted(checker())
    if unimplemented:
        raise LoadError(
            f"{label}: unimplemented standard check-type(s) {unimplemented}; "
            "every check type in the handbook must be bound to a registered "
            "evaluator (see automedia.validation.expects.CHECK_TYPE_EVALUATORS)"
        )


def _load_file(path: Path, registry: StandardsRegistryProtocol) -> Scenario:
    """Parse one scenario file: strict YAML, exactly one document, schema
    validation, per-step standard cross-check."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LoadError(f"{path}: cannot read scenario file: {exc}") from exc
    try:
        docs = list(yaml.safe_load_all(text))
    except yaml.YAMLError as exc:
        raise LoadError(_yaml_error(path, exc)) from exc
    if len(docs) != 1:
        raise LoadError(f"{path}: expected exactly one YAML document, found {len(docs)}")
    doc = docs[0]
    if doc is None:
        raise LoadError(f"{path}: empty scenario file (no YAML document)")
    try:
        scenario = Scenario.from_dict(doc)
    except SchemaError as exc:
        raise LoadError(f"{path}: {exc}") from exc
    _validate_standards(path, scenario, registry)
    _validate_expects(path, scenario)
    return scenario


def _yaml_error(path: Path, error: yaml.YAMLError) -> str:
    """Format a YAML error as ``path:line: problem`` (1-based line when known)."""
    mark = getattr(error, "problem_mark", None)
    line = getattr(mark, "line", None)
    problem = getattr(error, "problem", None) or str(error)
    if line is not None:
        return f"{path}:{line + 1}: {problem}"
    return f"{path}: {problem}"


def _validate_standards(
    path: Path, scenario: Scenario, registry: StandardsRegistryProtocol
) -> None:
    """Reject any step whose ``standard`` key is unknown to the registry,
    recursing into recovery and cleanup steps (guide §2.2/§2.6)."""

    def check(step: Step, where: str) -> None:
        if not registry.validate_standard(step.standard):
            raise LoadError(
                f"{path}: scenario {scenario.name!r} {where} (step {step.name!r}): "
                f"unknown standard key {step.standard!r}; "
                f"known: {sorted(registry.known_keys())}"
            )
        for index, recovery in enumerate(step.recovery_steps):
            check(recovery, f"{where}.recovery_steps[{index}]")

    for index, step in enumerate(scenario.steps):
        check(step, f"steps[{index}]")
    for index, step in enumerate(scenario.cleanup_steps):
        check(step, f"cleanup_steps[{index}]")


def _validate_expects(path: Path, scenario: Scenario) -> None:
    """Reject any non-boundary step with an empty ``expect`` block (T-02).

    Boundary probes are exempt: their contract is "assert an error occurs",
    which an empty expect expresses (the engine's boundary grader owns the
    verdict).  The scenario-level ``error_boundary`` flag exempts every step
    of a boundary-only scenario; the step-level flag exempts that step.
    Recovery and cleanup steps are held to the same rule unless the scenario
    is boundary-only.
    """

    def check(step: Step, where: str) -> None:
        if step.error_boundary or scenario.error_boundary:
            return
        if step.expect.is_empty():
            raise LoadError(
                f"{path}: scenario {scenario.name!r} {where} (step {step.name!r}): "
                "non-boundary step must declare at least one expectation; an "
                "empty expect block is not evidence (add an assertion or mark "
                "the step error_boundary: true)"
            )
        for index, recovery in enumerate(step.recovery_steps):
            check(recovery, f"{where}.recovery_steps[{index}]")

    for index, step in enumerate(scenario.steps):
        check(step, f"steps[{index}]")
    for index, step in enumerate(scenario.cleanup_steps):
        check(step, f"cleanup_steps[{index}]")
