"""D6 YouTube Standalone Rewrite Gate.

Rewrites pipeline content into a YouTube-style video script with:

- Intro hook — attention-grabbing opening
- Body sections — 2-4 structured segments with clear transitions
- Outro CTA — call to action (like, subscribe, comment)

All output is in English, optimised for YouTube's spoken-word format.
Writes to ``04_distribution/youtube/`` under the project directory.
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

_MIN_OUTPUT_LENGTH: int = 500
"""Minimum acceptable output length (characters) for the quality check."""

_EXPECTED_MAP: dict[str, str] = {
    "content_present": "Content is provided in gate_context",
    "llm_success": "LLM call completes without error",
    "youtube_script_quality": (
        f"Output exceeds {_MIN_OUTPUT_LENGTH} characters and has clear "
        f"intro, body, and outro sections"
    ),
    "file_write_success": "YouTube script file is written to disk",
}

# ---------------------------------------------------------------------------
# Section-detection patterns
# ---------------------------------------------------------------------------

_INTRO_PATTERNS: list[str] = [
    r"##\s*(?:intro|hook|opening)\b",
    r"\*\*intro(?:duction)?\*\*",
    r"\(intro\)",
    r"^intro(?:duction)?[:\s]",
]

_BODY_PATTERNS: list[str] = [
    r"##\s*(?:section|body|main|part|segment)\s*\d*",
    r"##\s*(?:point|key\s+point|topic|chapter)\s*\d*",
    r"\*\*(?:section|body|main)\*\*",
]

_OUTRO_PATTERNS: list[str] = [
    r"##\s*(?:outro|closing|conclusion|wrap.?up|summary)\b",
    r"\*\*outro\*\*",
    r"^outro[:\s]",
    r"\(outro\)",
]

_CTA_PATTERNS: list[str] = [
    r"(?:like|subscribe|comment|share|follow|ring\s+the\s+bell)",
    r"(?:click|tap|hit)\s+(?:that\s+)?(?:like|subscribe|bell|button)",
    r"(?:thanks?\s+(?:for\s+)?(?:watching|reading|sticking\s+around))",
    r"(?:see\s+you\s+(?:in\s+the\s+next|next\s+time))",
    r"(?:let\s+me\s+know|drop\s+(?:a|your)\s+comment)",
]

_COMPILED_INTRO = re.compile("|".join(_INTRO_PATTERNS), re.IGNORECASE)
_COMPILED_BODY = re.compile("|".join(_BODY_PATTERNS), re.IGNORECASE)
_COMPILED_OUTRO = re.compile("|".join(_OUTRO_PATTERNS), re.IGNORECASE)
_COMPILED_CTA = re.compile("|".join(_CTA_PATTERNS), re.IGNORECASE)


def _render_youtube_prompt(content: str, brand: str, title: str) -> str:
    """Build the YouTube video script rewrite prompt.

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
    title_hint = f" (adapted from: \"{title}\")" if title else ""

    return (
        f"You are a YouTube script writer. Rewrite the following content "
        f"into a video script{title_hint} for brand \"{brand}\".\n\n"
        f"## YouTube Script Requirements\n\n"
        f"- Write in English — conversational, punchy, spoken-word style\n"
        f"- Structure the script with these three clear sections:\n"
        f"  1. **Intro / Hook** — a strong attention-grabber that tells "
        f"viewers what they'll learn (use an ``## Intro`` heading)\n"
        f"  2. **Body** — 2-4 sections that develop the topic. Use "
        f"headings like ``## Section 1: ...``, ``## Section 2: ...``\n"
        f"  3. **Outro / CTA** — summary + call to action (use an "
        f"``## Outro`` heading)\n"
        f"- Keep sentences short and natural — YouTube is spoken, not read\n"
        f"- Use line breaks between sections for pacing\n"
        f"- End with a clear call to action (like, subscribe, comment)\n"
        f"- DO NOT include placeholder text or meta-commentary\n"
        f"- Return only the script content, no explanations\n\n"
        f"## Source Content\n\n"
        f"{content}"
    )


def _check_youtube_script_quality(script: str) -> str | None:
    """Run the single YouTube quality check.

    Returns ``None`` on pass, or an error-message string on failure.

    Quality criteria (combined into one check):
    - Output exceeds ``_MIN_OUTPUT_LENGTH`` characters
    - Has clear intro/hook section heading
    - Has clear body section heading(s)
    - Has clear outro/closing section heading
    - Has a call-to-action in the outro
    """
    issues: list[str] = []

    # Minimum length
    length = len(script.strip())
    if length < _MIN_OUTPUT_LENGTH:
        issues.append(
            f"script length {length} chars is below minimum {_MIN_OUTPUT_LENGTH}"
        )

    # Section structure
    if not _COMPILED_INTRO.search(script):
        issues.append("missing intro/hook section heading")
    if not _COMPILED_BODY.search(script):
        issues.append("missing body section heading")
    if not _COMPILED_OUTRO.search(script):
        issues.append("missing outro/closing section heading")
    if not _COMPILED_CTA.search(script):
        issues.append("missing call-to-action in outro")

    if not issues:
        return None
    return "; ".join(issues)


# ---------------------------------------------------------------------------
# D6YouTubeGate
# ---------------------------------------------------------------------------


class D6YouTubeGate(BaseGate):
    """D6 YouTube Standalone Rewrite Gate.

    Rewrites the pipeline's base content into a YouTube video script
    format using an LLM, validates output quality (length + section
    structure), and persists the result to disk.

    ``gate_context`` expected keys:
        - ``content``: str — the base article content to rewrite (required)
        - ``project_dir``: str — absolute path to the project root (required)
        - ``brand``: str — brand identifier (optional)
        - ``title``: str — original article title (optional)
        - ``config``: dict — merged AutoMedia configuration (optional)

    ``gate_context`` set keys:
        - ``extra["d6_output"]``: str — the YouTube-rewritten script content
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "D6"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Rewrite content into a YouTube video script format.

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
                gate="D6",
                error="D6YouTubeGate: 'content' is required and must be non-empty",
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
                gate="D6",
                error="D6YouTubeGate: 'project_dir' is required",
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Build LLM prompt
        # ------------------------------------------------------------------
        prompt = _render_youtube_prompt(content, brand, title)

        # ------------------------------------------------------------------
        # Check 2 — LLM call
        # ------------------------------------------------------------------
        try:
            script: str = llm_complete(prompt, config=config)
        except LLMError as exc:
            log.warning("D6 LLM call failed", error=str(exc))
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
                gate="D6",
                error=f"D6YouTubeGate: LLM rewrite failed — {exc}",
                expected_map=_EXPECTED_MAP,
            )

        script = script.strip()
        if not script:
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
                        "name": "youtube_script_quality",
                        "passed": False,
                        "detail": "LLM returned empty script",
                    },
                ],
                gate="D6",
                error="D6YouTubeGate: LLM returned empty script",
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Check 3 — YouTube script quality (length + section structure)
        # ------------------------------------------------------------------
        quality_error = _check_youtube_script_quality(script)
        if quality_error is not None:
            log.warning(
                "D6 YouTube script quality check failed",
                error=quality_error,
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
                        "name": "youtube_script_quality",
                        "passed": False,
                        "detail": quality_error,
                    },
                ],
                gate="D6",
                error=f"D6YouTubeGate: quality check failed — {quality_error}",
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Store in gate_context for downstream gates
        # ------------------------------------------------------------------
        context_extra = gate_context.setdefault("extra", {})
        if isinstance(context_extra, dict):
            context_extra["d6_output"] = script
        else:
            gate_context["extra"] = {"d6_output": script}

        # ------------------------------------------------------------------
        # Write to 04_distribution/youtube/
        # ------------------------------------------------------------------
        youtube_dir = os.path.join(project_dir, "04_distribution", "youtube")
        os.makedirs(youtube_dir, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_youtube_script.md"
        output_path = os.path.join(youtube_dir, filename)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(script)
        except OSError as exc:
            log.error("D6 file write failed", path=output_path, error=str(exc))
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
                        "name": "youtube_script_quality",
                        "passed": True,
                        "detail": (
                            f"script length {len(script)} chars >= {_MIN_OUTPUT_LENGTH}, "
                            f"all sections present"
                        ),
                    },
                    {
                        "name": "file_write_success",
                        "passed": False,
                        "detail": f"File write failed: {exc}",
                    },
                ],
                gate="D6",
                error=f"D6YouTubeGate: failed to write YouTube script -- {exc}",
                expected_map=_EXPECTED_MAP,
            )

        # Record in output_files
        gate_context.setdefault("output_files", []).append(
            {
                "type": "youtube_script",
                "path": output_path,
                "md5": "",
            }
        )

        log.info(
            "D6 YouTube rewrite complete",
            script_length=len(script),
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
                    "name": "youtube_script_quality",
                    "passed": True,
                    "detail": (
                        f"script length {len(script)} chars >= {_MIN_OUTPUT_LENGTH}, "
                        f"all sections present"
                    ),
                },
                {
                    "name": "file_write_success",
                    "passed": True,
                    "detail": f"YouTube script written to {output_path}",
                },
            ],
            gate="D6",
            expected_map=_EXPECTED_MAP,
            output_path=output_path,
            modified_content=script,
        )
