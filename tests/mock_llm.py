"""Mock helpers for testing LLM-driven gates without real API calls.

Provides context managers that patch
:func:`automedia.core.llm_client._structured_completion_with_fallback`
— the internal function that actually makes LLM API calls.

Why ``_structured_completion_with_fallback`` and not
``llm_complete_structured_safe``?
Because ``_structured_completion_with_fallback`` is looked up via
**module-level name resolution** (not ``from ... import``), so a single
patch at the definition site correctly intercepts all call paths —
including calls made via  ``llm_check_with_fallback`` (which submits
``llm_complete_structured_safe`` to a thread pool executor).

Usage
-----
>>> from tests.mock_llm import mock_llm_response
>>> from automedia.gates.llm_helpers import llm_check_with_fallback, G0CheckResult
>>>
>>> data = G0CheckResult(passed=True, issues=[])
>>> with mock_llm_response(data) as mock:
...     outcome = llm_check_with_fallback(
...         text="...",
...         check_type="fact_check",
...         prompt_template_name="g0_fact_check",
...         deterministic_fn=lambda t: {"passed": True, "issues": []},
...     )
...     assert outcome["method"] == "llm"
...     assert outcome["passed"] is True
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator
from unittest.mock import patch

if TYPE_CHECKING:
    from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Patch target
#
# We patch the INTERNAL function _structured_completion_with_fallback, not
# the public llm_complete_structured_safe.  Reason: llm_complete_structured
# _safe delegates by name to _structured_completion_with_fallback _within_
# the same module.  Even when some callers have grabbed llm_complete_structured
# _safe via ``from ... import``, the inner name lookup resolves against the
# module dict, which *is* affected by the patch.
# ---------------------------------------------------------------------------

_PATCH_TARGET: str = (
    "automedia.core.llm_client._structured_completion_with_fallback"
)


@contextmanager
def mock_llm_response(response_data: Any) -> Iterator[MagicMock]:
    """Mock the LLM structured-completion path to return *response_data*.

    Parameters
    ----------
    response_data:
        The value to return — typically a Pydantic model instance
        (``G0CheckResult``, ``G2CheckResult``, etc.).
    """
    with patch(_PATCH_TARGET) as mock:
        mock.return_value = response_data
        yield mock


@contextmanager
def mock_llm_failure() -> Iterator[MagicMock]:
    """Simulate LLM API failure to force deterministic fallback.

    The patched function raises ``TimeoutError``, which triggers the
    fallback path in :func:`~automedia.gates.llm_helpers.llm_check_with_fallback`.
    """
    with patch(_PATCH_TARGET) as mock:
        mock.side_effect = TimeoutError("LLM API timeout (simulated)")
        yield mock


@contextmanager
def assert_llm_called(mock: MagicMock, expected_calls: int = 1) -> Iterator[None]:
    """Assert that the LLM was called *expected_calls* times.

    This is typically used as a wrapper around the block where the LLM
    should have been invoked::

        with mock_llm_response(data) as llm_mock:
            with assert_llm_called(llm_mock, expected_calls=1):
                my_function()

    Parameters
    ----------
    mock:
        A ``MagicMock`` obtained from ``mock_llm_response`` or
        ``mock_llm_failure``.
    expected_calls:
        The exact number of times the mock should have been called.
        Defaults to 1.
    """
    yield
    actual = mock.call_count
    assert actual == expected_calls, (
        f"Expected {expected_calls} LLM call(s), got {actual}"
    )
