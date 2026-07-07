"""CW — Content Writer Gate.

Generates a full article from the selected topic using an LLM provider
and writes it to ``01_content/drafts/`` in the project directory.

This gate is the boundary between "topic selection" and "content operations".
It runs between ``pre-gate`` (topic_selection) and ``G0`` (fact_check) so
that every downstream gate has real content to work with.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from automedia.core.llm_client import LLMError, llm_complete
from automedia.gates.base import BaseGate

# ---------------------------------------------------------------------------
# Default system prompt used when no override is provided in config
# ---------------------------------------------------------------------------

_DEFAULT_WRITER_PROMPT: str = """\
You are a professional content writer for Chinese social media (WeChat, Xiaohongshu, Bilibili).
Write a high-quality, engaging article in Simplified Chinese based on the topic and brand provided.

Requirements:
- Write in a natural, human tone — avoid AI-sounding language
- Use markdown formatting with headings, lists, and emphasis where appropriate
- Include a compelling title as an H1 heading at the top
- Write 800–1500 characters (Chinese) — substantial enough to be valuable
- Include a strong call-to-action at the end
- Follow the brand voice guidelines if provided
- The article should be original, well-researched in tone, and ready for publication
- DO NOT include any placeholder text, notes about "AI generation", or meta-commentary
Return only the article content, no explanations."""


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

    def execute(self, gate_context: dict[str, Any]) -> dict[str, Any]:
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
            }
        if not project_dir:
            return {
                "passed": False,
                "gate": "CW",
                "error": "ContentWriterGate: 'project_dir' is required in gate_context",
            }

        # --- Build the writer prompt ------------------------------------------------
        writer_prompt = _DEFAULT_WRITER_PROMPT
        # Allow per-call override from model_config.yaml → llm.writer.system_prompt
        if config:
            llm_cfg = config.get("llm", {})
            writer_sys = llm_cfg.get("writer", {}).get("system_prompt")
            if writer_sys:
                writer_prompt = writer_sys

        # Build user message with topic + brand context
        user_message = f"Topic: {topic}\nBrand: {brand}"
        if brand_profile:
            voice = brand_profile.get("voice", "")
            if voice:
                user_message += f"\nBrand voice: {voice}"

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
            }

        if not content.strip():
            return {
                "passed": False,
                "gate": "CW",
                "error": "ContentWriterGate: LLM returned empty content",
            }

        # --- Write to disk ----------------------------------------------------------
        content_dir = os.path.join(project_dir, "01_content", "drafts")
        os.makedirs(content_dir, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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
        }
