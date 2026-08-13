"""D1 WeChat Distribution Gate — rewrites base content into WeChat Official Account article format.

This gate reads the pipeline content, rewrites it in WeChat's long-form
article style (professional tone, structured sections, 1500-3000 characters),
performs a single quality check (output length > 500 characters), stores
the result in ``gate_context.extra["d1_output"]``, and writes it to
``04_distribution/wechat/`` in the project directory.
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

_MIN_OUTPUT_LENGTH: int = 500
"""Minimum acceptable output length (characters) for the quality check."""

_EXPECTED_MAP: dict[str, str] = {
    "content_present": "Content is provided in gate_context",
    "llm_success": "LLM call completes without error",
    "output_length": f"Output exceeds {_MIN_OUTPUT_LENGTH} characters",
    "file_write_success": "WeChat article file is written to disk",
}


def _render_wechat_prompt(content: str, brand: str, title: str) -> str:
    """Build the WeChat article rewrite prompt.

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
        f"You are a professional WeChat Official Account content writer.\n"
        f"Rewrite the following content into a polished WeChat article{title_hint} "
        f"for brand \"{brand}\".\n\n"
        f"## WeChat Article Requirements\n\n"
        f"- Write in Simplified Chinese with a professional, authoritative tone\n"
        f"- Structure the article with a compelling hook, clear sections, "
        f"and an actionable conclusion\n"
        f"- Use H2/H3 subheadings to break up sections logically\n"
        f"- Include a click-worthy title at the top (keep under 64 characters)\n"
        f"- Target 1000-3000 characters — substantial enough to deliver real value\n"
        f"- End with a brand-aligned call-to-action\n"
        f"- Maintain factual accuracy — do not fabricate data or quotes\n"
        f"- Use natural, flowing prose — avoid bullet-point lists that feel "
        f"robotic\n\n"
        f"## Source Content\n\n"
        f"{content}\n\n"
        f"Return only the article content, no explanations or meta-commentary."
    )


# ---------------------------------------------------------------------------
# D1Gate
# ---------------------------------------------------------------------------


class D1Gate(BaseGate):
    """D1 WeChat Distribution Gate.

    Rewrites the pipeline's base content into WeChat Official Account format
    using an LLM, validates output length, and persists the result to disk.

    ``gate_context`` expected keys:
        - ``content``: str — the base article content to rewrite (required)
        - ``project_dir``: str — absolute path to the project root (required)
        - ``brand``: str — brand identifier (optional)
        - ``title``: str — original article title (optional)
        - ``config``: dict — merged AutoMedia configuration (optional)

    ``gate_context`` set keys:
        - ``extra["d1_output"]``: str — the WeChat-rewritten article content
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "D1"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Rewrite content into WeChat Official Account format.

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
                gate="D1",
                error="D1Gate: 'content' is required and must be non-empty",
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Build LLM prompt
        # ------------------------------------------------------------------
        prompt = _render_wechat_prompt(content, brand, title)

        # ------------------------------------------------------------------
        # Check 2 — LLM call
        # ------------------------------------------------------------------
        try:
            rewritten: str = llm_complete(prompt, config=config)
        except LLMError as exc:
            log.warning("D1 LLM call failed", error=str(exc))
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
                gate="D1",
                error=f"D1Gate: LLM rewrite failed — {exc}",
                expected_map=_EXPECTED_MAP,
            )

        rewritten = rewritten.strip()

        # ------------------------------------------------------------------
        # Check 3 — output length quality gate
        # ------------------------------------------------------------------
        output_length = len(rewritten)
        if output_length < _MIN_OUTPUT_LENGTH:
            log.warning(
                "D1 output too short",
                length=output_length,
                minimum=_MIN_OUTPUT_LENGTH,
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
                            f"Output length {output_length} chars is below "
                            f"the minimum {_MIN_OUTPUT_LENGTH}"
                        ),
                    },
                ],
                gate="D1",
                error=(
                    f"D1Gate: WeChat rewrite too short "
                    f"({output_length} < {_MIN_OUTPUT_LENGTH} chars)"
                ),
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Store in gate_context for downstream gates
        # ------------------------------------------------------------------
        context_extra = gate_context.setdefault("extra", {})
        if isinstance(context_extra, dict):
            context_extra["d1_output"] = rewritten
        else:
            gate_context["extra"] = {"d1_output": rewritten}

        # ------------------------------------------------------------------
        # Write to 04_distribution/wechat/
        # ------------------------------------------------------------------
        wechat_dir = os.path.join(project_dir, "04_distribution", "wechat")
        os.makedirs(wechat_dir, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_wechat_article.md"
        output_path = os.path.join(wechat_dir, filename)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(rewritten)
        except OSError as exc:
            log.error("D1 file write failed", path=output_path, error=str(exc))
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
                        "detail": f"output length {output_length} chars ≥ {_MIN_OUTPUT_LENGTH}",
                    },
                    {
                        "name": "file_write_success",
                        "passed": False,
                        "detail": f"File write failed: {exc}",
                    },
                ],
                gate="D1",
                error=f"D1Gate: failed to write WeChat article — {exc}",
                expected_map=_EXPECTED_MAP,
            )

        # Record in output_files
        gate_context.setdefault("output_files", []).append(
            {
                "type": "wechat_article",
                "path": output_path,
                "md5": "",
            }
        )

        log.info(
            "D1 WeChat rewrite complete",
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
                    "detail": f"output length {output_length} chars ≥ {_MIN_OUTPUT_LENGTH}",
                },
                {
                    "name": "file_write_success",
                    "passed": True,
                    "detail": f"WeChat article written to {output_path}",
                },
            ],
            gate="D1",
            expected_map=_EXPECTED_MAP,
            output_path=output_path,
            modified_content=rewritten,
        )
