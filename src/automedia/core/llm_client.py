"""LLM client — unified interface for text-generation providers.

Supports OpenAI-compatible APIs (OpenAI, Azure, Ollama, etc.).
Config is read from the merged AutoMedia config dict at call time.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING, Any, TypeVar, cast

from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from automedia.core.credential_loader import resolve_api_key
from automedia.core.env_overlay import env_lookup
from automedia.core.json_tolerance import repair_json_text, salvage_fields
from automedia.exceptions import AutoMediaError

# Underscore-prefixed aliases keep the private naming convention used inside
# this module and in tests.
_repair_json_text = repair_json_text
_salvage_fields = salvage_fields

if TYPE_CHECKING:
    from openai import OpenAI
    from openai.types.chat import ChatCompletion, ParsedChatCompletion


# Pydantic schema type bound for the structured-completion helpers.
_ModelT = TypeVar("_ModelT", bound=BaseModel)


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
    1. ``AUTOMEDIA_FAKE_LLM`` environment variable (fast, primary mechanism);
       a ``.env`` value is honoured here too, but never above a real env var.
    2. ``llm.fake_mode: true`` in the merged config file (fallback for
       environments where env vars are not practical, e.g. compound shell
       commands, container entrypoints, or systemd services).
    """
    if env_lookup("AUTOMEDIA_FAKE_LLM", "").lower() in {"1", "true", "yes"}:
        return True
    if config is not None:
        return bool(config.get("llm", {}).get("fake_mode", False))
    return False


def _warn_fake_once() -> None:
    """Emit a one-time warning that fake LLM mode is active."""
    global _fake_llm_warned
    if not _fake_llm_warned:
        logger.warning("AUTOMEDIA_FAKE_LLM=1 active — returning deterministic mock responses")
        _fake_llm_warned = True


def _fake_structured_response(response_format: type[_ModelT]) -> _ModelT:
    """Return a deterministic canned instance of *response_format*.

    Known gate result types receive realistic-looking data.  All others
    receive a minimal ``{"passed": True}`` (or the closest valid variant).
    """
    _dispatch: dict[str, dict[str, object]] = {
        "G0CheckResult": {"passed": True, "confidence": 0.95},
        "G1CheckResult": {"passed": True, "score": 0.85, "humanized": True, "changes": []},
        "G2CheckResult": {"passed": True, "issues": [], "score": 0.9},
    }
    name = response_format.__name__
    if name in _dispatch:
        return response_format.model_validate(_dispatch[name])
    try:
        return response_format.model_validate({"passed": True})
    except Exception:
        # Last resort: construct with zero-valued fields
        return response_format.model_construct(passed=True)


# Fixed body returned by the plain-text fake-LLM path.  It is deliberately
# substantial (well above the 500-byte floor the validation journeys assert)
# and contains no randomness, clock, or machine state, so repeated calls with
# the same prompt are byte-identical.
_FAKE_TEXT_BODY = """\
# Deterministic draft

This draft was produced by AutoMedia's fake-LLM mode (`AUTOMEDIA_FAKE_LLM=1`).
It is a fixed, self-contained placeholder that lets the full production
pipeline and the agent-tester validation journeys run end to end without
contacting a live model provider. Nothing in it is random and nothing depends
on the clock, so the same request always yields byte-identical output.

## Why this document is intentionally long

Downstream consumers assert that the content-writing gate hands the director a
non-trivial artifact rather than a stub. The copy gates, the lifecycle gates,
and the validation journeys all read this draft, and the journeys in
particular refuse a file smaller than five hundred bytes. A short placeholder
would prove the plumbing while hiding a broken content path, so this body
carries several paragraphs of structured prose and comfortably clears that
floor while staying small enough to keep test runs fast.

## How the pipeline uses it

1. The content-writing gate receives this text and writes it to `01_content/drafts/`.
2. The copy gates from G0 through G6 inspect the draft for tone, factuality, and brand fit.
3. The lifecycle gates from L1 through L4 record the run and its produced artifacts.
4. The validation engine grades each step and persists an immutable run record.

## Determinism guarantee

Because the body above never varies, two runs of the same scenario produce the
same draft bytes, which makes the validation record reproducible. When a test
needs richer content it injects its own fixture; this text exists only to keep
the shipped fake path honest and exerciseable.

## Prompt echo

The request that produced this response follows verbatim:

{prompt}
"""


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
    provider_spec: dict[str, Any] | None = None,
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
    provider_spec:
        Optional per-provider spec (used by the fallback chain).  When
        given, overrides the ``llm.<task_type>`` block for provider,
        model, base_url and api_key.

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
    if provider_spec is not None:
        llm_cfg = provider_spec
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
# Provider fallback chain
# ---------------------------------------------------------------------------


def _iter_provider_specs(
    config: dict[str, Any],
    task_type: str,
) -> list[dict[str, Any]]:
    """Return the provider chain for *task_type* as a list of specs.

    The first element is the primary ``llm.<task_type>`` block; any
    ``fallback:`` list entries (each an independent provider spec with
    provider/model/base_url/api_key) follow in order.  An empty list
    means no usable configuration.

    Fallback entries inherit fields from the primary block, so a fallback
    may override only ``provider``/``model``/``base_url`` and keep the
    primary's temperature/max_tokens.

    A field explicitly set to an empty value (``""`` or ``None``) in a
    fallback entry is treated as *not provided* and does not override the
    primary's value.  Without this, an empty ``api_key: ''`` placeholder
    would silently wipe the primary key and the fallback would only fail
    once the chain actually reached it.

    We deliberately stop here: this only skips empty overrides.  We do
    **not** add extra logic to fall back to the primary's key on a spec
    that has no key at all — primary and fallback may use different
    providers/base_urls, and sharing A's key with B would yield a 401.
    """
    llm_cfg: dict[str, Any] = config.get("llm", {}).get(task_type, {})
    if not isinstance(llm_cfg, dict) or not llm_cfg:
        return []
    primary = {k: v for k, v in llm_cfg.items() if k != "fallback"}
    chain: list[dict[str, Any]] = [primary]
    fallbacks = llm_cfg.get("fallback", [])
    if isinstance(fallbacks, list):
        for fb in fallbacks:
            if isinstance(fb, dict) and fb.get("provider"):
                merged = dict(primary)
                merged.update(
                    {k: v for k, v in fb.items() if k != "fallback" and v not in ("", None)}
                )
                chain.append(merged)
    return chain


def _retryable_fallback_errors() -> tuple[type[BaseException], ...]:
    """Exception types that justify switching to the next provider.

    Provider-unavailable errors (rate limit, timeout, connection,
    auth/API errors) mean the current provider is unusable for this
    request — move down the chain.  ``LLMError`` is included because
    ``llm_complete*`` wrap low-level errors in it; local configuration
    errors (missing model) also surface as LLMError.
    """
    try:
        import openai

        return (LLMError, openai.APIError, openai.APITimeoutError, openai.APIConnectionError)
    except ImportError:
        return (LLMError,)


_FALLBACK_ERRORS: tuple[type[BaseException], ...] = _retryable_fallback_errors()


def _should_try_next_provider(exc: BaseException) -> bool:
    """Whether *exc* should trigger the next provider in the chain."""
    return isinstance(exc, _FALLBACK_ERRORS)


# ---------------------------------------------------------------------------
# Retryable wrappers (private)
# ---------------------------------------------------------------------------


def _llm_chat_completion_with_retry(
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],  # type: ignore[type-arg]  # OpenAI expects ChatCompletionMessageParam, not plain dict[str, str]
    temperature: float,
    max_tokens: int,
    response_format: dict[str, str] | None = None,
    max_attempts: int = 3,
) -> ChatCompletion:
    """Call ``client.chat.completions.create`` with exponential-backoff retry.

    Retries on transient OpenAI errors (rate-limit, timeout, connection).
    Non-retryable errors propagate immediately.

    Token usage from the response is automatically recorded in the
    thread-local :class:`_UsageTracker`.

    Parameters
    ----------
    response_format:
        Optional ``response_format`` dict (e.g. ``{"type": "json_object"}``)
        passed to the provider.  Structured-output fallback paths use this to
        nudge providers that accept ``json_object`` mode.
    max_attempts:
        Total number of calls to ``create`` per provider, including the first.
        Callers that need a hard wall-clock bound (the bounded doctor probe)
        pass ``1`` so a hanging host cannot consume ``max_attempts`` timeouts.
    """

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
        reraise=True,
    )
    def _call() -> ChatCompletion:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,  # type: ignore[arg-type]  # OpenAI expects ChatCompletionMessageParam, not list[dict[str, str]]
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        return client.chat.completions.create(**kwargs)

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
# Keyed by provider so the fallback chain can switch to a provider that
# DOES support structured output even when the primary does not.
_provider_no_beta_api: dict[str, bool] = {}


def _strip_markdown_fence(raw_text: str) -> str:
    """Strip a markdown code fence (````` ```json ... ``` `````) from LLM output.

    Some providers (e.g. bigmodel.cn GLM) return 200 OK from the
    ``beta.chat.completions.parse`` endpoint but ignore the requested schema
    and wrap the JSON payload in a markdown code fence.  Pydantic's
    ``model_validate_json`` rejects fenced text, so strip a leading
    `` ```json`` / `` ``` `` line and the trailing `` ``` `` line before
    parsing.

    Parameters
    ----------
    raw_text:
        The raw LLM response text, possibly fenced.

    Returns
    -------
    str
        The text with a single surrounding markdown code fence removed, when
        present; otherwise the input unchanged (whitespace-trimmed).
    """
    text = raw_text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


# Maximum number of characters of the bad output echoed back to the model
# during a one-shot repair call.  Keeps the repair prompt bounded.
_REPAIR_ECHO_LIMIT = 1500


def _format_validation_error(exc: ValidationError) -> str:
    """Render a pydantic ``ValidationError`` as a compact, field-named string."""
    parts: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ())) or "<root>"
        parts.append(f"{loc}: {error.get('msg', 'validation error')}")
    return "; ".join(parts) if parts else str(exc)


def _mark_invalid_fields(instance: BaseModel, invalid_fields: list[str]) -> None:
    """Attach ``_invalid_fields`` to *instance* when its model allows extras."""
    if not invalid_fields:
        return
    if type(instance).model_config.get("extra") != "allow":
        return
    try:
        attr_name = "_invalid_fields"
        setattr(instance, attr_name, list(invalid_fields))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("could not record _invalid_fields on %s: %s", type(instance).__name__, exc)


def _tolerant_validate(
    model_cls: type[_ModelT],
    raw_text: str,
) -> tuple[_ModelT | None, list[str], str | None]:
    """Repair, parse and salvage *raw_text* into *model_cls*.

    Returns ``(instance, invalid_fields, error_detail)``:

    * *instance* is the validated model, or ``None`` when parsing/validation
      could not be saved by field-level salvage;
    * *invalid_fields* lists fields that were nulled/dropped;
    * *error_detail* describes the remaining failure (``None`` on success).
    """
    text = repair_json_text(raw_text)
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, [], f"invalid JSON: {exc}"

    if not isinstance(payload, (dict, list)):
        try:
            return model_cls.model_validate(payload), [], None
        except ValidationError as exc:
            return None, [], _format_validation_error(exc)

    try:
        return model_cls.model_validate(payload), [], None
    except ValidationError as first_error:
        salvaged, invalid_fields = salvage_fields(model_cls, payload)
        if not invalid_fields:
            return None, [], _format_validation_error(first_error)
        try:
            instance = model_cls.model_validate(salvaged)
        except ValidationError as exc:
            return None, invalid_fields, _format_validation_error(exc)
        _mark_invalid_fields(instance, invalid_fields)
        return instance, invalid_fields, None


def _build_repair_instruction(bad_text: str, error_detail: str) -> str:
    """Build the user message that asks the model to fix its own JSON."""
    echoed = (bad_text or "").strip()
    if len(echoed) > _REPAIR_ECHO_LIMIT:
        echoed = echoed[:_REPAIR_ECHO_LIMIT] + "…[truncated]"
    return (
        "The previous response could not be parsed as JSON matching the "
        "required schema.\n"
        f"Validation error: {error_detail}\n"
        "Previous (invalid) output:\n"
        f"{echoed}\n\n"
        "Return ONLY the corrected JSON object. Do not include explanations, "
        "commentary, or markdown code fences."
    )


def _attempt_structured_repair(
    *,
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],  # type: ignore[type-arg]
    temperature: float,
    max_tokens: int,
    bad_text: str,
    error_detail: str,
) -> str:
    """Make the single allowed repair call, returning the new raw text.

    The call uses the same provider spec (same client/model/temperature/
    limits) as the original request — never a different provider tier.
    """
    repair_messages = list(messages)
    repair_messages.append(
        {"role": "user", "content": _build_repair_instruction(bad_text, error_detail)}
    )
    try:
        response = _llm_chat_completion_with_retry(
            client,
            model=model,
            messages=repair_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
    except _FALLBACK_STRUCTURED_ERRORS:
        response = _llm_chat_completion_with_retry(
            client,
            model=model,
            messages=repair_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return response.choices[0].message.content or ""


def _parse_structured_with_repair(
    *,
    response_format: type[_ModelT],
    raw_text: str,
    client: OpenAI,
    model: str,
    messages: list[dict[str, str]],  # type: ignore[type-arg]
    temperature: float,
    max_tokens: int,
) -> _ModelT:
    """Parse *raw_text* tolerantly, with at most one repair call on failure."""
    instance, invalid_fields, error_detail = _tolerant_validate(response_format, raw_text)
    if instance is not None:
        if invalid_fields:
            logger.warning(
                "structured output for %s salvaged; invalid_fields=%s",
                response_format.__name__,
                invalid_fields,
            )
        return instance

    logger.warning(
        "structured output for %s failed validation (invalid_fields=%s): %s — "
        "attempting one repair call",
        response_format.__name__,
        invalid_fields,
        error_detail,
    )
    repaired_text = _attempt_structured_repair(
        client=client,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        bad_text=raw_text,
        error_detail=error_detail or "unknown validation error",
    )
    repaired_instance, repaired_invalid, repaired_detail = _tolerant_validate(
        response_format, repaired_text
    )
    if repaired_instance is not None:
        logger.info(
            "structured output for %s recovered after one repair call (salvaged_fields=%s)",
            response_format.__name__,
            sorted(set(invalid_fields) | set(repaired_invalid)),
        )
        if repaired_invalid:
            logger.warning(
                "structured output for %s salvaged after repair; invalid_fields=%s",
                response_format.__name__,
                repaired_invalid,
            )
        return repaired_instance

    bad_fields = sorted(set(invalid_fields) | set(repaired_invalid))
    raise LLMError(
        f"Failed to parse LLM response as {response_format.__name__} after one "
        f"repair attempt; invalid/missing fields: {bad_fields or ['<unknown>']}: "
        f"{repaired_detail or error_detail}"
    )


def _structured_completion_with_fallback(
    prompt: str,
    *,
    response_format: type[_ModelT],
    config: dict[str, Any] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    task_type: str = "text_generation",
) -> _ModelT:
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
    global _provider_no_beta_api  # module-level cache mutated deliberately

    if config is None:
        from automedia.core.config_loader import load_config

        config = load_config()

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    specs = _iter_provider_specs(config, task_type)
    if not specs:
        raise LLMError(
            f"No LLM provider configured in llm.{task_type}. "
            "Set it in ~/.automedia/model_config.yaml or pass model= explicitly."
        )

    errors: list[str] = []
    for spec in specs:
        provider_key: str = spec.get("provider", "openai") or "openai"
        try:
            client = _build_client(config, task_type=task_type, provider_spec=spec)
            resolved_model: str = model or spec.get("model", "")
            if not resolved_model:
                raise LLMError(
                    f"No model configured for structured output in llm.{task_type}.model. "
                    "Set it in ~/.automedia/model_config.yaml or pass model= explicitly."
                )
            resolved_temp: float = (
                temperature if temperature is not None else spec.get("temperature", 0.7)
            )
            resolved_max: int = (
                max_tokens if max_tokens is not None else spec.get("max_tokens", 4096)
            )

            # Skip beta API entirely if the provider already proved it doesn't support it
            response: ChatCompletion | ParsedChatCompletion | None = None
            if not _provider_no_beta_api.get(provider_key, False):
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
                    try:
                        return cast(_ModelT, response.choices[0].message.parsed)
                    except ValidationError:
                        # Lazy-parse SDKs raise here.  Fall through to the manual
                        # parse path, which reuses the response content and strips
                        # markdown fences.
                        logger.warning(
                            "Beta structured completion returned content that failed "
                            "schema validation (%s) — falling back to manual JSON parse.",
                            response_format.__name__,
                        )
                except ValidationError:
                    # openai >=2.0 parses eagerly inside parse(): the SDK raises
                    # ValidationError for fenced/non-schema JSON before returning.
                    # Cache the skip — a provider that ignores the schema contract
                    # (e.g. bigmodel.cn) will fail identically on every call.
                    logger.warning(
                        "Beta structured completion returned content that failed "
                        "schema validation (%s) — caching skip, falling back to "
                        "manual JSON parse.",
                        response_format.__name__,
                    )
                    _provider_no_beta_api[provider_key] = True
                except _FALLBACK_STRUCTURED_ERRORS as exc:
                    logger.warning(
                        "Structured beta API not supported by provider (%s: %s). "
                        "Caching result — falling back for subsequent calls.",
                        type(exc).__name__,
                        exc,
                    )
                    _provider_no_beta_api[provider_key] = True
            else:
                logger.info(
                    "Skipping beta API (cached — provider does not support structured output)"
                )

            if response is None:
                try:
                    response = _llm_chat_completion_with_retry(
                        client,
                        model=resolved_model,
                        messages=messages,
                        temperature=resolved_temp,
                        max_tokens=resolved_max,
                        response_format={"type": "json_object"},
                    )
                except _FALLBACK_STRUCTURED_ERRORS:
                    # Provider may reject json_object mode (e.g. OpenAI requires the
                    # word "json" in the prompt; some providers refuse it outright).
                    # Retry once without the format constraint.
                    logger.warning(
                        "Provider rejected response_format=json_object — retrying "
                        "without the format constraint."
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
                except Exception as exc:
                    raise LLMError(
                        f"LLM completion failed during structured fallback: {exc}"
                    ) from exc

            raw_text: str = response.choices[0].message.content or ""

            return _parse_structured_with_repair(
                response_format=response_format,
                raw_text=raw_text,
                client=client,
                model=resolved_model,
                messages=messages,
                temperature=resolved_temp,
                max_tokens=resolved_max,
            )
        except Exception as exc:
            errors.append(f"{provider_key}: {exc}")
            logger.warning(
                "structured completion provider %r failed (%s); %d provider(s) remaining",
                provider_key,
                exc,
                len(specs) - len(errors),
            )
            if not _should_try_next_provider(exc):
                raise
            continue

    raise LLMError(
        f"LLM structured completion failed for all {len(specs)} provider(s): " + "; ".join(errors)
    )


def llm_complete_structured_safe(
    prompt: str,
    *,
    response_format: type[_ModelT],
    config: dict[str, Any] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    task_type: str = "text_generation",
) -> _ModelT:
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
    timeout: float | None = None,
    max_attempts: int = 3,
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
    timeout:
        Optional per-request timeout in seconds.  When *None* (the default)
        the OpenAI SDK's own default timeout is left untouched — passing
        ``None`` to ``with_options`` would *disable* that default, so
        ``with_options`` is only called when a value is supplied.  When set,
        the SDK's transparent retries are also disabled so the timeout bounds
        the entire call, not each internal attempt.
    max_attempts:
        Total attempts per provider spec for transient errors
        (default 3).  Pass ``1`` for a hard wall-clock bound; the walk over
        the provider-spec chain still continues to the next spec on failure.

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
        return _FAKE_TEXT_BODY.format(prompt=prompt)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    specs = _iter_provider_specs(config, task_type)
    if not specs:
        raise LLMError(
            f"No LLM provider configured in llm.{task_type}. "
            "Set it in ~/.automedia/model_config.yaml or pass model= explicitly."
        )

    errors: list[str] = []
    for spec in specs:
        spec_provider: str = spec.get("provider", "openai") or "openai"
        try:
            client = _build_client(config, task_type=task_type, provider_spec=spec)
            if timeout is not None:
                # Bound the entire request.  ``max_retries=0`` disables the
                # SDK's own transparent retries (default 2); without it a 15s
                # socket timeout still costs up to 3x as the SDK retries.
                client = client.with_options(timeout=timeout, max_retries=0)
            resolved_model: str = model or spec.get("model", "")
            if not resolved_model:
                raise LLMError(
                    f"No model configured in llm.{task_type}.model. "
                    "Set it in ~/.automedia/model_config.yaml or pass model= explicitly."
                )
            resolved_temp: float = (
                temperature if temperature is not None else spec.get("temperature", 0.7)
            )
            resolved_max: int = (
                max_tokens if max_tokens is not None else spec.get("max_tokens", 2048)
            )

            response = _llm_chat_completion_with_retry(
                client,
                model=resolved_model,
                messages=messages,
                temperature=resolved_temp,
                max_tokens=resolved_max,
                max_attempts=max_attempts,
            )
            choice = response.choices[0]
            content: str = choice.message.content or ""
            return content
        except Exception as exc:
            errors.append(f"{spec_provider}: {exc}")
            logger.warning(
                "llm_complete provider %r failed (%s); %d provider(s) remaining",
                spec_provider,
                exc,
                len(specs) - len(errors),
            )
            if not _should_try_next_provider(exc):
                raise LLMError(f"LLM completion failed: {exc}") from exc
            continue

    raise LLMError(f"LLM completion failed for all {len(specs)} provider(s): " + "; ".join(errors))


def llm_complete_structured(
    prompt: str,
    *,
    response_format: type[_ModelT],
    config: dict[str, Any] | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    task_type: str = "text_generation",
) -> _ModelT:
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

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    specs = _iter_provider_specs(config, task_type)
    if not specs:
        raise LLMError(
            f"No LLM provider configured in llm.{task_type}. "
            "Set it in ~/.automedia/model_config.yaml or pass model= explicitly."
        )

    errors: list[str] = []
    for spec in specs:
        spec_provider: str = spec.get("provider", "openai") or "openai"
        try:
            client = _build_client(config, task_type=task_type, provider_spec=spec)
            resolved_model: str = model or spec.get("model", "")
            if not resolved_model:
                raise LLMError(
                    f"No model configured for structured output in llm.{task_type}.model. "
                    "Set it in ~/.automedia/model_config.yaml or pass model= explicitly."
                )
            resolved_temp: float = (
                temperature if temperature is not None else spec.get("temperature", 0.7)
            )
            resolved_max: int = (
                max_tokens if max_tokens is not None else spec.get("max_tokens", 4096)
            )

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

            try:
                return cast(_ModelT, response.choices[0].message.parsed)
            except ValidationError:
                # Provider returned 200 OK but ignored the schema (e.g. fenced JSON) —
                # retry against the raw content with tolerance repairs.
                raw_text: str = response.choices[0].message.content or ""
                instance, invalid_fields, error_detail = _tolerant_validate(
                    response_format, raw_text
                )
                if instance is not None:
                    return instance
                raise LLMError(
                    f"Failed to parse LLM response as {response_format.__name__}; "
                    f"invalid/missing fields: {invalid_fields or ['<unknown>']}: "
                    f"{error_detail}"
                ) from None
        except Exception as exc:
            errors.append(f"{spec_provider}: {exc}")
            logger.warning(
                "llm_complete_structured provider %r failed (%s); %d provider(s) remaining",
                spec_provider,
                exc,
                len(specs) - len(errors),
            )
            if not _should_try_next_provider(exc):
                raise LLMError(f"LLM structured completion failed: {exc}") from exc
            continue

    raise LLMError(
        f"LLM structured completion failed for all {len(specs)} provider(s): " + "; ".join(errors)
    )
