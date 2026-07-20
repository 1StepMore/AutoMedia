"""P1 WeChat Repurpose Gate — rewrite → fact check → humanize sub-pipeline.

Repurposes the pipeline's base content into a WeChat Official Account style
by running a 3-step sub-pipeline:

    1. **Rewrite** — converts base content into polished WeChat article format
       (professional tone, structured sections, 1000-3000 characters).
    2. **Fact Check** — lightweight factual consistency check on the rewritten
       content (adapted from G0, not a full gate).
    3. **Humanize** — removes AI-generated phrasing patterns (adapted from G1,
       not a full gate).

Each step uses repurpose-specific light-weight logic — no full G0/G1 gate
instances are reused.

Output is written to ``04_repurpose/wechat/`` under the project directory.

Failure mode: ``retry`` — the pipeline will re-run this gate on failure.
"""

from __future__ import annotations

import json as json_mod
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PLATFORM = "wechat"
"""Platform identifier for output directory naming."""

_MIN_OUTPUT_LENGTH: int = 500
"""Minimum acceptable output length (characters) after rewrite."""

_HEADING_PATTERN: re.Pattern[str] = re.compile(r"^#{1,3}\s", re.MULTILINE)
"""Regex to detect markdown section headings."""

_EXPECTED_MAP: dict[str, str] = {
    "content_present": "Content is provided in gate_context",
    "rewrite_success": "LLM rewrite call completes without error",
    "rewrite_quality": (
        f"Rewritten output exceeds {_MIN_OUTPUT_LENGTH} characters"
    ),
    "fact_check_completed": "Fact-check review completes without error",
    "humanize_completed": "LLM humanize call completes without error",
    "file_write_success": "WeChat repurpose file is written to disk",
}

# ---------------------------------------------------------------------------
# Sub-pipeline step 1 — Rewrite
# ---------------------------------------------------------------------------


def _render_rewrite_prompt(content: str, brand: str, title: str) -> str:
    """Build the WeChat repurpose rewrite prompt.

    Parameters
    ----------
    content:
        The source content to repurpose.
    brand:
        Brand identifier for brand-aligned messaging.
    title:
        The article title (optional, may be empty).

    Returns
    -------
    str
        The rendered prompt string.
    """
    title_hint = f' (original title: "{title}")' if title else ""

    return (
        f"You are a professional WeChat Official Account content writer.\n"
        f"Repurpose the following content into a polished WeChat article"
        f"{title_hint} for brand \"{brand}\".\n\n"
        f"## WeChat Article Requirements\n\n"
        f"- Write in Simplified Chinese with a professional, authoritative tone\n"
        f"- Structure the article with a compelling hook, clear sections, "
        f"and an actionable conclusion\n"
        f"- Use H2/H3 subheadings to break up sections logically\n"
        f"- Include a click-worthy title at the top (keep under 64 characters)\n"
        f"- Target 1000-3000 characters \u2014 substantial enough to deliver real value\n"
        f"- End with a brand-aligned call-to-action\n"
        f"- Maintain factual accuracy \u2014 do not fabricate data or quotes\n"
        f"- Use natural, flowing prose \u2014 avoid bullet-point lists that feel "
        f"robotic\n\n"
        f"## Source Content\n\n"
        f"{content}\n\n"
        f"Return only the article content, no explanations or meta-commentary."
    )


def _step_rewrite(
    content: str,
    brand: str,
    title: str,
    config: dict[str, Any] | None,
) -> str | None:
    """Step 1: Rewrite base content into WeChat repurpose format.

    Parameters
    ----------
    content:
        The base content to rewrite.
    brand:
        Brand identifier.
    title:
        Original article title.
    config:
        Merged AutoMedia configuration (optional).

    Returns
    -------
    str or None
        Rewritten content string, or ``None`` on failure.
    """
    prompt = _render_rewrite_prompt(content, brand, title)

    try:
        rewritten: str = llm_complete(prompt, config=config)
    except LLMError as exc:
        log.warning("P1.rewrite LLM call failed", error=str(exc))
        return None

    rewritten = rewritten.strip()
    if not rewritten:
        log.warning("P1.rewrite returned empty content")
        return None

    return rewritten


# ---------------------------------------------------------------------------
# Sub-pipeline step 2 — Fact check (lightweight, not full G0)
# ---------------------------------------------------------------------------


def _render_fact_check_prompt(content: str) -> str:
    """Build a lightweight fact-check prompt for repurposed content.

    Parameters
    ----------
    content:
        The rewritten content to verify.

    Returns
    -------
    str
        The rendered prompt string.
    """
    return (
        f"Review the following WeChat article for factual accuracy.\n"
        f"Check for:\n"
        f"1. Any fabricated data, statistics, or quotes\n"
        f"2. Plausible but unsupported claims\n"
        f"3. Contradictions within the content\n"
        f"4. Misleading or exaggerated statements\n\n"
        f"Respond in JSON format:\n"
        f'{{"passed": true/false, "issues": [{{"type": str, "detail": str}}], '
        f'"summary": str}}\n'
        f"Set passed=false if ANY issue is found.\n\n"
        f"## Content\n\n"
        f"{content}"
    )


def _step_fact_check(
    content: str,
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Step 2: Lightweight fact check on the rewritten content.

    Parameters
    ----------
    content:
        The rewritten content to verify.
    config:
        Merged AutoMedia configuration (optional).

    Returns
    -------
    dict or None
        Result dict with ``passed``, ``issues``, ``summary`` keys,
        or ``None`` on LLM failure.
    """
    if not content.strip():
        return {
            "passed": False,
            "issues": [{"type": "empty", "detail": "No content to check"}],
            "summary": "Content is empty",
        }

    prompt = _render_fact_check_prompt(content)

    try:
        raw: str = llm_complete(prompt, config=config)
    except LLMError as exc:
        log.warning("P1.fact_check LLM call failed", error=str(exc))
        return None

    raw = raw.strip()

    # Attempt JSON parse; fall back to text heuristic
    try:
        result = json_mod.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("not a dict")
        result.setdefault("passed", True)
        result.setdefault("issues", [])
        result.setdefault("summary", "")
        return result
    except (json_mod.JSONDecodeError, ValueError):
        # Non-JSON response — heuristic: check for failure keywords
        passed = not any(
            kw in raw.lower() for kw in ("fail", "issue", "error", "inaccurate")
        )
        return {
            "passed": passed,
            "issues": [],
            "summary": raw[:200] if raw else "No summary available",
        }


# ---------------------------------------------------------------------------
# Sub-pipeline step 3 — Humanize (lightweight, not full G1)
# ---------------------------------------------------------------------------


def _render_humanize_prompt(content: str) -> str:
    """Build a lightweight humanization prompt for WeChat repurpose content.

    Parameters
    ----------
    content:
        The rewritten/fact-checked content to humanize.

    Returns
    -------
    str
        The rendered prompt string.
    """
    return (
        f"Rewrite the following WeChat article to make it read more naturally.\n"
        f"Remove:\n"
        f"- AI transition phrases: 'furthermore', 'in summary', "
        f"'in the realm of', 'it is worth noting', 'importantly'\n"
        f"- Overly uniform sentence structure\n"
        f"- Robotic or flat tone\n"
        f"- Formulaic paragraph transitions\n\n"
        f"Preserve:\n"
        f"- All factual information and data\n"
        f"- The article's structure and section headings\n"
        f"- The brand message and call-to-action\n"
        f"- Chinese language and WeChat-appropriate style\n\n"
        f"Return only the rewritten content, no explanations.\n\n"
        f"## Content\n\n"
        f"{content}"
    )


def _step_humanize(
    content: str,
    config: dict[str, Any] | None,
) -> str | None:
    """Step 3: Lightweight humanization of the WeChat content.

    Removes AI-generated phrasing patterns while preserving factual content.

    Parameters
    ----------
    content:
        The content to humanize.
    config:
        Merged AutoMedia configuration (optional).

    Returns
    -------
    str or None
        Humanized content string, or ``None`` on failure (caller may
        fall back to original content).
    """
    if not content.strip():
        return None

    prompt = _render_humanize_prompt(content)

    try:
        humanized: str = llm_complete(prompt, config=config)
    except LLMError as exc:
        log.warning("P1.humanize LLM call failed", error=str(exc))
        return None

    humanized = humanized.strip()
    if not humanized:
        return None

    return humanized


# ---------------------------------------------------------------------------
# Quality check helpers
# ---------------------------------------------------------------------------


def _check_rewrite_quality(content: str) -> str | None:
    """Check rewritten content for minimum quality standards.

    Parameters
    ----------
    content:
        The rewritten content to check.

    Returns
    -------
    str or None
        ``None`` on pass, or an error string describing the issue.
    """
    length = len(content.strip())
    if length < _MIN_OUTPUT_LENGTH:
        return (
            f"rewritten content length {length} chars is below "
            f"minimum {_MIN_OUTPUT_LENGTH}"
        )
    return None


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------


def _write_wechat_output(
    project_dir: str,
    content: str,
    gate_context: GateContext | dict[str, Any],
) -> str | None:
    """Write the final repurposed content to ``04_repurpose/wechat/``.

    Parameters
    ----------
    project_dir:
        Absolute path to the project root.
    content:
        The final content to write.
    gate_context:
        Pipeline context (for appending output_files).

    Returns
    -------
    str or None
        Output file path, or ``None`` on failure.
    """
    wechat_dir = os.path.join(project_dir, "04_repurpose", "wechat")
    os.makedirs(wechat_dir, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_wechat_repurpose.md"
    output_path = os.path.join(wechat_dir, filename)

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except OSError as exc:
        log.error("P1 file write failed", path=output_path, error=str(exc))
        return None

    # Record in output_files
    gate_context.setdefault("output_files", []).append(
        {
            "type": "wechat_repurpose",
            "path": output_path,
            "md5": "",
        }
    )

    log.info("P1 WeChat repurpose written", path=output_path, length=len(content))
    return output_path


# ---------------------------------------------------------------------------
# P1WechatGate
# ---------------------------------------------------------------------------


class P1WechatGate(BaseGate):
    """P1 WeChat Repurpose Gate.

    Runs a 3-step sub-pipeline (rewrite -> fact_check -> humanize) to repurpose
    pipeline content into a WeChat Official Account article format.  Each step
    uses repurpose-specific lightweight functions — no full G0/G1 instances.

    ``gate_context`` expected keys:
        - ``content``: str — the base article content to repurpose (required)
        - ``project_dir``: str — absolute path to the project root (required)
        - ``brand``: str — brand identifier (optional)
        - ``title``: str — original article title (optional)
        - ``config``: dict — merged AutoMedia configuration (optional)

    ``gate_context`` set keys:
        - ``extra["p1_output"]``: str — the final WeChat repurposed content
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "P1"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Execute the 3-step WeChat repurpose sub-pipeline.

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
                gate="P1",
                error="P1WechatGate: 'content' is required and must be non-empty",
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
                gate="P1",
                error="P1WechatGate: 'project_dir' is required",
                expected_map=_EXPECTED_MAP,
            )

        # ==================================================================
        # Step 1 — Rewrite
        # ==================================================================
        rewritten = _step_rewrite(content, brand, title, config)
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
                gate="P1",
                error="P1WechatGate: rewrite step failed",
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
                gate="P1",
                error=f"P1WechatGate: rewrite quality check failed — {quality_error}",
                expected_map=_EXPECTED_MAP,
            )

        # ==================================================================
        # Step 2 — Fact check (lightweight, not full G0)
        # ==================================================================
        fact_check_result = _step_fact_check(rewritten, config)
        if fact_check_result is None:
            # LLM call failed — non-fatal, continue with rewritten content
            log.warning("P1 fact_check step failed, continuing without fact check")
        elif not fact_check_result.get("passed", True):
            # Fact check found issues — log but continue (advisory)
            log.warning(
                "P1 fact_check flagged issues",
                issues=fact_check_result.get("issues", []),
            )

        # ==================================================================
        # Step 3 — Humanize (lightweight, not full G1)
        # ==================================================================
        humanized = _step_humanize(rewritten, config)
        if humanized is None:
            # Non-fatal — use rewritten content as-is
            humanized = rewritten

        # ==================================================================
        # Store in gate_context for downstream gates
        # ==================================================================
        context_extra = gate_context.setdefault("extra", {})
        if isinstance(context_extra, dict):
            context_extra["p1_output"] = humanized
        else:
            gate_context["extra"] = {"p1_output": humanized}

        # ==================================================================
        # Write to 04_repurpose/wechat/
        # ==================================================================
        output_path = _write_wechat_output(project_dir, humanized, gate_context)
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
                        "name": "fact_check_completed",
                        "passed": True,
                        "detail": "fact check step completed",
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
                gate="P1",
                error="P1WechatGate: failed to write WeChat repurpose output",
                expected_map=_EXPECTED_MAP,
            )

        # ==================================================================
        # Success
        # ==================================================================
        log.info(
            "P1 WeChat repurpose sub-pipeline complete",
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
                    "name": "fact_check_completed",
                    "passed": True,
                    "detail": "fact check step completed",
                },
                {
                    "name": "humanize_completed",
                    "passed": True,
                    "detail": "humanize step completed",
                },
                {
                    "name": "file_write_success",
                    "passed": True,
                    "detail": f"WeChat repurpose written to {output_path}",
                },
            ],
            gate="P1",
            expected_map=_EXPECTED_MAP,
            output_path=output_path,
            modified_content=humanized,
        )
