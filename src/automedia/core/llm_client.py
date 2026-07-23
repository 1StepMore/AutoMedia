"""LLM client — unified interface for text-generation providers.

Supports OpenAI-compatible APIs (OpenAI, Azure, Ollama, etc.).
Config is read from the merged AutoMedia config dict at call time.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from automedia.core.credential_loader import resolve_api_key
from automedia.exceptions import AutoMediaError

if TYPE_CHECKING:
    from openai import OpenAI
    from openai.types.chat import ChatCompletion, ParsedChatCompletion


# ---------------------------------------------------------------------------
# Token usage tracker (thread-local, module-level)
# ---------------------------------------------------------------------------


class _UsageTracker:
    """Thread-local accumulator for LLM token usage.

    Thread safety comes from :class:`threading.local` — each thread gets
    its own call list and counters.  No locks needed.
    """

    def __init__(self) -> None:
        self._local = threading.local()

    def reset(self) -> None:
        """Clear accumulated usage for the current thread."""
        self._local.calls = []
        self._local.prompt_tokens = 0
        self._local.completion_tokens = 0
        self._local.total_tokens = 0

    def record(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        model: str,
    ) -> None:
        """Record a single LLM call's token usage."""
        if not hasattr(self._local, "calls"):
            self.reset()
        self._local.calls.append(
            {
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        )
        self._local.prompt_tokens += prompt_tokens
        self._local.completion_tokens += completion_tokens
        self._local.total_tokens += total_tokens

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all accumulated usage.

        Returns
        -------
        dict
            Keys: ``calls`` (list of per-call dicts), ``prompt_tokens``,
            ``completion_tokens``, ``total_tokens``.
        """
        if not hasattr(self._local, "calls"):
            return {
                "calls": [],
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        return {
            "calls": list(self._local.calls),
            "prompt_tokens": self._local.prompt_tokens,
            "completion_tokens": self._local.completion_tokens,
            "total_tokens": self._local.total_tokens,
        }

    def delta_from(self, previous: dict[str, Any]) -> dict[str, Any]:
        """Return usage delta since *previous* snapshot.

        Parameters
        ----------
        previous:
            A snapshot dict previously returned by :meth:`snapshot`.

        Returns
        -------
        dict
            Keys: ``calls`` (new calls only), ``prompt_tokens``,
            ``completion_tokens``, ``total_tokens``.
        """
        current = self.snapshot()
        prev_count = len(previous.get("calls", []))
        return {
            "calls": current["calls"][prev_count:],
            "prompt_tokens": current["prompt_tokens"] - previous.get("prompt_tokens", 0),
            "completion_tokens": current["completion_tokens"]
            - previous.get("completion_tokens", 0),
            "total_tokens": current["total_tokens"] - previous.get("total_tokens", 0),
        }


_usage_tracker = _UsageTracker()


def reset_usage_tracking() -> None:
    """Reset the thread-local usage tracker.

    Call at the start of each pipeline run so that per-pipeline
    accumulations do not leak across runs in the same thread.
    """
    _usage_tracker.reset()


def get_usage_summary() -> dict[str, Any]:
    """Return the current accumulated usage snapshot.

    Returns
    -------
    dict
        Keys: ``calls`` (list of dicts with ``model``, ``prompt_tokens``,
        ``completion_tokens``, ``total_tokens``), ``prompt_tokens``,
        ``completion_tokens``, ``total_tokens``.
    """
    return _usage_tracker.snapshot()


def get_usage_delta(previous: dict[str, Any]) -> dict[str, Any]:
    """Return usage delta since *previous* snapshot.

    Parameters
    ----------
    previous:
        A snapshot dict previously returned by :func:`get_usage_summary`.

    Returns
    -------
    dict
        Keys: ``calls`` (new calls only), ``prompt_tokens``,
        ``completion_tokens``, ``total_tokens``.
    """
    return _usage_tracker.delta_from(previous)


# ---------------------------------------------------------------------------
# Retryable error types (lazily resolved — openai is optional)
# ---------------------------------------------------------------------------


def _get_retryable_errors() -> tuple[type[BaseException], ...]:
    """Return the OpenAI exception types that are safe to retry."""
    try:
        import openai

        return (
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.APIConnectionError,
        )
    except ImportError:
        return ()


_RETRYABLE_ERRORS: tuple[type[BaseException], ...] = _get_retryable_errors()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fake LLM mode (AUTOMEDIA_FAKE_LLM env var)
# ---------------------------------------------------------------------------

_fake_llm_warned: bool = False


def _is_fake_mode(config: dict[str, Any] | None = None) -> bool:
    """Check whether fake LLM mode is active.

    Priority
    --------
    1. ``AUTOMEDIA_FAKE_LLM`` environment variable (fast, primary mechanism).
    2. ``llm.fake_mode: true`` in the merged config file (fallback for
       environments where env vars are not practical, e.g. compound shell
       commands, container entrypoints, or systemd services).
    """
    if os.environ.get("AUTOMEDIA_FAKE_LLM", "").lower() in {"1", "true", "yes"}:
        return True
    if config is not None:
        return bool(config.get("llm", {}).get("fake_mode", False))
    return False


def _warn_fake_once() -> None:
    """Emit a one-time warning that fake LLM mode is active."""
    global _fake_llm_warned
    if not _fake_llm_warned:
        logger.warning(
            "AUTOMEDIA_FAKE_LLM=1 active — returning deterministic mock responses"
        )
        _fake_llm_warned = True


def _fake_structured_response(response_format: type) -> BaseModel:
    """Return a deterministic canned instance of *response_format*.

    Known gate result types receive realistic-looking data.  All others
    receive a minimal ``{"passed": True}`` (or the closest valid variant).
    """
    _DISPATCH: dict[str, dict[str, object]] = {
        "G0CheckResult": {"passed": True, "confidence": 0.95},
        "G1CheckResult": {"passed": True, "score": 0.85, "humanized": True, "changes": []},
        "G2CheckResult": {"passed": True, "issues": [], "score": 0.9},
    }
    name = response_format.__name__
    if name in _DISPATCH:
        return response_format.model_validate(_DISPATCH[name])
    try:
        return response_format.model_validate({"passed": True})
    except Exception:
        # Last resort: construct with zero-valued fields
        return response_format.model_construct(passed=True)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMError(AutoMediaError):
    """Raised when the LLM provider returns an error or is unreachable."""


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def _build_client(
    config: dict[str, Any],
    task_type: str = "text_generation",
) -> OpenAI:
    """Build an ``openai.OpenAI`` client from *config*.

    Reads ``llm.<task_type>`` from *config* and resolves the API key
    via :func:`~automedia.core.credential_loader.resolve_api_key`.

    Parameters
    ----------
    config:
        The merged AutoMedia configuration dict.
    task_type:
        Config section to read (e.g. ``text_generation``, ``vision``,
        ``subtitle_proofread``).  Defaults to ``text_generation``.

    Returns
    -------
    openai.OpenAI
        A configured OpenAI client instance.

    Raises
    ------
    LLMError
        If no API key can be resolved.
    """
    # Lazy import: openai is an optional dependency
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' extra is required to use the OpenAI provider. "
            "Install it with: pip install automedia[openai]"
        ) from None

    llm_cfg: dict[str, Any] = config.get("llm", {}).get(task_type, {})
    provider: str = llm_cfg.get("provider", "") or ""
    api_key: str = llm_cfg.get("api_key", "") or ""

    # If no inline key, try credential resolver
    if not api_key:
        resolved = resolve_api_key(provider or "openai")
        if resolved:
            api_key = resolved

    if not api_key:
        raise LLMError(
            f"No API key for provider {provider!r}. "
            "Set AUTOMEDIA_LLM_API_KEY, add to model_config.yaml, "
            "or run `automedia init`."
        )

    base_url: str | None = llm_cfg.get("base_url") or None

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    return OpenAI(**client_kwargs)


# ---------------------------------------------------------------------------
# Retryable wrappers (private)
# ---------------------------------------------------------------------------


def _llm_chat_completion_with_retry(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],  # type: ignore[type-arg]  # OpenAI expects ChatCompletionMessageParam, not plain dict[str, str]
    temperature: float,
    max_tokens: int,
) -> ChatCompletion:
    """Call ``client.chat.completions.create`` with exponential-backoff retry.

    Retries on transient OpenAI errors (rate-limit, timeout, connection).
    Non-retryable errors propagate immediately.

    Token usage from the response is automatically recorded in the
    thread-local :class:`_UsageTracker`.
    """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
        reraise=True,
    )
    def _call() -> ChatCompletion:
        return client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]  # OpenAI expects ChatCompletionMessageParam, not list[dict[str, str]]
            temperature=temperature,
            max_tokens=max_tokens,
        )

    response = _call()

    # Capture token usage — .usage may be None for some providers
    if response.usage is not None:
        _usage_tracker.record(
            prompt_tokens=response.usage.prompt_tokens or 0,
            completion_tokens=response.usage.completion_tokens or 0,
            total_tokens=response.usage.total_tokens or 0,
            model=model,
        )

    return response


def _llm_structured_completion_with_retry(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],  # type: ignore[type-arg]  # OpenAI expects ChatCompletionMessageParam, not plain dict[str, str]
    response_format: type,
    temperature: float,
    max_tokens: int,
) -> ParsedChatCompletion:
    """Call ``client.beta.chat.completions.parse`` with exponential-backoff retry.

    Retries on transient OpenAI errors (rate-limit, timeout, connection).
    Non-retryable errors propagate immediately.

    Token usage from the response is automatically recorded in the
    thread-local :class:`_UsageTracker`.
    """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
        reraise=True,
    )
    def _call() -> ParsedChatCompletion:
        return client.beta.chat.completions.parse(
            model=model,
            messages=messages,  # type: ignore[arg-type]  # OpenAI expects ChatCompletionMessageParam, not list[dict[str, str]]
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    response = _call()

    if response.usage is not None:
        _usage_tracker.record(
            prompt_tokens=response.usage.prompt_tokens or 0,
            completion_tokens=response.usage.completion_tokens or 0,
            total_tokens=response.usage.total_tokens or 0,
            model=model,
        )

    return response


# ---------------------------------------------------------------------------
# Structured-output fallback for non-OpenAI providers
# ---------------------------------------------------------------------------


def _get_fallback_structured_errors() -> tuple[type[BaseException], ...]:
    """Return exception types that trigger the structured-output fallback.

    Non-OpenAI providers (DeepSeek, etc.) raise ``AttributeError`` when
    ``client.beta`` does not exist, ``NotImplementedError`` when the
    provider explicitly refuses structured output, or ``openai.APIError``
    when the server rejects the beta endpoint.
    """
    try:
        import openai

        return (AttributeError, NotImplementedError, openai.APIError)
    except ImportError:
        return (AttributeError, NotImplementedError)


_FALLBACK_STRUCTURED_ERRORS: tuple[type[BaseException], ...] = _get_fallback_structured_errors()

# Cache: once a provider fails the beta structured API, skip it on subsequent calls
# to avoid wasting 2-3s per gate on the inevitable 400 response.
_provider_no_beta_api: bool = False


def _structured_completion_with_fallback(
    prompt: str,
    *,
    response_format: type,
    config: dict[str, Any] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    task_type: str = "text_generation",
) -> BaseModel:
    """Try structured completion; fall back to manual JSON parse.

    Attempts the OpenAI ``beta.chat.completions.parse`` endpoint first.
    If the provider does not support structured output (e.g. DeepSeek),
    falls back to :func:`llm_complete` + ``model.model_validate_json``.

    Parameters
    ----------
    prompt:
        The user message content.
    response_format:
        A Pydantic model class that defines the expected JSON schema.
    config:
        Merged AutoMedia config.  Lazily loaded when *None*.
    system_prompt:
        Optional system instruction.
    model:
        Model override (default: from config).
    temperature:
        Sampling temperature override.
    max_tokens:
        Max output token override.
    task_type:
        Config section under ``llm`` to read (e.g. ``text_generation``,
        ``vision``, ``subtitle_proofread``).

    Returns
    -------
    Any
        An instance of *response_format* populated from the LLM response.

    Raises
    ------
    LLMError
        On provider errors or unexpected failures.
    """
    if config is None:
        from automedia.core.config_loader import load_config

        config = load_config()

    llm_cfg = config.get("llm", {}).get(task_type, {})
    client = _build_client(config, task_type=task_type)

    resolved_model: str = model or llm_cfg.get("model", "")
    if not resolved_model:
        raise LLMError(
            f"No model configured for structured output in llm.{task_type}.model. "
            "Set it in ~/.automedia/model_config.yaml or pass model= explicitly."
        )
    resolved_temp: float = (
        temperature if temperature is not None else llm_cfg.get("temperature", 0.7)
    )
    resolved_max: int = max_tokens if max_tokens is not None else llm_cfg.get("max_tokens", 4096)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # Skip beta API entirely if the provider already proved it doesn't support it
    if not _provider_no_beta_api:
        try:
            logger.info("Attempting structured completion via beta API")
            response = _llm_structured_completion_with_retry(
                client,
                model=resolved_model,
                messages=messages,
                response_format=response_format,
                temperature=resolved_temp,
                max_tokens=resolved_max,
            )
            return response.choices[0].message.parsed
        except _FALLBACK_STRUCTURED_ERRORS as exc:
            logger.warning(
                "Structured beta API not supported by provider (%s: %s). "
                "Caching result — falling back for subsequent calls.",
                type(exc).__name__,
                exc,
            )
            _provider_no_beta_api = True
    else:
        logger.info("Skipping beta API (cached — provider does not support structured output)")

    try:
        response = _llm_chat_completion_with_retry(
            client,
            model=resolved_model,
            messages=messages,
            temperature=resolved_temp,
            max_tokens=resolved_max,
        )
    except Exception as exc:
        raise LLMError(f"LLM completion failed during structured fallback: {exc}") from exc

    raw_text: str = response.choices[0].message.content or ""

    try:
        return response_format.model_validate_json(raw_text)  # type: ignore[attr-defined]  # response_format is type; mypy cannot know it's a Pydantic model with model_validate_json
    except Exception as exc:
        raise LLMError(
            f"Failed to parse LLM response as {response_format.__name__}: {exc}"
        ) from exc


def llm_complete_structured_safe(
    prompt: str,
    *,
    response_format: type,
    config: dict[str, Any] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    task_type: str = "text_generation",
) -> BaseModel:
    """Send a structured completion request with automatic fallback.

    Wraps :func:`_structured_completion_with_fallback` to provide a
    public API that works with both OpenAI (native structured output via
    ``beta.chat.completions.parse``) and non-OpenAI providers such as
    DeepSeek (manual JSON parse fallback).

    Parameters
    ----------
    prompt:
        The user message content.
    response_format:
        A Pydantic model class that defines the expected JSON schema.
    config:
        Merged AutoMedia config.  Lazily loaded when *None*.
    system_prompt:
        Optional system instruction.
    model:
        Model override (default: from config).
    temperature:
        Sampling temperature override.
    max_tokens:
        Max output token override.
    task_type:
        Config section under ``llm`` to read (e.g. ``text_generation``,
        ``vision``, ``subtitle_proofread``).

    Returns
    -------
    Any
        An instance of *response_format* populated from the LLM response.

    Raises
    ------
    LLMError
        On provider errors or unexpected failures.
    """
    # Lazy config load (needed for fake-mode check)
    if config is None:
        from automedia.core.config_loader import load_config

        config = load_config()

    if _is_fake_mode(config):
        _warn_fake_once()
        return _fake_structured_response(response_format)

    return _structured_completion_with_fallback(
        prompt,
        response_format=response_format,
        config=config,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        task_type=task_type,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def llm_complete(
    prompt: str,
    *,
    config: dict[str, Any] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    task_type: str = "text_generation",
) -> str:
    """Send a chat-completion request and return the response text.

    Parameters
    ----------
    prompt:
        The user / assistant message content.
    config:
        Merged AutoMedia config.  When *None* the config is loaded lazily
        via :func:`~automedia.core.config_loader.load_config`.
    system_prompt:
        Optional system-level instruction prepended to the conversation.
    model:
        Model identifier override (default: read from config).
    temperature:
        Sampling temperature override (default: read from config).
    max_tokens:
        Max output token override (default: read from config).
    task_type:
        Config section under ``llm`` to read (e.g. ``text_generation``,
        ``vision``, ``subtitle_proofread``).  Defaults to
        ``text_generation``.

    Returns
    -------
    str
        The response content.

    Raises
    ------
    LLMError
        On provider errors, API key missing, or unexpected failures.
    """
    # Lazy config load
    if config is None:
        from automedia.core.config_loader import load_config

        config = load_config()

    if _is_fake_mode(config):
        _warn_fake_once()
        return f"This is a fake LLM response for: {prompt[:80]}..."

    llm_cfg: dict[str, Any] = config.get("llm", {}).get(task_type, {})
    client = _build_client(config, task_type=task_type)

    resolved_model: str = model or llm_cfg.get("model", "")
    if not resolved_model:
        raise LLMError(
            f"No model configured in llm.{task_type}.model. "
            "Set it in ~/.automedia/model_config.yaml or pass model= explicitly."
        )
    resolved_temp: float = (
        temperature if temperature is not None else llm_cfg.get("temperature", 0.7)
    )
    resolved_max: int = max_tokens if max_tokens is not None else llm_cfg.get("max_tokens", 2048)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = _llm_chat_completion_with_retry(
            client,
            model=resolved_model,
            messages=messages,
            temperature=resolved_temp,
            max_tokens=resolved_max,
        )
    except Exception as exc:
        raise LLMError(f"LLM completion failed: {exc}") from exc

    choice = response.choices[0]
    content: str = choice.message.content or ""
    return content


def llm_complete_structured(
    prompt: str,
    *,
    response_format: type,
    config: dict[str, Any] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    task_type: str = "text_generation",
) -> BaseModel:
    """Send a chat-completion request with structured output (JSON schema).

    Uses OpenAI's ``response_format`` parameter with ``json_schema`` type.

    Parameters
    ----------
    prompt:
        The user message content.
    response_format:
        A Pydantic model class (or ``type[BaseModel]``) that defines the
        expected JSON schema.
    config:
        Merged AutoMedia config.  Lazily loaded when *None*.
    system_prompt:
        Optional system instruction.
    model:
        Model override (default: from config).  Must support structured
        output (gpt-4o-mini, gpt-4o, etc.).
    temperature:
        Sampling temperature override.
    max_tokens:
        Max output token override.
    task_type:
        Config section under ``llm`` to read (e.g. ``text_generation``,
        ``vision``, ``subtitle_proofread``).  Defaults to
        ``text_generation``.

    Returns
    -------
    Any
        An instance of *response_format* populated from the LLM response.

    Raises
    ------
    LLMError
        On provider errors or unexpected failures.
    """
    if config is None:
        from automedia.core.config_loader import load_config

        config = load_config()

    if _is_fake_mode(config):
        _warn_fake_once()
        return _fake_structured_response(response_format)

    llm_cfg = config.get("llm", {}).get(task_type, {})
    client = _build_client(config, task_type=task_type)

    resolved_model: str = model or llm_cfg.get("model", "")
    if not resolved_model:
        raise LLMError(
            f"No model configured for structured output in llm.{task_type}.model. "
            "Set it in ~/.automedia/model_config.yaml or pass model= explicitly."
        )
    resolved_temp: float = (
        temperature if temperature is not None else llm_cfg.get("temperature", 0.7)
    )
    resolved_max: int = max_tokens if max_tokens is not None else llm_cfg.get("max_tokens", 4096)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = _llm_structured_completion_with_retry(
            client,
            model=resolved_model,
            messages=messages,
            response_format=response_format,
            temperature=resolved_temp,
            max_tokens=resolved_max,
        )
    except Exception as exc:
        raise LLMError(f"LLM structured completion failed: {exc}") from exc

    return response.choices[0].message.parsed
