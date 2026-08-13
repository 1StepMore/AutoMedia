"""D4 Xiaohongshu Rewrite Gate — rewrites draft content into Xiaohongshu-style notes.

Xiaohongshu (小红书 / RED) note format: image-heavy note style, emoji-rich,
personal experience tone, Simplified Chinese. Produces a note with engaging
hooks, emotional resonance, and community-feel language.

Quality check: output > 200 characters and contains at least one emoji or
section heading (``#`` / ``##`` / ``###``).

Failure mode: ``retry`` — the pipeline will re-run this gate on quality failure.
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

log = get_logger(__name__)

_MIN_OUTPUT_LENGTH: int = 200
"""Minimum acceptable output length (characters) for the quality check."""

_EMOJI_PATTERN: re.Pattern[str] = re.compile(
    r"[\U0001F300-\U0001F9FF\u2600-\u27BF\uFE00-\uFE0F]"
)
"""Regex to detect emoji characters."""

_SECTION_PATTERN: re.Pattern[str] = re.compile(r"^#{1,3}\s", re.MULTILINE)
"""Regex to detect markdown section headings (``#``, ``##``, ``###``)."""

_EXPECTED_MAP: dict[str, str] = {
    "content_present": "Content is provided in gate_context",
    "llm_success": "LLM call completes without error",
    "content_quality": (
        f"Output exceeds {_MIN_OUTPUT_LENGTH} characters and contains "
        f"at least one emoji or section heading"
    ),
    "file_write_success": "Xiaohongshu note file is written to disk",
}


def _render_xiaohongshu_prompt(content: str, brand: str, title: str) -> str:
    """Build the Xiaohongshu note rewrite prompt.

    Parameters
    ----------
    content:
        The source content to rewrite.
    brand:
        Brand identifier for brand-aligned messaging.
    title:
        The article title (optional, may be empty).

    Returns
    -------
    str
        The rendered prompt string.
    """
    title_hint = f" (original title: \"{title}\")" if title else ""

    return (
        f"You are a professional content creator for Xiaohongshu (小红书 / RED).\n"
        f"Rewrite the following content into an engaging Xiaohongshu-style "
        f"note{title_hint} for brand \"{brand}\".\n\n"
        f"## Xiaohongshu Note Requirements\n\n"
        f"- Write in Simplified Chinese with a personal, authentic, "
        f"conversational tone\n"
        f"- Use a first-person perspective (我/我们) — share personal "
        f"experiences and genuine feelings\n"
        f"- Include emojis (📌✨🔥👍) naturally throughout the text "
        f"— they are essential for Xiaohongshu style\n"
        f"- Structure the note with short paragraphs and line breaks "
        f"for easy reading on mobile\n"
        f"- Write a compelling title at the top with emoji decoration, "
        f'e.g. "✨ 我发现了..."\n'
        f"- Target 300-1000 characters — concise and punchy\n"
        f"- End with engagement hooks: questions, calls for comments, "
        f"saved collection prompts\n"
        f"- Use trending Xiaohongshu expressions: 不得不说, 真的绝了, "
        f"谁懂啊, 建议收藏\n"
        f"- Maintain factual accuracy — do not fabricate experiences\n"
        f"- Each paragraph should be 1-3 sentences max\n\n"
        f"## Source Content\n\n"
        f"{content}\n\n"
        f"Return only the note content, no explanations or meta-commentary."
    )


def _contains_emoji(text: str) -> bool:
    """Check if text contains at least one emoji character."""
    return bool(_EMOJI_PATTERN.search(text))


def _contains_section(text: str) -> bool:
    """Check if text contains at least one section heading."""
    return bool(_SECTION_PATTERN.search(text))


# ---------------------------------------------------------------------------
# D4Gate
# ---------------------------------------------------------------------------


class D4Gate(BaseGate):
    """D4 Xiaohongshu Rewrite Gate.

    Rewrites the pipeline's base content into Xiaohongshu note format
    using an LLM, validates output quality, and persists the result to disk.

    ``gate_context`` expected keys:
        - ``content``: str — the base article content to rewrite (required)
        - ``project_dir``: str — absolute path to the project root (required)
        - ``brand``: str — brand identifier (optional)
        - ``title``: str — original article title (optional)
        - ``config``: dict — merged AutoMedia configuration (optional)

    ``gate_context`` set keys:
        - ``extra["d4_output"]``: str — the Xiaohongshu-rewritten note content
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "D4"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Rewrite content into Xiaohongshu note format.

        Args:
            gate_context: Pipeline context containing content and project_dir.

        Returns:
            dict with keys: ``passed``, ``gate``, ``checks``, ``output_path``,
            ``error``, and ``expected_vs_actual``.
        """
        content: str = gate_context.get("content", "")
        project_dir: str = gate_context.get("project_dir", "")
        brand: str = gate_context.get("brand", "")
        title: str = gate_context.get("title", "")
        config: dict[str, Any] | None = gate_context.get("config")

        # ------------------------------------------------------------------
        # Check 1 — content present
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
                gate="D4",
                error="D4Gate: 'content' is required and must be non-empty",
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Build LLM prompt
        # ------------------------------------------------------------------
        prompt = _render_xiaohongshu_prompt(content, brand, title)

        # ------------------------------------------------------------------
        # Check 2 — LLM call
        # ------------------------------------------------------------------
        try:
            rewritten: str = llm_complete(prompt, config=config)
        except LLMError as exc:
            log.warning("D4 LLM call failed", error=str(exc))
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "llm_success",
                        "passed": False,
                        "detail": f"LLM call failed: {exc}",
                    },
                ],
                gate="D4",
                error=f"D4Gate: LLM rewrite failed — {exc}",
                expected_map=_EXPECTED_MAP,
            )

        rewritten = rewritten.strip()

        # ------------------------------------------------------------------
        # Check 3 — content quality (single quality check combining both
        # conditions: minimum length + emoji/section presence)
        # ------------------------------------------------------------------
        output_length = len(rewritten)
        has_emoji = _contains_emoji(rewritten)
        has_section = _contains_section(rewritten)

        quality_passed = output_length > _MIN_OUTPUT_LENGTH and (has_emoji or has_section)

        if not quality_passed:
            detail_parts: list[str] = []
            if output_length <= _MIN_OUTPUT_LENGTH:
                detail_parts.append(
                    f"length {output_length} ≤ {_MIN_OUTPUT_LENGTH} chars"
                )
            if not has_emoji and not has_section:
                detail_parts.append("no emoji or section headings found")

            log.warning(
                "D4 content quality check failed",
                output_length=output_length,
                has_emoji=has_emoji,
                has_section=has_section,
            )
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "llm_success",
                        "passed": True,
                        "detail": "LLM call completed successfully",
                    },
                    {
                        "name": "content_quality",
                        "passed": False,
                        "detail": "; ".join(detail_parts),
                    },
                ],
                gate="D4",
                error=(
                    f"D4Gate: Xiaohongshu rewrite quality check failed — "
                    f"{'; '.join(detail_parts)}"
                ),
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Store in gate_context for downstream gates
        # ------------------------------------------------------------------
        context_extra = gate_context.setdefault("extra", {})
        if isinstance(context_extra, dict):
            context_extra["d4_output"] = rewritten
        else:
            gate_context["extra"] = {"d4_output": rewritten}

        # ------------------------------------------------------------------
        # Write to 04_distribution/xiaohongshu/
        # ------------------------------------------------------------------
        xiaohongshu_dir = os.path.join(project_dir, "04_distribution", "xiaohongshu")
        os.makedirs(xiaohongshu_dir, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_xiaohongshu_note.md"
        output_path = os.path.join(xiaohongshu_dir, filename)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(rewritten)
        except OSError as exc:
            log.error("D4 file write failed", path=output_path, error=str(exc))
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "llm_success",
                        "passed": True,
                        "detail": "LLM call completed successfully",
                    },
                    {
                        "name": "content_quality",
                        "passed": True,
                        "detail": (
                            f"output length {output_length} chars > "
                            f"{_MIN_OUTPUT_LENGTH}, "
                            f"emoji={'yes' if has_emoji else 'no'}, "
                            f"section={'yes' if has_section else 'no'}"
                        ),
                    },
                    {
                        "name": "file_write_success",
                        "passed": False,
                        "detail": f"File write failed: {exc}",
                    },
                ],
                gate="D4",
                error=f"D4Gate: failed to write Xiaohongshu note — {exc}",
                expected_map=_EXPECTED_MAP,
            )

        # Record in output_files
        gate_context.setdefault("output_files", []).append(
            {
                "type": "xiaohongshu_note",
                "path": output_path,
                "md5": "",
            }
        )

        log.info(
            "D4 Xiaohongshu rewrite complete",
            output_length=output_length,
            has_emoji=has_emoji,
            has_section=has_section,
            output_path=output_path,
        )

        # ------------------------------------------------------------------
        # Success
        # ------------------------------------------------------------------
        return build_gate_result(
            [
                {
                    "name": "content_present",
                    "passed": True,
                    "detail": "content present in gate_context",
                },
                {
                    "name": "llm_success",
                    "passed": True,
                    "detail": "LLM call completed successfully",
                },
                {
                    "name": "content_quality",
                    "passed": True,
                    "detail": (
                        f"output length {output_length} chars > "
                        f"{_MIN_OUTPUT_LENGTH}, "
                        f"emoji={'yes' if has_emoji else 'no'}, "
                        f"section={'yes' if has_section else 'no'}"
                    ),
                },
                {
                    "name": "file_write_success",
                    "passed": True,
                    "detail": f"Xiaohongshu note written to {output_path}",
                },
            ],
            gate="D4",
            expected_map=_EXPECTED_MAP,
            output_path=output_path,
            modified_content=rewritten,
        )
