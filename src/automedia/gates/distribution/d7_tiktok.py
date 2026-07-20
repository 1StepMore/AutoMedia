"""D7 TikTok Distribution Gate — rewrites base content into a TikTok video script.

This gate reads the pipeline content, rewrites it as a TikTok-style
short-form video script (hook-first, trending tone, 15-60 second duration),
performs a single quality check (output length 100-500 characters), stores
the result in ``gate_context.extra["d7_output"]``, and writes it to
``04_distribution/tiktok/`` in the project directory.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from structlog import get_logger

from automedia.core.llm_client import LLMError, llm_complete
from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate

log = get_logger(__name__)

_MIN_OUTPUT_LENGTH: int = 100
"""Minimum acceptable output length (characters)."""

_MAX_OUTPUT_LENGTH: int = 500
"""Maximum acceptable output length (characters)."""

_EXPECTED_MAP: dict[str, str] = {
    "content_present": "Content is provided in gate_context",
    "llm_success": "LLM call completes without error",
    "output_length": (
        f"Output between {_MIN_OUTPUT_LENGTH} and {_MAX_OUTPUT_LENGTH} characters"
    ),
    "file_write_success": "TikTok script file is written to disk",
}


def _render_tiktok_prompt(content: str, brand: str, title: str) -> str:
    """Build the TikTok video script rewrite prompt.

    Parameters
    ----------
    content:
        The source content to rewrite into a TikTok script.
    brand:
        Brand identifier for brand-aligned messaging.
    title:
        The article title (optional, may be empty).

    Returns
    -------
    str
        The rendered prompt string.
    """
    title_hint = f" (adapted from: \"{title}\")" if title else ""

    return (
        f"You are a TikTok content creator who makes viral short-form videos.\n"
        f"Rewrite the following content into a TikTok video script{title_hint} "
        f"for brand \"{brand}\".\n\n"
        f"## TikTok Script Requirements\n\n"
        f"- Write in Simplified Chinese (or match the source language)\n"
        f"- **CRITICAL: Output must be 100-500 characters total** — brief and punchy\n"
        f"- Start with a HOOK: the first 2 seconds must grab attention "
        f"(question, bold claim, or controversy)\n"
        f"- Use a fast-paced, trending, conversational tone — like speaking "
        f"directly to camera\n"
        f"- Design for 15-60 second video duration\n"
        f"- Include visual/action cues in [brackets] where appropriate "
        f"(e.g., [cut to], [text overlay], [zoom in])\n"
        f"- End with a strong call-to-action (follow, comment, share, like)\n"
        f"- Use short sentences, line breaks for pacing\n"
        f"- DO NOT use formal or academic language\n"
        f"- DO NOT include hashtags in the script body\n"
        f"- DO NOT include meta-commentary or explanations\n"
        f"- Return only the script content, no extra text\n\n"
        f"## Source Content\n\n"
        f"{content}"
    )


# ---------------------------------------------------------------------------
# D7Gate
# ---------------------------------------------------------------------------


class D7Gate(BaseGate):
    """D7 TikTok Distribution Gate.

    Rewrites the pipeline's base content into a TikTok short-form video
    script using an LLM, validates output length (100-500 chars), and
    persists the result to disk.

    ``gate_context`` expected keys:
        - ``content``: str — the base article content to rewrite (required)
        - ``project_dir``: str — absolute path to the project root (required)
        - ``brand``: str — brand identifier (optional)
        - ``title``: str — original article title (optional)
        - ``config``: dict — merged AutoMedia configuration (optional)

    ``gate_context`` set keys:
        - ``extra["d7_output"]``: str — the TikTok-rewritten script content
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "D7"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Rewrite content into a TikTok video script format.

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
                gate="D7",
                error="D7Gate: 'content' is required and must be non-empty",
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Build LLM prompt
        # ------------------------------------------------------------------
        prompt = _render_tiktok_prompt(content, brand, title)

        # ------------------------------------------------------------------
        # Check 2 — LLM call
        # ------------------------------------------------------------------
        try:
            rewritten: str = llm_complete(prompt, config=config)
        except LLMError as exc:
            log.warning("D7 LLM call failed", error=str(exc))
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
                gate="D7",
                error=f"D7Gate: LLM rewrite failed — {exc}",
                expected_map=_EXPECTED_MAP,
            )

        rewritten = rewritten.strip()

        # ------------------------------------------------------------------
        # Check 3 — output length quality gate (100-500 chars)
        # ------------------------------------------------------------------
        output_length = len(rewritten)
        if output_length < _MIN_OUTPUT_LENGTH or output_length > _MAX_OUTPUT_LENGTH:
            log.warning(
                "D7 output length out of range",
                length=output_length,
                minimum=_MIN_OUTPUT_LENGTH,
                maximum=_MAX_OUTPUT_LENGTH,
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
                        "name": "output_length",
                        "passed": False,
                        "detail": (
                            f"Output length {output_length} chars is outside "
                            f"the required range [{_MIN_OUTPUT_LENGTH}, {_MAX_OUTPUT_LENGTH}]"
                        ),
                    },
                ],
                gate="D7",
                error=(
                    f"D7Gate: TikTok script length {output_length} chars is "
                    f"outside range [{_MIN_OUTPUT_LENGTH}, {_MAX_OUTPUT_LENGTH}]"
                ),
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Store in gate_context for downstream gates
        # ------------------------------------------------------------------
        context_extra = gate_context.setdefault("extra", {})
        if isinstance(context_extra, dict):
            context_extra["d7_output"] = rewritten
        else:
            gate_context["extra"] = {"d7_output": rewritten}

        # ------------------------------------------------------------------
        # Write to 04_distribution/tiktok/
        # ------------------------------------------------------------------
        tiktok_dir = os.path.join(project_dir, "04_distribution", "tiktok")
        os.makedirs(tiktok_dir, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_tiktok_script.md"
        output_path = os.path.join(tiktok_dir, filename)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(rewritten)
        except OSError as exc:
            log.error("D7 file write failed", path=output_path, error=str(exc))
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
                        "name": "output_length",
                        "passed": True,
                        "detail": (
                            f"output length {output_length} chars is within "
                            f"[{_MIN_OUTPUT_LENGTH}, {_MAX_OUTPUT_LENGTH}]"
                        ),
                    },
                    {
                        "name": "file_write_success",
                        "passed": False,
                        "detail": f"File write failed: {exc}",
                    },
                ],
                gate="D7",
                error=f"D7Gate: failed to write TikTok script — {exc}",
                expected_map=_EXPECTED_MAP,
            )

        # Record in output_files
        gate_context.setdefault("output_files", []).append(
            {
                "type": "tiktok_script",
                "path": output_path,
                "md5": "",
            }
        )

        log.info(
            "D7 TikTok rewrite complete",
            output_length=output_length,
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
                    "name": "output_length",
                    "passed": True,
                    "detail": (
                        f"output length {output_length} chars is within "
                        f"[{_MIN_OUTPUT_LENGTH}, {_MAX_OUTPUT_LENGTH}]"
                    ),
                },
                {
                    "name": "file_write_success",
                    "passed": True,
                    "detail": f"TikTok script written to {output_path}",
                },
            ],
            gate="D7",
            expected_map=_EXPECTED_MAP,
            output_path=output_path,
            modified_content=rewritten,
        )
