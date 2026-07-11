"""Comprehensive unit tests for automedia.core.llm_client.

Covers:
- LLMError exception class
- _get_retryable_errors() and _RETRYABLE_ERRORS module constant
- _build_client() factory with credential resolution
- _llm_chat_completion_with_retry() retry logic
- _llm_structured_completion_with_retry() retry logic
- llm_complete() public API
- llm_complete_structured() public API

All tests are offline — no real OpenAI API calls are made.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.core.llm_client import (
    LLMError,
    _build_client,
    _get_retryable_errors,
    _llm_chat_completion_with_retry,
    _llm_structured_completion_with_retry,
    llm_complete,
    llm_complete_structured,
)

# ---------------------------------------------------------------------------
# Auto-clean AUTOMEDIA_* env vars for test isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_automedia_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove AUTOMEDIA_* env vars so tests are isolated."""
    for key in [k for k in os.environ if k.startswith("AUTOMEDIA_")]:
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client() -> MagicMock:
    """A mock OpenAI client with a chat.completions.create method."""
    client = MagicMock()
    client.chat.completions.create = MagicMock()
    return client


@pytest.fixture()
def mock_parsed_client() -> MagicMock:
    """A mock OpenAI client with beta.chat.completions.parse method."""
    client = MagicMock()
    client.beta.chat.completions.parse = MagicMock()
    return client


@pytest.fixture()
def mock_response() -> MagicMock:
    """A mock chat completion response with choices[0].message.content."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "Hello from LLM"
    return response


@pytest.fixture()
def mock_parsed_response() -> MagicMock:
    """A mock structured completion response with choices[0].message.parsed."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.parsed = {"key": "value"}
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RetryableTestError(Exception):
    """Custom exception patched into _RETRYABLE_ERRORS for retry testing."""


def _make_mock_response() -> MagicMock:
    """Create a mock OpenAI chat completion response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "mock content"
    return response


def _make_llm_config(
    model: str = "test-model",
    api_key: str = "sk-test",
    base_url: str = "https://api.test.com/v1",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Build a minimal config dict for llm tests.

    Only includes temperature/max_tokens when explicitly provided, matching
    real config behavior where these keys may be absent.
    """
    cfg: dict[str, Any] = {
        "llm": {
            "text_generation": {
                "provider": "test-provider",
                "model": model,
                "api_key": api_key,
                "base_url": base_url,
            }
        }
    }
    if temperature is not None:
        cfg["llm"]["text_generation"]["temperature"] = temperature
    if max_tokens is not None:
        cfg["llm"]["text_generation"]["max_tokens"] = max_tokens
    return cfg


@contextmanager
def _patch_openai_module() -> Generator[MagicMock, None, None]:
    """Context manager that injects a mock openai module into sys.modules.

    Since ``_build_client`` does ``from openai import OpenAI`` internally,
    we need the module in sys.modules.  Yields the mock OpenAI class so
    callers can assert on constructor calls.
    """
    mock_openai_module = MagicMock()
    with patch.dict(sys.modules, {"openai": mock_openai_module}):
        yield mock_openai_module.OpenAI


# =========================================================================
# 1. TestLLMError - Exception class basics
# =========================================================================


class TestLLMError:
    """LLMError is a plain Exception subclass used for LLM-related failures."""

    def test_is_exception_subclass(self) -> None:
        """LLMError inherits from Exception."""
        assert issubclass(LLMError, Exception)

    def test_raises_with_message(self) -> None:
        """LLMError can be raised and carries the message."""
        with pytest.raises(LLMError, match="something went wrong"):
            raise LLMError("something went wrong")


# =========================================================================
# 2. TestGetRetryableErrors - _get_retryable_errors() function
# =========================================================================


class TestGetRetryableErrors:
    """_get_retryable_errors() returns the correct OpenAI error types."""

    def test_returns_tuple(self) -> None:
        """_get_retryable_errors() returns a tuple."""
        result = _get_retryable_errors()
        assert isinstance(result, tuple)

    def test_returns_openai_errors_when_installed(self) -> None:
        """When openai is importable, returns the three retryable error types."""
        try:
            import openai  # noqa: F401
        except ImportError:
            pytest.skip("openai not installed")
        result = _get_retryable_errors()
        assert len(result) == 3
        import openai as _openai  # noqa: F811

        assert _openai.RateLimitError in result
        assert _openai.APITimeoutError in result
        assert _openai.APIConnectionError in result

    def test_returns_empty_tuple_when_openai_missing(self) -> None:
        """When openai cannot be imported, _get_retryable_errors() returns ()."""
        import automedia.core.llm_client as mod

        with patch.dict(sys.modules, {"openai": None}):
            result = mod._get_retryable_errors()
        assert result == ()

    def test_module_constant_is_tuple(self) -> None:
        """The module-level _RETRYABLE_ERRORS is a tuple (computed at import)."""
        import automedia.core.llm_client as mod

        assert isinstance(mod._RETRYABLE_ERRORS, tuple)


# =========================================================================
# 3. TestBuildClient - _build_client() factory
# =========================================================================


class TestBuildClient:
    """_build_client() constructs an OpenAI client from config."""

    def test_constructs_with_api_key_and_base_url(self) -> None:
        """Passes api_key and base_url to OpenAI constructor."""
        config = _make_llm_config()
        with _patch_openai_module() as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(
                api_key="sk-test",
                base_url="https://api.test.com/v1",
            )

    def test_uses_task_type_config(self) -> None:
        """Reads config from llm.<task_type> when task_type is non-default."""
        config: dict[str, Any] = {
            "llm": {
                "vision": {
                    "provider": "vision-provider",
                    "model": "vision-model",
                    "api_key": "sk-vision",
                    "base_url": "https://vision.api.com/v1",
                }
            }
        }
        with _patch_openai_module() as mock_openai:
            _build_client(config, task_type="vision")
            mock_openai.assert_called_once_with(
                api_key="sk-vision",
                base_url="https://vision.api.com/v1",
            )

    def test_omits_empty_base_url(self) -> None:
        """When base_url is empty, omits it from OpenAI() call."""
        config: dict[str, Any] = {
            "llm": {
                "text_generation": {
                    "provider": "test",
                    "model": "test-model",
                    "api_key": "sk-test",
                    "base_url": "",
                }
            }
        }
        with _patch_openai_module() as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(api_key="sk-test")

    def test_raises_llm_error_on_missing_key(self) -> None:
        """Raises LLMError when no API key can be resolved."""
        config: dict[str, Any] = {
            "llm": {
                "text_generation": {
                    "provider": "unknown",
                    "model": "test-model",
                    "base_url": "https://example.com",
                }
            }
        }
        with _patch_openai_module(), pytest.raises(LLMError, match="No API key"):
            _build_client(config)

    def test_resolves_key_via_credential_loader(self) -> None:
        """When api_key is empty, falls through to resolve_api_key()."""
        config: dict[str, Any] = {
            "llm": {
                "text_generation": {
                    "provider": "test-provider",
                    "model": "test-model",
                    "base_url": "https://api.test.com/v1",
                }
            }
        }
        with (
            _patch_openai_module() as mock_openai,
            patch(
                "automedia.core.llm_client.resolve_api_key",
                return_value="sk-resolved",
            ) as mock_resolve,
        ):
            _build_client(config)
            mock_resolve.assert_called_once_with("test-provider")
            mock_openai.assert_called_once_with(
                api_key="sk-resolved",
                base_url="https://api.test.com/v1",
            )

    def test_inline_key_overrides_env(self) -> None:
        """An inline api_key in config takes precedence over resolve_api_key()."""
        config = _make_llm_config(api_key="sk-inline")
        with (
            _patch_openai_module() as mock_openai,
            patch(
                "automedia.core.llm_client.resolve_api_key",
                return_value="sk-from-env",
            ) as mock_resolve,
        ):
            _build_client(config)
            mock_resolve.assert_not_called()
            mock_openai.assert_called_once_with(
                api_key="sk-inline",
                base_url="https://api.test.com/v1",
            )

    def test_raises_import_error_when_openai_missing(self) -> None:
        """Raises ImportError when openai package is not installed."""
        config = _make_llm_config()
        with patch.dict(sys.modules, {"openai": None}), \
                pytest.raises(ImportError, match="openai.*extra"):
            _build_client(config)

    def test_omits_base_url_when_absent_from_config(self) -> None:
        """When base_url key is absent from config, omits it."""
        config: dict[str, Any] = {
            "llm": {
                "text_generation": {
                    "provider": "test",
                    "model": "test-model",
                    "api_key": "sk-test",
                }
            }
        }
        with _patch_openai_module() as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(api_key="sk-test")


# =========================================================================
# 4. TestLlmComplete - llm_complete() public API
# =========================================================================


class TestLlmComplete:
    """llm_complete() sends chat completion requests and returns text."""

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_returns_response_content(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Returns the content string from the LLM response."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_response
        config = _make_llm_config()
        result = llm_complete("Hello", config=config)
        assert result == "Hello from LLM"

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_sends_user_message(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Passes the prompt as a user message."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_response
        config = _make_llm_config()
        llm_complete("What is AI?", config=config)
        messages = mock_retry.call_args[1]["messages"]
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["content"] == "What is AI?"

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_sends_system_prompt(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """When system_prompt is given, prepends it as a system message."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_response
        config = _make_llm_config()
        llm_complete("Hello", config=config, system_prompt="You are helpful.")
        messages = mock_retry.call_args[1]["messages"]
        assert messages[0] == {"role": "system", "content": "You are helpful."}
        assert messages[1] == {"role": "user", "content": "Hello"}

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_uses_model_from_config(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Uses the model from config when no model override is given."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_response
        config = _make_llm_config(model="gpt-4o")
        llm_complete("Hello", config=config)
        assert mock_retry.call_args[1]["model"] == "gpt-4o"

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_model_override_takes_precedence(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Explicit model= parameter overrides config model."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_response
        config = _make_llm_config(model="gpt-4o")
        llm_complete("Hello", config=config, model="gpt-4o-mini")
        assert mock_retry.call_args[1]["model"] == "gpt-4o-mini"

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_temperature_and_max_tokens_from_config(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Uses temperature and max_tokens from config."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_response
        config = _make_llm_config(temperature=0.5, max_tokens=1024)
        llm_complete("Hello", config=config)
        assert mock_retry.call_args[1]["temperature"] == 0.5
        assert mock_retry.call_args[1]["max_tokens"] == 1024

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_raises_llm_error_on_no_model(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
    ) -> None:
        """Raises LLMError when no model is configured or passed."""
        mock_build.return_value = MagicMock()
        config = _make_llm_config(model="")
        with pytest.raises(LLMError, match="No model configured"):
            llm_complete("Hello", config=config)

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_raises_llm_error_on_provider_error(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
    ) -> None:
        """Wraps provider exceptions in LLMError."""
        mock_build.return_value = MagicMock()
        mock_retry.side_effect = RuntimeError("API down")
        config = _make_llm_config()
        with pytest.raises(LLMError, match="LLM completion failed.*API down"):
            llm_complete("Hello", config=config)

    @patch("automedia.core.llm_client._build_client")
    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    def test_lazy_loads_config_when_none(
        self,
        mock_retry: MagicMock,
        mock_build: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """When config=None, lazy-loads via load_config()."""
        mock_retry.return_value = mock_response
        mock_build.return_value = MagicMock()
        loaded_config = _make_llm_config()
        with patch(
            "automedia.core.config_loader.load_config",
            return_value=loaded_config,
        ) as mock_load:
            result = llm_complete("Hello", config=None)
            mock_load.assert_called_once()
            assert result == "Hello from LLM"

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_default_temperature_is_07(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Default temperature is 0.7 when not in config or params."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_response
        # Config without temperature key triggers the default
        config = _make_llm_config()
        llm_complete("Hello", config=config)
        assert mock_retry.call_args[1]["temperature"] == 0.7

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_default_max_tokens_is_2048(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """Default max_tokens is 2048 when not in config or params."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_response
        # Config without max_tokens key triggers the default
        config = _make_llm_config()
        llm_complete("Hello", config=config)
        assert mock_retry.call_args[1]["max_tokens"] == 2048

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_handles_empty_response_content(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
    ) -> None:
        """Returns empty string when response content is None."""
        mock_build.return_value = MagicMock()
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = None
        mock_retry.return_value = response
        config = _make_llm_config()
        result = llm_complete("Hello", config=config)
        assert result == ""

    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_no_system_prompt_when_none(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_response: MagicMock,
    ) -> None:
        """When system_prompt is None, only the user message is sent."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_response
        config = _make_llm_config()
        llm_complete("Hello", config=config, system_prompt=None)
        messages = mock_retry.call_args[1]["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"


# =========================================================================
# 5. TestLlmCompleteStructured - llm_complete_structured() public API
# =========================================================================


class TestLlmCompleteStructured:
    """llm_complete_structured() sends structured requests and returns parsed data."""

    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_returns_parsed_response(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_parsed_response: MagicMock,
    ) -> None:
        """Returns the parsed object from the structured LLM response."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_parsed_response
        config = _make_llm_config()
        result = llm_complete_structured("Hello", response_format=dict, config=config)
        assert result == {"key": "value"}

    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_default_max_tokens_is_4096(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_parsed_response: MagicMock,
    ) -> None:
        """Default max_tokens is 4096 for structured output."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_parsed_response
        # Config without max_tokens key triggers the structured default
        config = _make_llm_config()
        llm_complete_structured("Hello", response_format=dict, config=config)
        assert mock_retry.call_args[1]["max_tokens"] == 4096

    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_passes_response_format(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
        mock_parsed_response: MagicMock,
    ) -> None:
        """Passes the response_format to the retry wrapper."""
        mock_build.return_value = MagicMock()
        mock_retry.return_value = mock_parsed_response
        config = _make_llm_config()
        llm_complete_structured("Hello", response_format=dict, config=config)
        assert mock_retry.call_args[1]["response_format"] is dict

    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_raises_llm_error_on_provider_error(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
    ) -> None:
        """Wraps provider exceptions in LLMError for structured calls."""
        mock_build.return_value = MagicMock()
        mock_retry.side_effect = RuntimeError("Structured API error")
        config = _make_llm_config()
        with pytest.raises(LLMError, match="LLM structured completion failed"):
            llm_complete_structured("Hello", response_format=dict, config=config)

    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    @patch("automedia.core.llm_client._build_client")
    def test_raises_llm_error_on_no_model(
        self,
        mock_build: MagicMock,
        mock_retry: MagicMock,
    ) -> None:
        """Raises LLMError when no model is configured for structured output."""
        mock_build.return_value = MagicMock()
        config = _make_llm_config(model="")
        with pytest.raises(LLMError, match="No model configured"):
            llm_complete_structured("Hello", response_format=dict, config=config)

    @patch("automedia.core.llm_client._build_client")
    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    def test_lazy_loads_config_when_none(
        self,
        mock_retry: MagicMock,
        mock_build: MagicMock,
        mock_parsed_response: MagicMock,
    ) -> None:
        """When config=None, lazy-loads via load_config() for structured calls."""
        mock_retry.return_value = mock_parsed_response
        mock_build.return_value = MagicMock()
        loaded_config = _make_llm_config()
        with patch(
            "automedia.core.config_loader.load_config",
            return_value=loaded_config,
        ) as mock_load:
            result = llm_complete_structured("Hello", response_format=dict, config=None)
            mock_load.assert_called_once()
            assert result == {"key": "value"}


# =========================================================================
# 6. TestRetryWrappers - Tenacity retry behavior
# =========================================================================


class TestRetryWrappers:
    """Both retry wrappers retry on transient OpenAI errors with exponential backoff."""

    def test_retries_on_rate_limit_error(self, mock_client: MagicMock) -> None:
        """Retries when a retryable error (simulating RateLimitError) is raised."""
        response = _make_mock_response()
        mock_client.chat.completions.create.side_effect = [
            _RetryableTestError("rate limited"),
            response,
        ]
        with patch("automedia.core.llm_client._RETRYABLE_ERRORS", (_RetryableTestError,)):
            result = _llm_chat_completion_with_retry(
                mock_client, "model", [], 0.7, 100
            )
        assert result == response
        assert mock_client.chat.completions.create.call_count == 2

    def test_retries_on_timeout_error(self, mock_client: MagicMock) -> None:
        """Retries when a timeout error is raised."""
        response = _make_mock_response()
        mock_client.chat.completions.create.side_effect = [
            _RetryableTestError("timeout"),
            response,
        ]
        with patch("automedia.core.llm_client._RETRYABLE_ERRORS", (_RetryableTestError,)):
            result = _llm_chat_completion_with_retry(
                mock_client, "model", [], 0.7, 100
            )
        assert result == response

    def test_retries_on_connection_error(self, mock_client: MagicMock) -> None:
        """Retries when a connection error is raised."""
        response = _make_mock_response()
        mock_client.chat.completions.create.side_effect = [
            _RetryableTestError("connection failed"),
            response,
        ]
        with patch("automedia.core.llm_client._RETRYABLE_ERRORS", (_RetryableTestError,)):
            result = _llm_chat_completion_with_retry(
                mock_client, "model", [], 0.7, 100
            )
        assert result == response

    def test_does_not_retry_on_non_retryable_error(self, mock_client: MagicMock) -> None:
        """Non-retryable errors propagate immediately without retry."""
        mock_client.chat.completions.create.side_effect = ValueError("bad request")
        with patch("automedia.core.llm_client._RETRYABLE_ERRORS", (_RetryableTestError,)), \
                pytest.raises(ValueError, match="bad request"):
            _llm_chat_completion_with_retry(
                mock_client, "model", [], 0.7, 100
            )
        assert mock_client.chat.completions.create.call_count == 1

    def test_succeeds_on_second_attempt(self, mock_client: MagicMock) -> None:
        """Succeeds when the second attempt returns a valid response."""
        response = _make_mock_response()
        mock_client.chat.completions.create.side_effect = [
            _RetryableTestError("transient"),
            response,
        ]
        with patch("automedia.core.llm_client._RETRYABLE_ERRORS", (_RetryableTestError,)):
            result = _llm_chat_completion_with_retry(
                mock_client, "model", [], 0.7, 100
            )
        assert result == response
        assert mock_client.chat.completions.create.call_count == 2

    def test_retries_exactly_three_times(self, mock_client: MagicMock) -> None:
        """After 3 failed retryable attempts, re-raises the exception."""
        mock_client.chat.completions.create.side_effect = _RetryableTestError(
            "always fail"
        )
        with patch("automedia.core.llm_client._RETRYABLE_ERRORS", (_RetryableTestError,)), \
                pytest.raises(_RetryableTestError, match="always fail"):
            _llm_chat_completion_with_retry(
                mock_client, "model", [], 0.7, 100
            )
        assert mock_client.chat.completions.create.call_count == 3

    def test_structured_retry_retries_on_transient_error(
        self, mock_parsed_client: MagicMock
    ) -> None:
        """The structured retry wrapper also retries on transient errors."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.parsed = {"result": "ok"}
        mock_parsed_client.beta.chat.completions.parse.side_effect = [
            _RetryableTestError("transient"),
            response,
        ]
        with patch("automedia.core.llm_client._RETRYABLE_ERRORS", (_RetryableTestError,)):
            result = _llm_structured_completion_with_retry(
                mock_parsed_client, "model", [], dict, 0.7, 100
            )
        assert result == response
        assert mock_parsed_client.beta.chat.completions.parse.call_count == 2

    def test_no_retry_when_retryable_errors_empty(self, mock_client: MagicMock) -> None:
        """When _RETRYABLE_ERRORS is empty, no retries occur even for matching errors."""
        mock_client.chat.completions.create.side_effect = _RetryableTestError(
            "no retry"
        )
        with patch("automedia.core.llm_client._RETRYABLE_ERRORS", ()), \
                pytest.raises(_RetryableTestError, match="no retry"):
            _llm_chat_completion_with_retry(
                mock_client, "model", [], 0.7, 100
            )
        assert mock_client.chat.completions.create.call_count == 1


# =========================================================================
# 7. TestCredentialResolutionIntegration - Credential resolution paths
# =========================================================================


class TestCredentialResolutionIntegration:
    """_build_client credential resolution with environment variables."""

    def test_env_var_resolved_as_api_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When no inline api_key, resolves from AUTOMEDIA_<PROVIDER> env var."""
        monkeypatch.setenv("AUTOMEDIA_TESTPROVIDER", "sk-from-env")
        config: dict[str, Any] = {
            "llm": {
                "text_generation": {
                    "provider": "testprovider",
                    "model": "test-model",
                    "base_url": "https://api.test.com/v1",
                }
            }
        }
        with _patch_openai_module() as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(
                api_key="sk-from-env",
                base_url="https://api.test.com/v1",
            )

    def test_inline_key_takes_priority_over_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Inline api_key in config takes priority over environment variable."""
        monkeypatch.setenv("AUTOMEDIA_TESTPROVIDER", "sk-from-env")
        config: dict[str, Any] = {
            "llm": {
                "text_generation": {
                    "provider": "testprovider",
                    "model": "test-model",
                    "api_key": "sk-inline",
                    "base_url": "https://api.test.com/v1",
                }
            }
        }
        with _patch_openai_module() as mock_openai:
            _build_client(config)
            mock_openai.assert_called_once_with(
                api_key="sk-inline",
                base_url="https://api.test.com/v1",
            )


# =========================================================================
# 8. TestConfigFallback - Lazy config loading
# =========================================================================


class TestConfigFallback:
    """llm_complete and llm_complete_structured lazy-load config when None."""

    @patch("automedia.core.llm_client._build_client")
    @patch("automedia.core.llm_client._llm_chat_completion_with_retry")
    def test_lazy_loads_config_for_llm_complete(
        self,
        mock_retry: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        """llm_complete with config=None imports and calls load_config()."""
        response = _make_mock_response()
        mock_retry.return_value = response
        mock_build.return_value = MagicMock()
        loaded = _make_llm_config()
        with patch(
            "automedia.core.config_loader.load_config",
            return_value=loaded,
        ) as mock_load:
            result = llm_complete("test prompt", config=None)
            mock_load.assert_called_once()
            assert result == "mock content"

    @patch("automedia.core.llm_client._build_client")
    @patch("automedia.core.llm_client._llm_structured_completion_with_retry")
    def test_lazy_loads_config_for_structured(
        self,
        mock_retry: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        """llm_complete_structured with config=None imports and calls load_config()."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.parsed = {"parsed": True}
        mock_retry.return_value = response
        mock_build.return_value = MagicMock()
        loaded = _make_llm_config()
        with patch(
            "automedia.core.config_loader.load_config",
            return_value=loaded,
        ) as mock_load:
            result = llm_complete_structured(
                "test prompt", response_format=dict, config=None
            )
            mock_load.assert_called_once()
            assert result == {"parsed": True}
