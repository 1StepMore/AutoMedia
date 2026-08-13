"""D3 Zhihu Rewrite Gate — rewrites draft content into Zhihu-style Q&A or long-form article.

Q&A or long-form article with Zhihu style (expert tone, Chinese, structured);
ensures output > 800 chars and contains at least one section heading (``##`` / ``###``).

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
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.prompts import load_prompt

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_CONTENT_LENGTH: int = 800
"""Minimum character count for the Zhihu-style output."""

_HEADING_PATTERN: re.Pattern[str] = re.compile(r"^#{2,3}\s", re.MULTILINE)
"""Regex to detect at least one ``##`` or ``###`` section heading."""

_CHECK_NAMES: list[str] = [
    "zhihu_content_generated",
    "min_length",
    "section_headings",
]

_EXPECTED_MAP: dict[str, str] = {
    "zhihu_content_generated": "LLM generates non-empty Zhihu-style content",
    "min_length": f"Content exceeds {_MIN_CONTENT_LENGTH} characters",
    "section_headings": "Content contains at least one ## or ### section heading",
}


# ---------------------------------------------------------------------------
# D3ZhihuRewrite gate
# ---------------------------------------------------------------------------


class D3ZhihuRewrite(BaseGate):
    """D3 Zhihu Rewrite Gate — rewrites existing draft content into Zhihu style.

    Takes the ``content`` from ``gate_context``, sends it to an LLM with a
    Zhihu-style prompt (expert tone, Chinese, structured sections or Q&A),
    writes the result to ``04_distribution/zhihu/``, and validates output
    quality.

    ``gate_context`` expected keys:
        - ``topic``: str — the content topic (required)
        - ``brand``: str — brand identifier
        - ``project_dir``: str — absolute path to the project root (required)
        - ``content``: str — draft content produced by CW / earlier gates
        - ``config``: dict — merged AutoMedia configuration (optional)
        - ``brand_profile``: dict — brand voice / style guide (optional)
        - ``brand_platforms``: list[str] — target platforms for prompt scoping

    ``gate_context`` set keys:
        - ``zhihu_content``: str — the Zhihu-rewritten content
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "D3"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Rewrite draft content in Zhihu style and validate output quality.

        Args:
            gate_context: Pipeline context with ``topic``, ``project_dir``,
                ``content``, and optional ``config`` / ``brand_profile``.

        Returns:
            dict with keys: ``passed``, ``gate``, ``content``, ``output_path``,
            ``checks``, and ``error`` on failure.
        """
        topic: str = gate_context.get("topic", "")
        brand: str = gate_context.get("brand", "")
        project_dir: str = gate_context.get("project_dir", "")
        draft_content: str = gate_context.get("content", "")
        config: dict[str, Any] | None = gate_context.get("config")
        brand_profile: dict[str, Any] = gate_context.get("brand_profile", {})

        # Detect target platform for platform-scoped prompt overrides
        brand_platforms: list[str] = gate_context.get("brand_platforms", [])
        platform: str = brand_platforms[0] if brand_platforms else "zhihu"

        # ---- Validation: required fields -------------------------------------------
        if not topic:
            return {
                "passed": False,
                "gate": "D3",
                "error": "D3ZhihuRewrite: 'topic' is required in gate_context",
                "checks": [],
                "expected_vs_actual": {
                    "check": "topic_present",
                    "expected": "Topic is provided in gate_context",
                    "actual": "topic is empty or missing",
                    "context": {},
                },
            }

        if not project_dir:
            return {
                "passed": False,
                "gate": "D3",
                "error": "D3ZhihuRewrite: 'project_dir' is required in gate_context",
                "checks": [],
                "expected_vs_actual": {
                    "check": "project_dir_present",
                    "expected": "Project directory is provided in gate_context",
                    "actual": "project_dir is empty or missing",
                    "context": {},
                },
            }

        if not draft_content.strip():
            return {
                "passed": False,
                "gate": "D3",
                "error": "D3ZhihuRewrite: no draft 'content' to rewrite in gate_context",
                "checks": [],
                "expected_vs_actual": {
                    "check": "draft_content_present",
                    "expected": "Non-empty content is available for rewriting",
                    "actual": "content is empty or missing",
                    "context": {},
                },
            }

        # ---- LLM rewrite -----------------------------------------------------------
        prompt = load_prompt("zhihu_rewrite", platform=platform)

        # Allow per-call override from model_config.yaml → llm.zhihu.system_prompt
        if config:
            llm_cfg = config.get("llm", {})
            zhihu_sys = llm_cfg.get("zhihu", {}).get("system_prompt")
            if zhihu_sys:
                prompt = zhihu_sys

        user_message = f"Topic: {topic}\nBrand: {brand}\n\nDraft content:\n\n{draft_content}"
        if brand_profile:
            voice = brand_profile.get("voice", "")
            if voice:
                user_message += f"\n\nBrand voice: {voice}"

        try:
            zhihu_content: str = llm_complete(
                user_message,
                config=config,
                system_prompt=prompt,
            )
        except LLMError as exc:
            return {
                "passed": False,
                "gate": "D3",
                "error": f"D3ZhihuRewrite: LLM call failed — {exc}",
                "checks": [
                    {
                        "name": "zhihu_content_generated",
                        "passed": False,
                        "detail": f"LLM call failed: {exc}",
                    },
                ],
                "expected_vs_actual": {
                    "check": "zhihu_content_generated",
                    "expected": _EXPECTED_MAP["zhihu_content_generated"],
                    "actual": f"LLM call failed: {exc}",
                    "context": {},
                },
            }

        if not zhihu_content.strip():
            return {
                "passed": False,
                "gate": "D3",
                "error": "D3ZhihuRewrite: LLM returned empty content",
                "checks": [
                    {
                        "name": "zhihu_content_generated",
                        "passed": False,
                        "detail": "LLM returned empty or whitespace-only content",
                    },
                ],
                "expected_vs_actual": {
                    "check": "zhihu_content_generated",
                    "expected": _EXPECTED_MAP["zhihu_content_generated"],
                    "actual": "LLM returned empty or whitespace-only content",
                    "context": {},
                },
            }

        # ---- Quality checks --------------------------------------------------------

        checks: list[CheckResult] = [
            {
                "name": "zhihu_content_generated",
                "passed": True,
                "detail": f"Zhihu-style content generated ({len(zhihu_content)} chars)",
            },
            {
                "name": "min_length",
                "passed": len(zhihu_content) > _MIN_CONTENT_LENGTH,
                "detail": (
                    f"Content length {len(zhihu_content)} exceeds {_MIN_CONTENT_LENGTH}"
                    if len(zhihu_content) > _MIN_CONTENT_LENGTH
                    else f"Content length {len(zhihu_content)} ≤ {_MIN_CONTENT_LENGTH}"
                ),
            },
            {
                "name": "section_headings",
                "passed": bool(_HEADING_PATTERN.search(zhihu_content)),
                "detail": (
                    "At least one ## or ### section heading found"
                    if _HEADING_PATTERN.search(zhihu_content)
                    else "No ## or ### section heading found"
                ),
            },
        ]

        all_passed = all(c["passed"] for c in checks)

        # ---- Write to disk ---------------------------------------------------------
        zhihu_dir = os.path.join(project_dir, "04_distribution", "zhihu")
        os.makedirs(zhihu_dir, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_zhihu.md"
        output_path = os.path.join(zhihu_dir, filename)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(zhihu_content)
        except OSError as exc:
            log.warning("D3ZhihuRewrite: failed to write output file", error=str(exc))
            # File write failure is non-blocking for content — still report results
            output_path = ""

        # ---- Update gate_context for downstream gates ------------------------------
        gate_context["zhihu_content"] = zhihu_content
        if output_path:
            gate_context.setdefault("output_files", []).append(
                {"type": "zhihu_article", "path": output_path, "md5": ""}
            )

        return build_gate_result(
            checks,
            gate="D3",
            error=None if all_passed else "Zhihu rewrite quality checks failed",
            expected_map=_EXPECTED_MAP,
            content=zhihu_content,
            output_path=output_path,
        )
