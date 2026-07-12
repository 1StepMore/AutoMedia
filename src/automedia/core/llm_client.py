"""LLM client — unified interface for text-generation providers.

Supports OpenAI-compatible APIs (OpenAI, Azure, Ollama, etc.).
Config is read from the merged AutoMedia config dict at call time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from automedia.core.credential_loader import resolve_api_key

if TYPE_CHECKING:
    from openai import OpenAI


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
# Exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
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
    messages: list[dict[str, str]],  # type: ignore[type-arg]
    temperature: float,
    max_tokens: int,
) -> Any:  # noqa: ANN401 — LLM response type varies by provider
    """Call ``client.chat.completions.create`` with exponential-backoff retry.

    Retries on transient OpenAI errors (rate-limit, timeout, connection).
    Non-retryable errors propagate immediately.
    """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
        reraise=True,
    )
    def _call() -> Any:  # noqa: ANN401 — inner retry helper
        return client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )

    return _call()


def _llm_structured_completion_with_retry(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],  # type: ignore[type-arg]
    response_format: type,
    temperature: float,
    max_tokens: int,
) -> Any:  # noqa: ANN401 — LLM response type varies by provider
    """Call ``client.beta.chat.completions.parse`` with exponential-backoff retry.

    Retries on transient OpenAI errors (rate-limit, timeout, connection).
    Non-retryable errors propagate immediately.
    """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
        reraise=True,
    )
    def _call() -> Any:  # noqa: ANN401 — inner retry helper
        return client.beta.chat.completions.parse(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    return _call()


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


_FALLBACK_STRUCTURED_ERRORS: tuple[type[BaseException], ...] = (
    _get_fallback_structured_errors()
)


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
) -> Any:  # noqa: ANN401
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
    resolved_max: int = (
        max_tokens if max_tokens is not None else llm_cfg.get("max_tokens", 4096)
    )

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

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
        logger.info(
            "Structured beta API not supported by provider (%s: %s). "
            "Falling back to manual JSON parse.",
            type(exc).__name__,
            exc,
        )

    try:
        response = _llm_chat_completion_with_retry(
            client,
            model=resolved_model,
            messages=messages,
            temperature=resolved_temp,
            max_tokens=resolved_max,
        )
    except Exception as exc:
        raise LLMError(
            f"LLM completion failed during structured fallback: {exc}"
        ) from exc

    raw_text: str = response.choices[0].message.content or ""

    try:
        return response_format.model_validate_json(raw_text)
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
) -> Any:  # noqa: ANN401
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
) -> Any:  # noqa: ANN401 — LLM response type varies
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
