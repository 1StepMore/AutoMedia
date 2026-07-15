"""LLM evaluation helpers for gates with deterministic fallback.

Provides :func:`llm_check_with_fallback` — a unified entry point for
G0 (fact-check) and G2 (copy-review) gates that attempts an LLM-based
evaluation first, then falls back to a deterministic function on any failure.

Usage
-----
>>> from automedia.gates.llm_helpers import llm_check_with_fallback
>>> result = llm_check_with_fallback(
...     text="Some content to check",
...     check_type="fact_check",
...     prompt_template_name="g0_fact_check",
...     deterministic_fn=my_deterministic_check,
... )
>>> result["method"]  # "llm" or "deterministic"
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, TypedDict

from pydantic import BaseModel, Field

from automedia.core.llm_client import llm_complete_structured_safe
from automedia.prompts import load_prompt

logger = logging.getLogger(__name__)


class LLMCheckResult(TypedDict, total=False):
    """Result dict produced by :func:`llm_check_with_fallback`.

    ``passed``, ``issues``, and ``method`` are always present.
    ``confidence`` (G0/G1), ``tone_score`` (G2), and
    ``brand_compliance`` (G2) are model-specific extras.
    """

    passed: bool
    issues: list[str]
    method: str
    confidence: float
    tone_score: float
    brand_compliance: bool


class DeepCheckOutput(TypedDict, total=False):
    """Result dict produced by :func:`run_deep_check`."""

    passed: bool
    issues: list[str]
    method: str


# ---------------------------------------------------------------------------
# Counters for monitoring LLM vs fallback ratio
# ---------------------------------------------------------------------------

_llm_success_count: int = 0
_fallback_count: int = 0


# ---------------------------------------------------------------------------
# Pydantic models for structured LLM output
# ---------------------------------------------------------------------------


class G0CheckResult(BaseModel):
    """Structured output model for G0 (fact-check) LLM evaluation."""

    passed: bool
    issues: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class G2CheckResult(BaseModel):
    """Structured output model for G2 (copy-review) LLM evaluation."""

    passed: bool
    issues: list[str] = Field(default_factory=list)
    tone_score: float = 1.0
    brand_compliance: bool = True


class G1CheckResult(BaseModel):
    """Structured output model for G1 (humanizer) LLM evaluation."""

    passed: bool
    issues: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class DeepCheckResult(BaseModel):
    """Structured output model for optional deep-check LLM evaluation.

    Used by G3, V3, L3, and pre-gate for advisory-only LLM checks
    that never block the gate.
    """

    passed: bool
    issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result type mapping
# ---------------------------------------------------------------------------

_RESULT_MODELS: dict[str, type[BaseModel]] = {
    "fact_check": G0CheckResult,
    "copy_review": G2CheckResult,
    "humanizer": G1CheckResult,
    "deep_check": DeepCheckResult,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def llm_check_with_fallback(
    text: str,
    check_type: str,
    prompt_template_name: str,
    deterministic_fn: Callable[[str], LLMCheckResult],
    timeout: int = 30,
    **kwargs: Any,  # noqa: ANN401  — passthrough to LLM call
) -> LLMCheckResult:
    """Run an LLM-based check with deterministic fallback.

    Attempts to evaluate *text* using an LLM with structured output.
    If the LLM call fails (timeout, API error, parse error), falls back
    to *deterministic_fn*.

    Parameters
    ----------
    text:
        The content to evaluate.
    check_type:
        Either ``"fact_check"`` (G0), ``"copy_review"`` (G2), or
        ``"humanizer"`` (G1).
    prompt_template_name:
        Name of the Jinja2 prompt template (without ``.j2`` extension).
    deterministic_fn:
        Fallback function that takes *text* and returns a dict with
        ``passed`` (bool) and ``issues`` (list[str]) keys.
    timeout:
        Maximum seconds to wait for the LLM response. Defaults to 30.
    **kwargs:
        Additional template variables passed to :func:`load_prompt`.

    Returns
    -------
    dict[str, Any]
        A dict with keys:

        - ``passed``: bool — whether the check passed
        - ``issues``: list[str] — list of issues found
        - ``method``: str — ``"llm"`` or ``"deterministic"``
        - ``confidence``: float (G0 / G1) — confidence score
        - ``tone_score``: float (G2 only) — tone quality score
        - ``brand_compliance``: bool (G2 only) — brand compliance flag
    """
    global _llm_success_count, _fallback_count

    result_model = _RESULT_MODELS.get(check_type)
    if result_model is None:
        raise ValueError(
            f"Unknown check_type {check_type!r}. "
            f"Expected one of: {list(_RESULT_MODELS)}"
        )

    # --- Attempt LLM evaluation ---
    try:
        prompt = load_prompt(prompt_template_name, content=text, **kwargs)

        # Run LLM call in a thread with timeout
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                llm_complete_structured_safe,
                prompt,
                response_format=result_model,
            )
            result = future.result(timeout=timeout)

        # Build success response
        response: LLMCheckResult = {
            "passed": result.passed,
            "issues": result.issues,
            "method": "llm",
        }

        # Add model-specific fields
        if isinstance(result, (G0CheckResult, G1CheckResult)):
            response["confidence"] = result.confidence
        elif isinstance(result, G2CheckResult):
            response["tone_score"] = result.tone_score
            response["brand_compliance"] = result.brand_compliance

        _llm_success_count += 1
        logger.info(
            "LLM check succeeded for %s (total: llm=%d, fallback=%d)",
            check_type,
            _llm_success_count,
            _fallback_count,
        )
        return response

    except FutureTimeoutError:
        _fallback_count += 1
        logger.warning(
            "LLM check timed out for %s after %ds, falling back to deterministic",
            check_type,
            timeout,
        )
    except Exception as exc:
        _fallback_count += 1
        logger.warning(
            "LLM check failed for %s, falling back to deterministic: %s",
            check_type,
            exc,
        )

    # --- Fallback to deterministic function ---
    det_result = deterministic_fn(text)
    det_result["method"] = "deterministic"

    logger.info(
        "Deterministic fallback used for %s (total: llm=%d, fallback=%d)",
        check_type,
        _llm_success_count,
        _fallback_count,
    )
    return det_result


# ---------------------------------------------------------------------------
# Deep-check helper (advisory-only, never blocks the gate)
# ---------------------------------------------------------------------------


def run_deep_check(
    text: str,
    check_description: str,
    timeout: int = 15,
) -> DeepCheckOutput:
    """Run an advisory LLM deep-check on gate content.

    This is optional and never blocks the gate.  Returns a dict with
    ``passed``, ``issues``, and ``method`` keys.

    Parameters
    ----------
    text:
        The content to evaluate by the LLM.
    check_description:
        Short description for the LLM prompt
        (e.g. ``"brand and CTA compliance"``).
    timeout:
        Maximum seconds to wait for the LLM response.  Defaults to 15.

    Returns
    -------
    dict[str, Any]
        A dict with keys:

        - ``passed``: bool — whether the check passed
        - ``issues``: list[str] — list of issues found (empty when passed)
        - ``method``: str — ``"llm"`` on success, ``"failed"`` on error
    """
    prompt = f"Review this content for {check_description}:\n\n{text}"
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                llm_complete_structured_safe,
                prompt,
                response_format=DeepCheckResult,
                system_prompt=(
                    "You are a content quality reviewer. "
                    "Identify any issues in the content."
                ),
            )
            result = future.result(timeout=timeout)
        return {
            "passed": result.passed,
            "issues": result.issues,
            "method": "llm",
        }
    except Exception:
        logger.debug("LLM deep-check failed (advisory, suppressed)", exc_info=True)
        return {
            "passed": True,
            "issues": [],
            "method": "failed",
        }
