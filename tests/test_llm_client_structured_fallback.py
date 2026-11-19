"""Fallback exception tuple for structured-output calls (#560).

A thinking model on the beta ``chat.completions.parse`` endpoint can exhaust
``max_tokens`` before the payload terminates, which the SDK reports as
``openai.LengthFinishReasonError``.  That error must route into the manual
parse fallback instead of failing the structured call outright.
"""

from __future__ import annotations

import pytest

from automedia.core.llm_client import _get_fallback_structured_errors

openai = pytest.importorskip("openai")


def test_length_finish_reason_error_in_fallback_tuple() -> None:
    """The SDK's LengthFinishReasonError is part of the fallback tuple."""
    length_error = getattr(openai, "LengthFinishReasonError", None)
    if length_error is None:
        pytest.skip("installed openai SDK predates LengthFinishReasonError")

    errors = _get_fallback_structured_errors()

    assert length_error in errors
    # Pre-existing entries must survive the addition.
    assert AttributeError in errors
    assert NotImplementedError in errors
    assert openai.APIError in errors


def test_fallback_tuple_survives_sdk_without_length_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An older SDK without the class still yields a usable tuple."""
    monkeypatch.delattr(openai, "LengthFinishReasonError", raising=False)

    errors = _get_fallback_structured_errors()

    assert errors
    assert all(
        isinstance(exc_type, type) and issubclass(exc_type, BaseException)
        for exc_type in errors
    )
    assert AttributeError in errors
    assert NotImplementedError in errors
    assert openai.APIError in errors


def test_non_exception_length_attribute_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-exception attribute of that name is not smuggled into the tuple."""
    monkeypatch.setattr(openai, "LengthFinishReasonError", object(), raising=False)

    errors = _get_fallback_structured_errors()

    assert all(
        isinstance(exc_type, type) and issubclass(exc_type, BaseException)
        for exc_type in errors
    )
