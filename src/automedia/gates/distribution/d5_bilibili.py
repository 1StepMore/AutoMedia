"""D5 Bilibili Rewrite Gate — rewrites draft content into Bilibili-style video script.

Video script format with ``[SCENE]`` markers, hook opening, and Chinese language;
ensures output > 500 chars and contains at least one ``[SCENE]`` marker.

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

_MIN_CONTENT_LENGTH: int = 500
"""Minimum character count for the Bilibili video script output."""

_SCENE_PATTERN: re.Pattern[str] = re.compile(r"\[SCENE\]", re.IGNORECASE)
"""Regex to detect at least one ``[SCENE]`` marker."""

_CHECK_NAMES: list[str] = [
    "bilibili_content_generated",
    "min_length",
    "scene_markers",
]

_EXPECTED_MAP: dict[str, str] = {
    "bilibili_content_generated": "LLM generates non-empty Bilibili-style video script",
    "min_length": f"Content exceeds {_MIN_CONTENT_LENGTH} characters",
    "scene_markers": "Content contains at least one [SCENE] marker",
}


# ---------------------------------------------------------------------------
# D5BilibiliRewrite gate
# ---------------------------------------------------------------------------


class D5BilibiliRewrite(BaseGate):
    """D5 Bilibili Rewrite Gate — rewrites existing draft content into Bilibili video script.

    Takes the ``content`` from ``gate_context``, sends it to an LLM with a
    Bilibili-style prompt (video script with ``[SCENE]`` markers, hook opening,
    Chinese), writes the result to ``04_distribution/bilibili/``, and validates
    output quality.

    ``gate_context`` expected keys:
        - ``topic``: str — the content topic (required)
        - ``brand``: str — brand identifier
        - ``project_dir``: str — absolute path to the project root (required)
        - ``content``: str — draft content produced by CW / earlier gates
        - ``config``: dict — merged AutoMedia configuration (optional)
        - ``brand_profile``: dict — brand voice / style guide (optional)
        - ``brand_platforms``: list[str] — target platforms for prompt scoping

    ``gate_context`` set keys:
        - ``bilibili_content``: str — the Bilibili-rewritten video script
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "D5"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Rewrite draft content as a Bilibili video script and validate output quality.

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
        platform: str = brand_platforms[0] if brand_platforms else "bilibili"

        # ---- Validation: required fields -------------------------------------------
        if not topic:
            return {
                "passed": False,
                "gate": "D5",
                "error": "D5BilibiliRewrite: 'topic' is required in gate_context",
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
                "gate": "D5",
                "error": "D5BilibiliRewrite: 'project_dir' is required in gate_context",
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
                "gate": "D5",
                "error": "D5BilibiliRewrite: no draft 'content' to rewrite in gate_context",
                "checks": [],
                "expected_vs_actual": {
                    "check": "draft_content_present",
                    "expected": "Non-empty content is available for rewriting",
                    "actual": "content is empty or missing",
                    "context": {},
                },
            }

        # ---- LLM rewrite -----------------------------------------------------------
        prompt = load_prompt("bilibili_rewrite", platform=platform)

        # Allow per-call override from model_config.yaml → llm.bilibili.system_prompt
        if config:
            llm_cfg = config.get("llm", {})
            bilibili_sys = llm_cfg.get("bilibili", {}).get("system_prompt")
            if bilibili_sys:
                prompt = bilibili_sys

        user_message = (
            f"Topic: {topic}\nBrand: {brand}\n\nDraft content:\n\n{draft_content}"
        )
        if brand_profile:
            voice = brand_profile.get("voice", "")
            if voice:
                user_message += f"\n\nBrand voice: {voice}"

        try:
            bilibili_content: str = llm_complete(
                user_message,
                config=config,
                system_prompt=prompt,
            )
        except LLMError as exc:
            return {
                "passed": False,
                "gate": "D5",
                "error": f"D5BilibiliRewrite: LLM call failed — {exc}",
                "checks": [
                    {
                        "name": "bilibili_content_generated",
                        "passed": False,
                        "detail": f"LLM call failed: {exc}",
                    },
                ],
                "expected_vs_actual": {
                    "check": "bilibili_content_generated",
                    "expected": _EXPECTED_MAP["bilibili_content_generated"],
                    "actual": f"LLM call failed: {exc}",
                    "context": {},
                },
            }

        if not bilibili_content.strip():
            return {
                "passed": False,
                "gate": "D5",
                "error": "D5BilibiliRewrite: LLM returned empty content",
                "checks": [
                    {
                        "name": "bilibili_content_generated",
                        "passed": False,
                        "detail": "LLM returned empty or whitespace-only content",
                    },
                ],
                "expected_vs_actual": {
                    "check": "bilibili_content_generated",
                    "expected": _EXPECTED_MAP["bilibili_content_generated"],
                    "actual": "LLM returned empty or whitespace-only content",
                    "context": {},
                },
            }

        # ---- Quality checks --------------------------------------------------------
        checks: list[CheckResult] = [
            {
                "name": "bilibili_content_generated",
                "passed": True,
                "detail": (
                    f"Bilibili video script generated ({len(bilibili_content)} chars)"
                ),
            },
            {
                "name": "min_length",
                "passed": len(bilibili_content) > _MIN_CONTENT_LENGTH,
                "detail": (
                    f"Content length {len(bilibili_content)} exceeds {_MIN_CONTENT_LENGTH}"
                    if len(bilibili_content) > _MIN_CONTENT_LENGTH
                    else (
                        f"Content length {len(bilibili_content)} ≤ {_MIN_CONTENT_LENGTH}"
                    )
                ),
            },
            {
                "name": "scene_markers",
                "passed": bool(_SCENE_PATTERN.search(bilibili_content)),
                "detail": (
                    "At least one [SCENE] marker found"
                    if _SCENE_PATTERN.search(bilibili_content)
                    else "No [SCENE] marker found"
                ),
            },
        ]

        all_passed = all(c["passed"] for c in checks)

        # ---- Write to disk ---------------------------------------------------------
        bilibili_dir = os.path.join(project_dir, "04_distribution", "bilibili")
        os.makedirs(bilibili_dir, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_bilibili.md"
        output_path = os.path.join(bilibili_dir, filename)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(bilibili_content)
        except OSError as exc:
            log.warning("D5BilibiliRewrite: failed to write output file", error=str(exc))
            # File write failure is non-blocking for content — still report results
            output_path = ""

        # ---- Update gate_context for downstream gates ------------------------------
        gate_context["bilibili_content"] = bilibili_content
        if output_path:
            gate_context.setdefault("output_files", []).append(
                {"type": "bilibili_script", "path": output_path, "md5": ""}
            )

        return build_gate_result(
            checks,
            gate="D5",
            error=None if all_passed else "Bilibili rewrite quality checks failed",
            expected_map=_EXPECTED_MAP,
            content=bilibili_content,
            output_path=output_path,
        )
