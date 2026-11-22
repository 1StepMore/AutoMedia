"""Wall-clock timeout and structured-fallback behavior (issue #621).

Covers:
- ``_build_client`` consumes ``llm.<task>.timeout`` (and disables SDK retries).
- No configured timeout leaves SDK defaults untouched.
- A ``beta.chat.completions.parse`` timeout degrades to the manual
  ``response_format={"type": "json_object"}`` path after a single attempt
  and marks the provider as lacking beta structured support.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from automedia.core import llm_client as _llm_client_module
from automedia.core.llm_client import _build_client, _structured_completion_with_fallback

openai = pytest.importorskip("openai")
httpx = pytest.importorskip("httpx")


class _Demo(BaseModel):
    value: str


@pytest.fixture(autouse=True)
def _reset_beta_cache() -> None:
    """Keep the module-level provider cache isolated between tests."""
    _llm_client_module._provider_no_beta_api = {}


def _config(**overrides: Any) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "provider": "test-provider",
        "model": "test-model",
        "api_key": "sk-test",
        "base_url": "https://api.test.com/v1",
    }
    spec.update(overrides)
    return {"llm": {"text_generation": spec}}


def _fallback_response() -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = '{"value": "ok"}'
    response.usage = None
    return response


def test_beta_timeout_degrades_after_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A beta parse timeout is not retried; it degrades immediately."""
    timeout_error = openai.APITimeoutError(request=httpx.Request("POST", "https://api.test.com/v1"))

    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = timeout_error
    client.chat.completions.create.return_value = _fallback_response()

    monkeypatch.setattr(_llm_client_module, "_build_client", lambda *a, **k: client)

    with caplog.at_level(logging.WARNING):
        result = _structured_completion_with_fallback(
            "hello",
            response_format=_Demo,
            config=_config(),
        )

    assert result == _Demo(value="ok")
    # Exactly one beta attempt — no retry storm on a hung provider.
    assert client.beta.chat.completions.parse.call_count == 1
    # The manual json_object fallback took over.
    assert client.chat.completions.create.call_count == 1
    assert _llm_client_module._provider_no_beta_api["test-provider"] is True

    warnings = " ".join(record.getMessage() for record in caplog.records)
    assert "provider=test-provider" in warnings
    assert "model=test-model" in warnings
    assert "elapsed_s=" in warnings


def test_build_client_applies_configured_timeout() -> None:
    """A configured timeout is passed through and SDK retries are disabled."""
    client = _build_client(_config(timeout=7.5))
    try:
        assert client.timeout == 7.5
        assert client.max_retries == 0
    finally:
        client.close()


def test_build_client_without_timeout_keeps_sdk_defaults() -> None:
    """Missing timeout preserves the pre-#621 SDK defaults."""
    client = _build_client(_config())
    try:
        assert client.max_retries == 2
        assert client.timeout.read == 600
    finally:
        client.close()
