"""Unit tests for the regression flywheel helpers (plan W4-T6, C4).

All fixtures are synthetic (Red Line 4): a scenario library under
``tmp_path`` whose steps cite standard keys present in the library's own
fixture ``STANDARDS.md`` (the loader resolves the handbook through
``AUTOMEDIA_VALIDATION_SCENARIOS_DIR``, monkeypatched to the library so the
tests never depend on the real repo handbook).  The fixture library mirrors
the flywheel's two accepted placements (guide §5.2): pinned scenarios under
the canonical ``regression/`` subdirectory and a pinned scenario carried in
place next to its family.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from automedia.validation.loader import LoadError
from automedia.validation.regression import (
    regression_issues,
    regression_scenarios,
    verify_regression_discipline,
)
from automedia.validation.schema import Scenario

_HANDBOOK = """\
## Standards

| Key | Check type | Standard | Source doc | Clause |
| --- | --- | --- | --- | --- |
| tool.contract | data_has | Tool return contract | api-reference | PipelineResult |
| founder-expectations.F01 | artifact_exists | F01 ever-green clause | founder-expectations | §8.3 |
"""


def _step(**overrides: object) -> dict[str, object]:
    """A valid tool-kind step dict (health_check), overridable per test."""
    step: dict[str, object] = {
        "name": "probe the surface",
        "kind": "tool",
        "check": "the surface answers",
        "standard": "tool.contract",
        "tool": "health_check",
        "arguments": {},
        "expect": {"success": True},
    }
    step.update(overrides)
    return step


def _scenario(**overrides: object) -> dict[str, object]:
    """A valid minimal scenario dict, overridable per test."""
    base: dict[str, object] = {
        "name": "unnamed",
        "description": "A synthetic scenario",
        "intent": "Exercise the regression flywheel helpers",
        "user_level": "L0",
        "steps": [_step()],
    }
    base.update(overrides)
    return base


def _write(root: Path, rel: str, data: object) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.fixture()
def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A synthetic library with pinned scenarios in both placements."""
    root = tmp_path / "library"
    root.mkdir()
    (root / "STANDARDS.md").write_text(_HANDBOOK, encoding="utf-8")
    _write(root, "health.yaml", _scenario(name="health-baseline"))
    _write(
        root,
        "regression/glm-fence.yaml",
        _scenario(name="regression-glm-fence", regression=True, regression_issue="#101"),
    )
    _write(
        root,
        "regression/upload-timeout.yaml",
        _scenario(name="regression-upload-timeout", regression=True, regression_issue="#105"),
    )
    _write(
        root,
        "quality/quality-draft.yaml",
        _scenario(name="quality-draft-pin", regression=True, regression_issue="#17"),
    )
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(root))
    return root


@pytest.fixture()
def empty_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A synthetic library with no pinned scenarios."""
    root = tmp_path / "empty"
    root.mkdir()
    (root / "STANDARDS.md").write_text(_HANDBOOK, encoding="utf-8")
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(root))
    return root


class TestRegressionScenarios:
    def test_returns_only_pinned_scenarios_in_load_order(self, library: Path) -> None:
        # Given: a library with three pinned and one unpinned scenario
        # When: the flywheel helper lists regression scenarios
        pinned = regression_scenarios(library)

        # Then: only regression: true scenarios return, in deterministic
        # load order (rglob sorts "quality/" before "regression/")
        assert [s.name for s in pinned] == [
            "quality-draft-pin",
            "regression-glm-fence",
            "regression-upload-timeout",
        ]
        assert all(isinstance(s, Scenario) for s in pinned)
        assert all(s.regression for s in pinned)
        assert [s.regression_issue for s in pinned] == ["#17", "#101", "#105"]

    def test_explicit_dir_ignores_env_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: an env override pointing elsewhere and a second library
        other = tmp_path / "other"
        other.mkdir()
        (other / "STANDARDS.md").write_text(_HANDBOOK, encoding="utf-8")
        _write(
            other,
            "regression/o.yaml",
            _scenario(name="regression-other", regression=True, regression_issue="#9"),
        )
        real = tmp_path / "real"
        real.mkdir()
        (real / "STANDARDS.md").write_text(_HANDBOOK, encoding="utf-8")
        _write(real, "r.yaml", _scenario(name="health-real"))
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(other))

        # When: an explicit scenarios_dir is passed
        pinned = regression_scenarios(real)

        # Then: the explicit directory wins and no scenario is pinned
        assert pinned == []

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        # Given: a scenarios_dir that does not exist
        # When / Then: the helper reports an empty pin list, never crashes
        assert regression_scenarios(tmp_path / "nope") == []

    def test_default_dir_honors_env_override(self, library: Path) -> None:
        # Given: AUTOMEDIA_VALIDATION_SCENARIOS_DIR names the library (the
        # fixture set it)
        # When: no explicit scenarios_dir is passed
        pinned = regression_scenarios()

        # Then: the env override resolves the same tree
        assert {s.name for s in pinned} == {
            "quality-draft-pin",
            "regression-glm-fence",
            "regression-upload-timeout",
        }


class TestRegressionIssues:
    def test_shape_and_values(self, library: Path) -> None:
        # When: the flywheel helper lists the pinned bug references
        issues = regression_issues(library)

        # Then: every entry names the scenario, its issue, and its file
        assert [i["name"] for i in issues] == [
            "quality-draft-pin",
            "regression-glm-fence",
            "regression-upload-timeout",
        ]
        assert [i["regression_issue"] for i in issues] == ["#17", "#101", "#105"]
        for issue in issues:
            assert set(issue) == {"name", "regression_issue", "file"}
            assert isinstance(issue["file"], str)
        by_name = {i["name"]: i for i in issues}
        assert by_name["regression-glm-fence"]["file"].endswith("regression/glm-fence.yaml")
        assert by_name["quality-draft-pin"]["file"].endswith("quality/quality-draft.yaml")

    def test_empty_library(self, empty_library: Path) -> None:
        # Given / When / Then: no pins, no issue references
        assert regression_issues(empty_library) == []


class TestVerifyDiscipline:
    def test_reports_both_placements(self, library: Path) -> None:
        # When: the discipline check runs over the library
        report = verify_regression_discipline(library)

        # Then: the pinned core shape holds with both placements reported
        assert report["count"] == 3
        assert report["regression_scenarios"] == [
            "quality-draft-pin",
            "regression-glm-fence",
            "regression-upload-timeout",
        ]
        assert report["issues"] == regression_issues(library)
        # Belt-and-braces: the schema guarantees an issue for every pin
        assert report["missing_issue"] == []
        # Placement: canonical regression/ subdir vs marker carried in place
        assert report["in_regression_dir"] == [
            "regression-glm-fence",
            "regression-upload-timeout",
        ]
        assert report["in_place"] == ["quality-draft-pin"]

    def test_empty_library(self, empty_library: Path) -> None:
        # Given / When / Then: a pinless library is a healthy discipline
        report = verify_regression_discipline(empty_library)
        assert report["count"] == 0
        assert report["regression_scenarios"] == []
        assert report["issues"] == []
        assert report["missing_issue"] == []
        assert report["in_regression_dir"] == []
        assert report["in_place"] == []

    def test_deterministic(self, library: Path) -> None:
        # Given / When / Then: repeated checks are byte-identical
        assert verify_regression_discipline(library) == verify_regression_discipline(library)


class TestSchemaBeltAndBraces:
    def test_regression_without_issue_rejected_at_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a scenario declares regression: true without an issue
        root = tmp_path / "library"
        root.mkdir()
        (root / "STANDARDS.md").write_text(_HANDBOOK, encoding="utf-8")
        _write(root, "broken.yaml", _scenario(name="regression-broken", regression=True))
        monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(root))

        # When: the library loads through the flywheel helper
        # Then: the schema rejects the pin loudly — the reason
        # missing_issue can only ever be empty
        with pytest.raises(LoadError, match="regression=True requires 'regression_issue'"):
            regression_scenarios(root)
