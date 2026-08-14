"""Unit tests for the environment gate (W1-T5).

Covers: empty/None ``requires_env`` → configured; every named variable present
→ configured; a missing variable is named in ``missing``; an empty-string
value counts as missing (guide §2.5 honesty rule); the injectable ``environ``
is used instead of ``os.environ``; duplicates are deduped; declaration order
is preserved.
"""

from __future__ import annotations

import pytest

from automedia.validation.env_gate import EnvGateResult, check_env


class TestConfigured:
    def test_empty_requires_env_is_configured(self) -> None:
        result = check_env([], environ={})
        assert result.configured is True
        assert result.missing == []

    def test_none_requires_env_is_configured(self) -> None:
        result = check_env(None, environ={})
        assert result.configured is True
        assert result.missing == []

    def test_all_present_is_configured(self) -> None:
        result = check_env(
            ["API_KEY", "HOST"], environ={"API_KEY": "sk-1", "HOST": "db:5432"}
        )
        assert result.configured is True
        assert result.missing == []


class TestMissing:
    def test_one_missing_is_named(self) -> None:
        result = check_env(["PRESENT", "ABSENT"], environ={"PRESENT": "yes"})
        assert result.configured is False
        assert result.missing == ["ABSENT"]

    def test_empty_string_value_counts_as_missing(self) -> None:
        result = check_env(["EMPTY"], environ={"EMPTY": ""})
        assert result.configured is False
        assert result.missing == ["EMPTY"]

    def test_whitespace_value_is_configured(self) -> None:
        result = check_env(["SPACES"], environ={"SPACES": "  "})
        assert result.configured is True
        assert result.missing == []

    def test_several_missing_keeps_declaration_order(self) -> None:
        result = check_env(["B", "A", "C"], environ={"A": "x"})
        assert result.configured is False
        assert result.missing == ["B", "C"]

    def test_duplicate_names_deduped_in_missing(self) -> None:
        result = check_env(["DUP", "DUP", "REAL"], environ={"REAL": "x"})
        assert result.configured is False
        assert result.missing == ["DUP"]


class TestEnvironInjection:
    def test_injected_environ_is_used_not_os_environ(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key = "ONLY_IN_PROCESS"
        monkeypatch.setenv(key, "from-process")
        result = check_env([key], environ={})
        assert result.configured is False
        assert result.missing == [key]

    def test_default_environ_is_os_environ(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        key = "AUTOMEDIA_VALIDATION_ENV_GATE_TEST"
        monkeypatch.setenv(key, "1")
        result = check_env([key])
        assert result.configured is True
        assert result.missing == []


class TestResult:
    def test_result_is_frozen(self) -> None:
        result = EnvGateResult(configured=True, missing=[])
        with pytest.raises(AttributeError):
            result.configured = False  # type: ignore[misc]
