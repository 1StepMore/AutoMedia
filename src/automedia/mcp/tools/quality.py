"""Content quality evaluation MCP tool handler."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from automedia.core.llm_client import LLMError
from automedia.mcp.tools._shared import (
    MCPErrorCode,
    ResearchPattern,
    error_response,
    success_response,
    validation_error_response,
)


def evaluate_content_quality(
    content: str,
    criteria: str = "general",
    brand: str = "",
    pattern: ResearchPattern = "b",
    platform: str = "",
) -> dict[str, Any]:
    """Evaluate content quality using an LLM with structured output.

    Uses the ``content_quality.j2`` prompt template in combination with
    ``ContentQualityOutput`` Pydantic model to produce a scored evaluation
    with issues, suggestions, and an overall assessment.

    Parameters
    ----------
    content:
        The content text to evaluate.
    criteria:
        Quality dimensions to evaluate — e.g. ``"general"``,
        ``"clarity, accuracy, brand voice, SEO readiness"``.
    brand:
        Optional brand identifier for brand-specific evaluation.
    pattern:
        When ``"a"``, return raw input data without calling the LLM.
        When ``"b"`` (default), use the LLM as usual.
    platform:
        Optional platform name for platform-specific prompt variants.
        When provided and a platform-specific prompt exists (e.g.
        ``platforms/wechat/content_quality.j2``), that variant is used
        instead of the generic ``content_quality.j2``.  When empty
        (default), the generic prompt is used.

    Returns
    -------
    dict
        ``{"quality_score": float, "issues": list[str],
        "suggestions": list[str], "overall_assessment": str}``
        or an error dict on failure.
    """
    if pattern == "a":
        return success_response(
            {
                "quality_score": 0.5,
                "note": "pattern_a_raw_data",
                "criteria": criteria,
            }
        )
    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import ContentQualityOutput
        from automedia.prompts import load_prompt

        prompt = load_prompt(
            "content_quality",
            content=content,
            criteria=criteria,
            brand=brand,
            platform=platform if platform else None,
        )
        result = llm_complete_structured_safe(
            prompt,
            response_format=ContentQualityOutput,
        )
        return success_response(result.model_dump())
    except LLMError as exc:
        return {
            "quality_score": 0.0,
            "issues": [],
            "suggestions": [],
            "overall_assessment": "",
            **error_response(MCPErrorCode.LLM_ERROR, str(exc)),
        }
    except ImportError as exc:
        return {
            "quality_score": 0.0,
            "issues": [],
            "suggestions": [],
            "overall_assessment": "",
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except ValidationError as exc:
        return {
            "quality_score": 0.0,
            "issues": [],
            "suggestions": [],
            "overall_assessment": "",
            **validation_error_response(
                f"LLM response validation failed: {exc}",
                errors=[{"field": str(e.get("loc", "unknown")), "message": e.get("msg", "")}
                        for e in (exc.errors() if hasattr(exc, "errors") else [])],
            ),
        }
    except Exception as exc:
        return {
            "quality_score": 0.0,
            "issues": [],
            "suggestions": [],
            "overall_assessment": "",
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }
