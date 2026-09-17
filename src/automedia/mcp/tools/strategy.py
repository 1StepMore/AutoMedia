"""Content strategy MCP tools — brand strategy, pipeline from strategy."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from structlog import get_logger

from automedia.core.llm_client import LLMError
from automedia.exceptions import PipelineError
from automedia.mcp.tools._shared import (
    MCPErrorCode,
    NonEmptyStr,
    PipelineMode,
    ResearchPattern,
    _pipeline_result_to_dict,
    _validate_workflow,
    bind_correlation_id,
    error_response,
    success_response,
    validation_error_response,
)

log = get_logger(__name__)

__all__ = [
    "run_brand_strategy",
    "run_pipeline_from_strategy",
]


def run_brand_strategy(
    brand_name: str,
    industry: str,
    target_audience: str,
    context: str = "",
    pattern: ResearchPattern = "b",
    platform: str = "",
) -> dict[str, Any]:
    """Generate a brand strategy using LLM-driven analysis.

    Loads the ``brand_strategy`` Jinja2 prompt template, fills in the
    parameters, and sends it to the configured LLM via
    :func:`~automedia.core.llm_client.llm_complete_structured_safe` with
    :class:`~automedia.decision.pydantic.BrandStrategyOutput` as the
    response schema.

    Parameters
    ----------
    brand_name:
        Name of the brand to analyse.
    industry:
        Industry or vertical (e.g. ``"SaaS"``, ``"e-commerce"``).
    target_audience:
        Description of the target audience.
    context:
        Optional additional context or constraints for the strategy.
    pattern:
        When ``"a"``, return raw input data without calling the LLM.
        When ``"b"`` (default), use the LLM as usual.
    platform:
        Optional platform name for platform-specific prompt variants.
        When provided and a platform-specific prompt exists (e.g.
        ``platforms/wechat/brand_strategy.j2``), that variant is used.

    Returns
    -------
    dict
        A dict matching the ``BrandStrategyOutput`` schema with keys:
        ``brand_positioning``, ``audience_analysis``,
        ``competitive_landscape``, ``key_differentiators``,
        ``suggested_messaging``.  On failure the dict contains an
        ``"error"`` key instead.
    """
    if pattern == "a":
        return success_response(
            {
                "note": "pattern_a_raw_data",
                "input": {
                    "brand_name": brand_name,
                    "industry": industry,
                    "target_audience": target_audience,
                    "context": context,
                },
            }
        )
    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import BrandStrategyOutput
        from automedia.prompts import load_prompt

        prompt = load_prompt(
            "brand_strategy",
            brand_name=brand_name,
            industry=industry,
            target_audience=target_audience,
            context=context,
            platform=platform if platform else None,
        )
        result = llm_complete_structured_safe(
            prompt,
            response_format=BrandStrategyOutput,
        )
        return success_response(result.model_dump())
    except LLMError as exc:
        return error_response(
            MCPErrorCode.LLM_ERROR,
            f"Brand strategy generation failed: {exc}",
        )
    except ImportError as exc:
        return error_response(MCPErrorCode.IMPORT_ERROR, str(exc))
    except ValidationError as exc:
        return validation_error_response(
            f"LLM response validation failed: {exc}",
            errors=[
                {"field": str(e.get("loc", "unknown")), "message": e.get("msg", "")}
                for e in (exc.errors() if hasattr(exc, "errors") else [])
            ],
        )
    except Exception as exc:
        return error_response(MCPErrorCode.UNKNOWN, str(exc))


def run_pipeline_from_strategy(
    topic: NonEmptyStr,
    brand: NonEmptyStr,
    mode: PipelineMode = "auto",
    strategy_context: str = "",
    pattern: ResearchPattern = "b",
    platform: str = "",
    workflow: str = "",
) -> dict[str, Any]:
    """Generate a content strategy via LLM then execute the production pipeline.

    Loads the ``pipeline_strategy`` Jinja2 prompt template, fills in the
    parameters, and sends it to the configured LLM via
    :func:`~automedia.core.llm_client.llm_complete_structured_safe` with
    :class:`~automedia.decision.pydantic.PipelineStrategyOutput` as the
    response schema.  Then delegates to
    :func:`~automedia.pipelines.runner.run_full_pipeline` with the
    original *topic*, *brand*, and *mode* parameters.

    Parameters
    ----------
    topic:
        Content topic / subject.
    brand:
        Brand identifier.
    mode:
        Pipeline mode — ``"auto"``, ``"text_only"``,
        ``"text_with_cover"``, ``"video_only"``, ``"qa_only"``,
        ``"image-carousel"``, ``"social-thread"``, or
        ``"short-video"``.
    strategy_context:
        Optional additional context or constraints for the strategy
        (e.g. target audience, tone, platform hints).
    pattern:
        When ``"a"``, return raw input data without calling the LLM.
        When ``"b"`` (default), use the LLM as usual.
    platform:
        Optional platform name for platform-specific prompt variants.
        When provided and a platform-specific prompt exists (e.g.
        ``platforms/wechat/pipeline_strategy.j2``), that variant is used.
    workflow:
        Optional named workflow to apply.  When provided, the workflow's
        mode, platforms, gates, prompts, and media spec are merged over
        the brand profile as a higher-priority config layer.

    Returns
    -------
    dict
        ``{"strategy": {...}, "pipeline_result": {...}}`` on success.
        On failure the dict contains an ``"error"`` key with the
        failure description.
    """
    if pattern == "a":
        return success_response(
            {
                "note": "pattern_a_raw_data",
                "input": {
                    "topic": topic,
                    "brand": brand,
                    "mode": mode,
                    "strategy_context": strategy_context,
                },
            }
        )

    # Validate workflow name when provided
    if workflow:
        try:
            _validate_workflow(workflow)
        except (FileNotFoundError, ValueError) as exc:
            return error_response(
                MCPErrorCode.INVALID_PARAM,
                f"Unknown workflow {workflow!r}: {exc}",
            )

    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import PipelineStrategyOutput
        from automedia.pipelines.runner import run_full_pipeline
        from automedia.prompts import load_prompt

        prompt = load_prompt(
            "pipeline_strategy",
            topic=topic,
            brand=brand,
            mode=mode,
            context=strategy_context,
            platform=platform if platform else None,
        )
        strategy: PipelineStrategyOutput = llm_complete_structured_safe(
            prompt,
            response_format=PipelineStrategyOutput,
        )

        bind_correlation_id()
        pipeline_result = run_full_pipeline(
            topic=topic,
            brand=brand,
            mode=mode,
            workflow=workflow or None,
        )

        return success_response(
            {
                "strategy": strategy.model_dump(),
                "pipeline_result": _pipeline_result_to_dict(pipeline_result),
            }
        )
    except LLMError as exc:
        return error_response(
            MCPErrorCode.LLM_ERROR,
            f"Strategy generation failed: {exc}",
        )
    except PipelineError as exc:
        return error_response(
            MCPErrorCode.PIPELINE_ERROR,
            f"Pipeline execution failed: {exc}",
        )
    except ValidationError as exc:
        return validation_error_response(
            f"LLM response validation failed: {exc}",
            errors=[
                {"field": str(e.get("loc", "unknown")), "message": e.get("msg", "")}
                for e in (exc.errors() if hasattr(exc, "errors") else [])
            ],
        )
    except Exception as exc:
        return error_response(MCPErrorCode.UNKNOWN, str(exc))
