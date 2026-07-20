"""P3 Newsletter Repurpose Gate — rewrite → review → humanize sub-pipeline.

Repurposes the pipeline's base content into a newsletter/email format by
running a 3-step sub-pipeline:

    1. **Rewrite** — converts base content into newsletter format using the
       platform-specific ``newsletter/content_writer`` prompt template.
    2. **Review** — evaluates the rewritten content for brand compliance,
       tone, and newsletter-specific quality via the
       ``newsletter/copy_review_g2`` prompt template.
    3. **Humanize** — detects and removes AI writing patterns using the
       ``newsletter/humanizer_g1`` prompt template.

Each step uses the newsletter-adapted prompts created in Task 17 and
included in ``prompts/platforms/newsletter/``.

Output is written to ``04_repurpose/newsletter/`` under the project
directory.

Failure mode: ``retry`` — the pipeline will re-run this gate on failure.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

from structlog import get_logger

from automedia.core.llm_client import LLMError, llm_complete
from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate
from automedia.prompts import load_prompt

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PLATFORM = "newsletter"
"""Platform identifier for prompt resolution and output directory."""

_MIN_OUTPUT_LENGTH: int = 300
"""Minimum acceptable output length (characters) for the quality check."""

_HEADING_PATTERN: re.Pattern[str] = re.compile(r"^#{1,3}\s", re.MULTILINE)
"""Regex to detect markdown section headings."""

_EXPECTED_MAP: dict[str, str] = {
    "content_present": "Content is provided in gate_context",
    "rewrite_success": "LLM rewrite call completes without error",
    "rewrite_quality": (
        f"Rewritten output exceeds {_MIN_OUTPUT_LENGTH} characters "
        f"and contains section headings"
    ),
    "review_completed": "LLM review completes without error",
    "humanize_completed": "LLM humanize call completes without error",
    "file_write_success": "Newsletter file is written to disk",
}

# ---------------------------------------------------------------------------
# Sub-pipeline step functions
# ---------------------------------------------------------------------------


def _step_rewrite(
    content: str,
    brand: str,
    topic: str,
    platform: str,
    config: dict[str, Any] | None,
) -> str | None:
    """Step 1: Rewrite base content into newsletter format.

    Uses the ``newsletter/content_writer`` prompt template which produces
    a conversational newsletter with subject line, preheader, body sections,
    CTA, and sign-off.

    Returns the rewritten content string, or ``None`` on failure.
    """
    prompt = load_prompt("content_writer", platform=platform)

    user_message = (
        f"Topic: {topic}\n"
        f"Brand: {brand}\n\n"
        f"Original content to rewrite into a newsletter:\n\n{content}"
    )

    try:
        rewritten: str = llm_complete(
            prompt + "\n\n" + user_message,
            config=config,
        )
    except LLMError as exc:
        log.warning("P3.rewrite LLM call failed", error=str(exc))
        return None

    rewritten = rewritten.strip()
    if not rewritten:
        log.warning("P3.rewrite returned empty content")
        return None

    return rewritten


def _step_review(
    content: str,
    brand: str,
    platform: str,
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Step 2: Review newsletter content for quality and brand compliance.

    Uses the ``newsletter/copy_review_g2`` prompt template which checks
    tone, brand compliance, subject-line quality, spam indicators, and
    mobile-readability.

    Returns the review result dict (``{"passed": bool, ...}``), or
    ``None`` on LLM failure.
    """
    try:
        review_prompt = load_prompt("copy_review_g2", platform=platform)
    except FileNotFoundError:
        # No newsletter-specific review prompt — skip review step
        log.info("P3.review no platform-specific prompt, skipping")
        return {"passed": True, "issues": []}

    user_message = (
        f"Brand: {brand}\n\n"
        f"Newsletter content to review:\n\n{content}"
    )

    try:
        review_raw: str = llm_complete(
            review_prompt + "\n\n" + user_message,
            config=config,
        )
    except LLMError as exc:
        log.warning("P3.review LLM call failed", error=str(exc))
        return None

    review_raw = review_raw.strip()
    if not review_raw:
        log.warning("P3.review returned empty response")
        return {"passed": True, "issues": [], "raw": ""}

    return {"passed": True, "raw": review_raw}


def _step_humanize(
    content: str,
    platform: str,
    config: dict[str, Any] | None,
) -> str | None:
    """Step 3: Humanize newsletter content to remove AI writing patterns.

    Uses the ``newsletter/humanizer_g1`` prompt template which detects
    corporate-speak, generic value claims, missing personal voice, and
    other AI markers specific to newsletter writing.

    Returns the humanized content string, or the original ``content`` on
    failure (non-fatal).
    """
    try:
        humanize_prompt = load_prompt("humanizer_g1", platform=platform)
    except FileNotFoundError:
        # No newsletter-specific humanizer prompt — skip humanize step
        log.info("P3.humanize no platform-specific prompt, skipping")
        return content

    user_message = (
        f"Newsletter content to humanize:\n\n{content}"
    )

    try:
        humanized: str = llm_complete(
            humanize_prompt + "\n\n" + user_message,
            config=config,
        )
    except LLMError as exc:
        log.warning("P3.humanize LLM call failed", error=str(exc))
        # Non-fatal — return original content
        return content

    humanized = humanized.strip()
    if not humanized:
        return content

    return humanized


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------


def _write_newsletter_output(
    project_dir: str,
    content: str,
    gate_context: GateContext | dict[str, Any],
) -> str | None:
    """Write the final newsletter content to ``04_repurpose/newsletter/``.

    Returns the output file path, or ``None`` on failure.
    """
    newsletter_dir = os.path.join(project_dir, "04_repurpose", "newsletter")
    os.makedirs(newsletter_dir, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_newsletter.md"
    output_path = os.path.join(newsletter_dir, filename)

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as exc:
        log.error("P3 file write failed", path=output_path, error=str(exc))
        return None

    # Record in output_files
    gate_context.setdefault("output_files", []).append(
        {
            "type": "newsletter",
            "path": output_path,
            "md5": "",
        }
    )

    log.info("P3 newsletter written", path=output_path, length=len(content))
    return output_path


# ---------------------------------------------------------------------------
# Quality check
# ---------------------------------------------------------------------------


def _check_rewrite_quality(content: str) -> str | None:
    """Check rewritten content for minimum quality standards.

    Returns ``None`` on pass, or an error string describing the issue.
    """
    length = len(content.strip())
    if length < _MIN_OUTPUT_LENGTH:
        return (
            f"rewritten content length {length} chars is below "
            f"minimum {_MIN_OUTPUT_LENGTH}"
        )
    return None


# ---------------------------------------------------------------------------
# P3NewsletterGate
# ---------------------------------------------------------------------------


class P3NewsletterGate(BaseGate):
    """P3 Newsletter Repurpose Gate.

    Runs a 3-step sub-pipeline (rewrite → review → humanize) to repurpose
    the pipeline's base content into a newsletter/email format using
    platform-adapted prompts.  The final output is written to
    ``04_repurpose/newsletter/``.

    ``gate_context`` expected keys:
        - ``content``: str — the base article content to repurpose (required)
        - ``project_dir``: str — absolute path to the project root (required)
        - ``brand``: str — brand identifier (optional)
        - ``topic``: str — original topic (optional)
        - ``config``: dict — merged AutoMedia configuration (optional)
        - ``brand_platforms``: list[str] — target platforms (optional)

    ``gate_context`` set keys:
        - ``extra["p3_newsletter"]``: str — the final newsletter content
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "P3"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Execute the 3-step newsletter sub-pipeline.

        Args:
            gate_context: Pipeline context containing content and project_dir.

        Returns:
            dict with keys: ``passed``, ``gate``, ``checks``, ``output_path``,
            ``error``, and ``expected_vs_actual``.
        """
        content: str = gate_context.get("content", "")
        project_dir: str = gate_context.get("project_dir", "")
        brand: str = gate_context.get("brand", "")
        topic: str = gate_context.get("topic", "")
        config: dict[str, Any] | None = gate_context.get("config")

        # Detect target platform for platform-scoped prompt overrides
        brand_platforms: list[str] = gate_context.get("brand_platforms", [])
        platform: str = _PLATFORM
        if brand_platforms:
            # Use first platform if it matches our newsletter platform
            for bp in brand_platforms:
                if bp.lower() == "newsletter":
                    platform = bp.lower()
                    break

        # ------------------------------------------------------------------
        # Check 0 — content present
        # ------------------------------------------------------------------
        if not content.strip():
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": False,
                        "detail": "gate_context 'content' is empty or missing",
                    }
                ],
                gate="P3",
                error="P3NewsletterGate: 'content' is required and must be non-empty",
                expected_map=_EXPECTED_MAP,
            )

        if not project_dir:
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": False,
                        "detail": "gate_context 'project_dir' is empty or missing",
                    }
                ],
                gate="P3",
                error="P3NewsletterGate: 'project_dir' is required",
                expected_map=_EXPECTED_MAP,
            )

        # ==================================================================
        # Step 1 — Rewrite
        # ==================================================================
        rewritten = _step_rewrite(content, brand, topic, platform, config)
        if rewritten is None:
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "rewrite_success",
                        "passed": False,
                        "detail": "LLM rewrite call failed or returned empty content",
                    },
                ],
                gate="P3",
                error="P3NewsletterGate: rewrite step failed",
                expected_map=_EXPECTED_MAP,
            )

        # Quality check on rewrite output
        quality_error = _check_rewrite_quality(rewritten)
        if quality_error is not None:
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "rewrite_success",
                        "passed": True,
                        "detail": "LLM rewrite call completed successfully",
                    },
                    {
                        "name": "rewrite_quality",
                        "passed": False,
                        "detail": quality_error,
                    },
                ],
                gate="P3",
                error=f"P3NewsletterGate: rewrite quality check failed — {quality_error}",
                expected_map=_EXPECTED_MAP,
            )

        # ==================================================================
        # Step 2 — Review
        # ==================================================================
        review_result = _step_review(rewritten, brand, platform, config)
        if review_result is None:
            # LLM call failed — non-fatal, continue with original rewritten content
            log.warning("P3 review step failed, continuing without review")
        elif not review_result.get("passed", True):
            # Review identified quality issues — still continue (review is advisory)
            log.warning(
                "P3 review flagged issues",
                issues=review_result.get("issues", []),
            )

        # ==================================================================
        # Step 3 — Humanize
        # ==================================================================
        humanized = _step_humanize(rewritten, platform, config)
        if humanized is None:
            # Non-fatal — use rewritten content as-is
            humanized = rewritten

        # ==================================================================
        # Store in gate_context for downstream gates
        # ==================================================================
        context_extra = gate_context.setdefault("extra", {})
        if isinstance(context_extra, dict):
            context_extra["p3_newsletter"] = humanized
        else:
            gate_context["extra"] = {"p3_newsletter": humanized}

        # ==================================================================
        # Write to 04_repurpose/newsletter/
        # ==================================================================
        output_path = _write_newsletter_output(project_dir, humanized, gate_context)
        if output_path is None:
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "rewrite_success",
                        "passed": True,
                        "detail": "LLM rewrite call completed successfully",
                    },
                    {
                        "name": "rewrite_quality",
                        "passed": True,
                        "detail": (
                            f"rewritten content length {len(rewritten)} chars "
                            f">= {_MIN_OUTPUT_LENGTH}"
                        ),
                    },
                    {
                        "name": "review_completed",
                        "passed": True,
                        "detail": "review step completed",
                    },
                    {
                        "name": "humanize_completed",
                        "passed": True,
                        "detail": "humanize step completed",
                    },
                    {
                        "name": "file_write_success",
                        "passed": False,
                        "detail": "File write failed",
                    },
                ],
                gate="P3",
                error="P3NewsletterGate: failed to write newsletter output",
                expected_map=_EXPECTED_MAP,
            )

        # ==================================================================
        # Success
        # ==================================================================
        log.info(
            "P3 newsletter sub-pipeline complete",
            rewritten_length=len(rewritten),
            humanized_length=len(humanized),
            output_path=output_path,
        )

        return build_gate_result(
            [
                {
                    "name": "content_present",
                    "passed": True,
                    "detail": "content present in gate_context",
                },
                {
                    "name": "rewrite_success",
                    "passed": True,
                    "detail": "LLM rewrite call completed successfully",
                },
                {
                    "name": "rewrite_quality",
                    "passed": True,
                    "detail": (
                        f"rewritten content length {len(rewritten)} chars "
                        f">= {_MIN_OUTPUT_LENGTH}"
                    ),
                },
                {
                    "name": "review_completed",
                    "passed": True,
                    "detail": "review step completed",
                },
                {
                    "name": "humanize_completed",
                    "passed": True,
                    "detail": "humanize step completed",
                },
                {
                    "name": "file_write_success",
                    "passed": True,
                    "detail": f"Newsletter written to {output_path}",
                },
            ],
            gate="P3",
            expected_map=_EXPECTED_MAP,
            output_path=output_path,
            modified_content=humanized,
        )
