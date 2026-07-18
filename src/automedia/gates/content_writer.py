"""CW — Content Writer Gate.

Generates a full article from the selected topic using an LLM provider
and writes it to ``01_content/drafts/`` in the project directory.

This gate is the boundary between "topic selection" and "content operations".
It runs between ``pre-gate`` (topic_selection) and ``G0`` (fact_check) so
that every downstream gate has real content to work with.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from structlog import get_logger

from automedia.core.llm_client import LLMError, llm_complete
from automedia.gates._context import GateContext
from automedia.gates.base import BaseGate
from automedia.prompts import load_prompt

log = get_logger(__name__)

_EXPECTED_MAP: dict[str, str] = {
    "topic_present": "Topic is provided in gate_context",
    "project_dir_present": "Project directory is provided in gate_context",
    "llm_success": "LLM call completes without error",
    "content_not_empty": "LLM returns non-empty content",
    "file_write_success": "Draft file is written to disk",
    "content_generated": "Article content is generated and saved",
}

_THRESHOLDS: dict[str, str] = {
    "topic_present": "gate_context must contain a non-empty 'topic' string",
    "project_dir_present": "gate_context must contain a non-empty 'project_dir' string",
    "llm_success": "LLM call must return without raising LLMError",
    "content_not_empty": "LLM response must contain non-whitespace content",
    "file_write_success": "Draft file must be writable to 01_content/drafts/",
}

_SUGGESTIONS: dict[str, str] = {
    "topic_present": "Provide a non-empty 'topic' string in gate_context",
    "project_dir_present": "Provide a valid 'project_dir' path in gate_context",
    "llm_success": "Check LLM configuration (API key, model, endpoint) and network connectivity",
    "content_not_empty": "Review the writer prompt — it may be producing empty responses",
    "file_write_success": "Ensure the project directory exists and is writable",
}


def _derive_expected(check_name: str) -> str:
    """Convert a check name to a human-readable expected statement."""
    return _EXPECTED_MAP.get(check_name, check_name.replace("_", " ").capitalize())


# ---------------------------------------------------------------------------
# ContentWriterGate
# ---------------------------------------------------------------------------


class ContentWriterGate(BaseGate):
    """Generate article content from topic using an LLM provider.

    ``gate_context`` expected keys:
        - ``topic``: str — the content topic (required)
        - ``brand``: str — brand identifier
        - ``project_dir``: str — absolute path to the project root
        - ``config``: dict — merged AutoMedia configuration (optional;
          loaded from :func:`~automedia.core.config_loader.load_config`
          when missing)
        - ``brand_profile``: dict — brand voice / style guide (optional)
        - ``source_data``: dict — source info (optional, used for context)

    ``gate_context`` set keys:
        - ``content``: str — the generated article (so downstream gates
          like G0, G1, G2, G3 can work with it)
        - ``output_files``: list[dict] — added entry for the written file

    Returns
    -------
    dict with keys: ``passed``, ``gate``, ``content``, ``output_path``, ``error``.
    """

    _gate_name = "CW"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Generate article content from the provided topic via LLM.

        Validates that ``topic`` and ``project_dir`` are present in the
        context, calls the LLM to produce content, writes the draft to
        ``01_content/drafts/`` under the project directory, and updates
        gate_context with the generated content for downstream gates.

        Args:
            gate_context: Pipeline context containing ``topic``, ``brand``,
                ``project_dir``, and optional ``config`` / ``brand_profile``.

        Returns:
            dict with keys: ``passed``, ``gate``, ``content``, ``output_path``,
            ``expected_vs_actual``, and ``error`` on failure.
        """
        topic: str = gate_context.get("topic", "")
        brand: str = gate_context.get("brand", "")
        project_dir: str = gate_context.get("project_dir", "")
        config: dict[str, Any] | None = gate_context.get("config")
        brand_profile: dict[str, Any] = gate_context.get("brand_profile", {})

        if not topic:
            return {
                "passed": False,
                "gate": "CW",
                "error": "ContentWriterGate: 'topic' is required in gate_context",
                "checks": [
                    {
                        "name": "topic_present",
                        "passed": False,
                        "detail": "topic is empty or missing",
                        "actual_value": f"topic={topic!r}",
                        "threshold": _THRESHOLDS["topic_present"],
                        "suggestion": _SUGGESTIONS["topic_present"],
                    },
                ],
                "expected_vs_actual": {
                    "check": "topic_present",
                    "expected": _derive_expected("topic_present"),
                    "actual": "topic is empty or missing",
                    "context": {},
                },
            }
        if not project_dir:
            return {
                "passed": False,
                "gate": "CW",
                "error": "ContentWriterGate: 'project_dir' is required in gate_context",
                "checks": [
                    {
                        "name": "project_dir_present",
                        "passed": False,
                        "detail": "project_dir is empty or missing",
                        "actual_value": f"project_dir={project_dir!r}",
                        "threshold": _THRESHOLDS["project_dir_present"],
                        "suggestion": _SUGGESTIONS["project_dir_present"],
                    },
                ],
                "expected_vs_actual": {
                    "check": "project_dir_present",
                    "expected": _derive_expected("project_dir_present"),
                    "actual": "project_dir is empty or missing",
                    "context": {},
                },
            }

        # Detect target platform for platform-scoped prompt overrides
        brand_platforms: list[str] = gate_context.get("brand_platforms", [])
        platform: str = brand_platforms[0] if brand_platforms else ""

        # --- Build the writer prompt ------------------------------------------------
        writer_prompt = load_prompt("content_writer", platform=platform)
        # Allow per-call override from model_config.yaml → llm.writer.system_prompt
        if config:
            llm_cfg = config.get("llm", {})
            writer_sys = llm_cfg.get("writer", {}).get("system_prompt")
            if writer_sys:
                writer_prompt = writer_sys

        # Detect pipeline mode for content length optimization
        pipeline_mode: str = gate_context.get("mode", "") or ""
        is_short_video: bool = pipeline_mode == "short-video"

        # Build user message with topic + brand context
        user_message = f"Topic: {topic}\nBrand: {brand}"
        if brand_profile:
            voice = brand_profile.get("voice", "")
            if voice:
                user_message += f"\nBrand voice: {voice}"

        # Inject format hint for social-thread mode
        content_format = gate_context.get("content_format", "")
        if content_format == "social_thread":
            user_message += (
                "\n\nIMPORTANT: Write this content as a social media thread "
                "with 5-8 numbered posts. Each post must have its own hook "
                "and contain 2-4 short paragraphs. Format each post with\n"
                "'## Post N: <hook>' headers. The thread should flow "
                "logically from post to post, building a complete narrative."
            )
        if is_short_video:
            user_message += (
                "\n\nIMPORTANT: This is for a SHORT VIDEO format. "
                "Write concise, punchy content (200–400 characters Chinese). "
                "Use short sentences, a hook at the start, and a strong CTA. "
                "Avoid long paragraphs — this is optimized for 30–60 second video narration."
            )

        # --- Call LLM ---------------------------------------------------------------
        try:
            content: str = llm_complete(
                user_message,
                config=config,
                system_prompt=writer_prompt,
            )
        except LLMError as exc:
            return {
                "passed": False,
                "gate": "CW",
                "error": f"ContentWriterGate: LLM call failed — {exc}",
                "checks": [
                    {
                        "name": "llm_success",
                        "passed": False,
                        "detail": f"LLM call failed: {exc}",
                        "actual_value": str(exc),
                        "threshold": _THRESHOLDS["llm_success"],
                        "suggestion": _SUGGESTIONS["llm_success"],
                    },
                ],
                "expected_vs_actual": {
                    "check": "llm_success",
                    "expected": _derive_expected("llm_success"),
                    "actual": f"LLM call failed: {exc}",
                    "context": {},
                },
            }

        if not content.strip():
            return {
                "passed": False,
                "gate": "CW",
                "error": "ContentWriterGate: LLM returned empty content",
                "checks": [
                    {
                        "name": "content_not_empty",
                        "passed": False,
                        "detail": "LLM returned empty or whitespace-only content",
                        "actual_value": f"content length={len(content)}",
                        "threshold": _THRESHOLDS["content_not_empty"],
                        "suggestion": _SUGGESTIONS["content_not_empty"],
                    },
                ],
                "expected_vs_actual": {
                    "check": "content_not_empty",
                    "expected": _derive_expected("content_not_empty"),
                    "actual": "LLM returned empty or whitespace-only content",
                    "context": {},
                },
            }

        # --- Write to disk ----------------------------------------------------------
        content_dir = os.path.join(project_dir, "01_content", "drafts")
        os.makedirs(content_dir, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_draft.md"
        output_path = os.path.join(content_dir, filename)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(content)
        except OSError as exc:
            return {
                "passed": False,
                "gate": "CW",
                "error": f"ContentWriterGate: failed to write file — {exc}",
                "checks": [
                    {
                        "name": "file_write_success",
                        "passed": False,
                        "detail": f"File write failed: {exc}",
                        "actual_value": str(exc),
                        "threshold": _THRESHOLDS["file_write_success"],
                        "suggestion": _SUGGESTIONS["file_write_success"],
                    },
                ],
                "expected_vs_actual": {
                    "check": "file_write_success",
                    "expected": _derive_expected("file_write_success"),
                    "actual": f"File write failed: {exc}",
                    "context": {},
                },
            }

        # --- Update gate_context for downstream gates -------------------------------
        gate_context["content"] = content
        gate_context.setdefault("output_files", []).append(
            {"type": "article", "path": output_path, "md5": ""}
        )

        return {
            "passed": True,
            "gate": "CW",
            "content": content,
            "output_path": output_path,
            "expected_vs_actual": {
                "check": "content_generated",
                "expected": _derive_expected("content_generated"),
                "actual": f"Article written to {output_path}",
                "context": {},
            },
        }
