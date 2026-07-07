"""LLM client — unified interface for text-generation providers.

Supports OpenAI-compatible APIs (OpenAI, Azure, Ollama, etc.).
Config is read from the merged AutoMedia config dict at call time.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from automedia.core.credential_loader import resolve_api_key


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Raised when the LLM provider returns an error or is unreachable."""


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def _build_client(config: dict[str, Any]) -> OpenAI:
    """Build an ``openai.OpenAI`` client from *config*.

    Reads ``llm.text_generation`` from *config* and resolves the API key
    via :func:`~automedia.core.credential_loader.resolve_api_key`.

    Parameters
    ----------
    config:
        The merged AutoMedia configuration dict.

    Returns
    -------
    openai.OpenAI
        A configured OpenAI client instance.

    Raises
    ------
    LLMError
        If no API key can be resolved.
    """
    llm_cfg: dict[str, Any] = config.get("llm", {}).get("text_generation", {})
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

    llm_cfg: dict[str, Any] = config.get("llm", {}).get("text_generation", {})
    client = _build_client(config)

    resolved_model: str = model or llm_cfg.get("model", "") or "gpt-4o"
    resolved_temp: float = temperature if temperature is not None else llm_cfg.get("temperature", 0.7)
    resolved_max: int = max_tokens if max_tokens is not None else llm_cfg.get("max_tokens", 2048)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
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
) -> Any:
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

    llm_cfg = config.get("llm", {}).get("text_generation", {})
    client = _build_client(config)

    resolved_model: str = model or llm_cfg.get("model", "") or "gpt-4o-mini"
    resolved_temp: float = temperature if temperature is not None else llm_cfg.get("temperature", 0.7)
    resolved_max: int = max_tokens if max_tokens is not None else llm_cfg.get("max_tokens", 4096)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.beta.chat.completions.parse(
            model=resolved_model,
            messages=messages,
            response_format=response_format,
            temperature=resolved_temp,
            max_tokens=resolved_max,
        )
    except Exception as exc:
        raise LLMError(f"LLM structured completion failed: {exc}") from exc

    return response.choices[0].message.parsed
