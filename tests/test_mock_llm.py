"""Tests for LLM mock helpers in ``tests/mock_llm.py``.

These tests validate that the mock helpers correctly intercept
``llm_complete_structured_safe`` without making real API calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from automedia.core.llm_client import llm_complete_structured_safe
from automedia.gates.llm_helpers import (
    G0CheckResult,
    llm_check_with_fallback,
)
from tests.mock_llm import (
    assert_llm_called,
    mock_llm_failure,
    mock_llm_response,
)


# =========================================================================
# mock_llm_response — direct call to llm_complete_structured_safe
# =========================================================================


class TestMockLlmResponseDirect:
    """mock_llm_response patches the function without calling the real LLM."""

    def test_returns_provided_data(self) -> None:
        """mock_llm_response returns the Pydantic model instance."""
        expected = G0CheckResult(passed=True, issues=[], confidence=1.0)
        with mock_llm_response(expected) as mock:
            result = llm_complete_structured_safe(
                "test prompt",
                response_format=G0CheckResult,
            )
        assert result is expected
        assert result.passed is True
        assert result.issues == []

    def test_called_with_prompt(self) -> None:
        """The mock records the prompt passed to llm_complete_structured_safe."""
        data = G0CheckResult(passed=True, issues=[])
        with mock_llm_response(data) as mock:
            llm_complete_structured_safe(
                "my prompt",
                response_format=G0CheckResult,
            )
        args, kwargs = mock.call_args
        assert args[0] == "my prompt"
        assert kwargs.get("response_format") is G0CheckResult

    def test_multiple_calls(self) -> None:
        """Multiple calls to llm_complete_structured_safe work."""
        data = G0CheckResult(passed=True, issues=[])
        with mock_llm_response(data):
            for _ in range(3):
                result = llm_complete_structured_safe(
                    "prompt",
                    response_format=G0CheckResult,
                )
                assert result is data

    def test_context_cleanup_restores_original(self) -> None:
        """After exiting the context, the real function is restored."""
        data = G0CheckResult(passed=False, issues=["x"])
        with mock_llm_response(data):
            pass  # mock was active
        # Verify the mock is no longer active — the function would fail
        # if called without a real API key, but we just check it's a real
        # function (not a MagicMock).
        assert not isinstance(
            llm_complete_structured_safe, MagicMock
        ), "mock leaked outside context"


# =========================================================================
# mock_llm_response — via llm_check_with_fallback
# =========================================================================


class TestMockLlmResponseViaFallback:
    """mock_llm_response also works through llm_check_with_fallback."""

    def test_llm_method_selected(self) -> None:
        """When mock returns a G0CheckResult, method='llm' is chosen."""
        data = G0CheckResult(passed=True, issues=[])
        with mock_llm_response(data):
            result = llm_check_with_fallback(
                text="Some content",
                check_type="fact_check",
                prompt_template_name="fact_check_g0",
                deterministic_fn=lambda t: {"passed": False, "issues": ["fallback"]},
            )
        assert result["method"] == "llm"
        assert result["passed"] is True

    def test_confidence_scaled_to_fail(self) -> None:
        """Mock with passed=False propagates through."""
        data = G0CheckResult(passed=False, issues=["mock issue"], confidence=0.2)
        with mock_llm_response(data):
            result = llm_check_with_fallback(
                text="Bad content",
                check_type="fact_check",
                prompt_template_name="fact_check_g0",
                deterministic_fn=lambda t: {"passed": True, "issues": []},
            )
        assert result["method"] == "llm"
        assert result["passed"] is False
        assert result["issues"] == ["mock issue"]
        assert result["confidence"] == 0.2


# =========================================================================
# mock_llm_failure
# =========================================================================


class TestMockLlmFailure:
    """mock_llm_failure simulates an LLM timeout/API error."""

    def test_raises_on_direct_call(self) -> None:
        """Calling llm_complete_structured_safe raises TimeoutError."""
        with mock_llm_failure():
            with pytest.raises(TimeoutError, match="LLM API timeout"):
                llm_complete_structured_safe(
                    "prompt",
                    response_format=G0CheckResult,
                )

    def test_triggers_deterministic_fallback(self) -> None:
        """llm_check_with_fallback falls back to deterministic_fn."""
        fallback_result = {"passed": True, "issues": ["fallback note"]}

        with mock_llm_failure():
            result = llm_check_with_fallback(
                text="Content",
                check_type="fact_check",
                prompt_template_name="fact_check_g0",
                deterministic_fn=lambda t: fallback_result,
            )
        assert result["method"] == "deterministic"
        assert result["passed"] is True


# =========================================================================
# assert_llm_called
# =========================================================================


class TestAssertLlmCalled:
    """assert_llm_called verifies the mock was used as expected."""

    def test_passes_when_called_once(self) -> None:
        """assert_llm_called does not raise when called_count matches."""
        data = G0CheckResult(passed=True, issues=[])
        with mock_llm_response(data) as mock:
            with assert_llm_called(mock, expected_calls=1):
                llm_complete_structured_safe(
                    "prompt",
                    response_format=G0CheckResult,
                )

    def test_fails_when_not_called(self) -> None:
        """assert_llm_called raises AssertionError when no call was made."""
        data = G0CheckResult(passed=True, issues=[])
        with mock_llm_response(data) as mock:
            with pytest.raises(AssertionError, match="Expected 1 LLM call"):
                with assert_llm_called(mock, expected_calls=1):
                    pass  # no LLM call

    def test_passes_with_custom_count(self) -> None:
        """assert_llm_called accepts custom expected_calls."""
        data = G0CheckResult(passed=True, issues=[])
        with mock_llm_response(data) as mock:
            with assert_llm_called(mock, expected_calls=3):
                for _ in range(3):
                    llm_complete_structured_safe(
                        "prompt",
                        response_format=G0CheckResult,
                    )

    def test_fails_on_wrong_count(self) -> None:
        """assert_llm_called raises when actual count != expected."""
        data = G0CheckResult(passed=True, issues=[])
        with mock_llm_response(data) as mock:
            with pytest.raises(AssertionError, match="Expected 2 LLM call"):
                with assert_llm_called(mock, expected_calls=2):
                    llm_complete_structured_safe(
                        "prompt",
                        response_format=G0CheckResult,
                    )


# =========================================================================
# llm_mock fixture from conftest.py
# =========================================================================


class TestLlmMockFixture:
    """The ``llm_mock`` fixture provides all three helpers."""

    def test_fixture_keys(self, llm_mock: dict[str, Any]) -> None:
        """llm_mock returns dict with response, failure, assert_called."""
        assert "response" in llm_mock
        assert "failure" in llm_mock
        assert "assert_called" in llm_mock

    def test_response_helper_works(self, llm_mock: dict[str, Any]) -> None:
        """Using llm_mock['response'] works end-to-end."""
        data = G0CheckResult(passed=True, issues=[])
        with llm_mock["response"](data):
            result = llm_complete_structured_safe(
                "prompt",
                response_format=G0CheckResult,
            )
        assert result is data

    def test_failure_helper_works(self, llm_mock: dict[str, Any]) -> None:
        """Using llm_mock['failure'] triggers fallback."""
        with llm_mock["failure"]():
            with pytest.raises(TimeoutError):
                llm_complete_structured_safe(
                    "prompt",
                    response_format=G0CheckResult,
                )

    def test_assert_called_helper_works(self, llm_mock: dict[str, Any]) -> None:
        """Using llm_mock['assert_called'] verifies call counts."""
        data = G0CheckResult(passed=True, issues=[])
        with llm_mock["response"](data) as mock:
            with llm_mock["assert_called"](mock, expected_calls=1):
                llm_complete_structured_safe(
                    "prompt",
                    response_format=G0CheckResult,
                )
