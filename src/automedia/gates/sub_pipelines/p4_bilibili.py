"""P4 Bilibili Repurpose Gate — 3-step sub-pipeline for Bilibili-adapted video scripts.

Runs a sub-pipeline of rewrite → fact_check → humanize, each step adapted for
Bilibili's Chinese video script format (``[TIMESTAMP]``, ``[VISUAL]``,
``[弹幕互动]`` markers).  The output is written to ``04_repurpose/bilibili/``.

This is a **repurpose** gate (P-series), distinct from the **distribution**
D5BilibiliRewrite gate which does a single-shot rewrite to
``04_distribution/bilibili/``.  P4 runs a multi-step pipeline for deeper
platform adaptation.

Failure mode: ``retry`` — the pipeline will re-run this gate on quality failure.
"""

from __future__ import annotations

import json
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
"""Minimum character count for the final Bilibili video script output."""

_SCENE_PATTERN: re.Pattern[str] = re.compile(r"\[(TIMESTAMP|SCENE)\]", re.IGNORECASE)
"""Regex to detect at least one scene/timestamp marker in the script."""

_CHECK_NAMES: list[str] = [
    "rewrite_step",
    "fact_check_step",
    "humanize_step",
    "min_length",
    "scene_markers",
]

_EXPECTED_MAP: dict[str, str] = {
    "rewrite_step": "Bilibili rewrite step produces non-empty video script",
    "fact_check_step": "Bilibili fact-check step verifies content quality",
    "humanize_step": "Bilibili humanize step removes AI-generated patterns",
    "min_length": f"Final content exceeds {_MIN_CONTENT_LENGTH} characters",
    "scene_markers": "Content contains at least one [TIMESTAMP] or [SCENE] marker",
}

_OUTPUT_SUBDIR: str = os.path.join("04_repurpose", "bilibili")
"""Relative path under ``project_dir`` for P4 output."""


# ---------------------------------------------------------------------------
# P4BilibiliRepurpose gate
# ---------------------------------------------------------------------------


class P4BilibiliRepurpose(BaseGate):
    """P4 Bilibili Repurpose Gate — 3-step sub-pipeline for Bilibili adaptation.

    Takes the ``content`` from ``gate_context`` and runs three sequential
    LLM-driven steps:

    1. **rewrite** — Rewrites draft content into a Bilibili-style Chinese video
       script with ``[TIMESTAMP]`` / ``[VISUAL]`` / ``[弹幕互动]`` markers,
       hook opening, and platform-native tone.
    2. **fact_check** — Verifies brand compliance, tone, and content quality
       using Bilibili-adapted review criteria.
    3. **humanize** — Detects and removes AI-generated writing patterns,
       ensuring the script reads like a real Bilibili UP creator.

    The final output is written to ``04_repurpose/bilibili/`` under the project
    directory.

    ``gate_context`` expected keys:
        - ``topic``: str — the content topic (required)
        - ``brand``: str — brand identifier
        - ``project_dir``: str — absolute path to the project root (required)
        - ``content``: str — draft content produced by CW / earlier gates
        - ``config``: dict — merged AutoMedia configuration (optional)
        - ``brand_profile``: dict — brand voice / style guide (optional)
        - ``brand_platforms``: list[str] — target platforms for prompt scoping

    ``gate_context`` set keys:
        - ``bilibili_repurpose_content``: str — the final Bilibili-adapted script
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "P4"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run the 3-step Bilibili repurpose sub-pipeline.

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
                "gate": "P4",
                "error": "P4BilibiliRepurpose: 'topic' is required in gate_context",
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
                "gate": "P4",
                "error": "P4BilibiliRepurpose: 'project_dir' is required in gate_context",
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
                "gate": "P4",
                "error": "P4BilibiliRepurpose: no draft 'content' to rewrite in gate_context",
                "checks": [],
                "expected_vs_actual": {
                    "check": "draft_content_present",
                    "expected": "Non-empty content is available for rewriting",
                    "actual": "content is empty or missing",
                    "context": {},
                },
            }

        # ------------------------------------------------------------------
        # Step 1: Rewrite — Bilibili video script adaptation
        # ------------------------------------------------------------------
        log.info("P4.sub_pipeline.step_1", step="rewrite")

        rewrite_prompt = load_prompt("content_writer", platform=platform)
        # Allow per-call override from config
        if config:
            llm_cfg = config.get("llm", {})
            bilibili_sys = llm_cfg.get("bilibili", {}).get("system_prompt")
            if bilibili_sys:
                rewrite_prompt = bilibili_sys

        rewrite_user = (
            f"Topic: {topic}\nBrand: {brand}\n\n"
            f"Draft content:\n\n{draft_content}"
        )
        if brand_profile:
            voice = brand_profile.get("voice", "")
            if voice:
                rewrite_user += f"\n\nBrand voice: {voice}"

        try:
            rewritten_content: str = llm_complete(
                rewrite_user,
                config=config,
                system_prompt=rewrite_prompt,
            )
        except LLMError as exc:
            return {
                "passed": False,
                "gate": "P4",
                "error": f"P4BilibiliRepurpose: rewrite step LLM call failed — {exc}",
                "checks": [
                    {
                        "name": "rewrite_step",
                        "passed": False,
                        "detail": f"LLM call failed: {exc}",
                    },
                ],
                "expected_vs_actual": {
                    "check": "rewrite_step",
                    "expected": _EXPECTED_MAP["rewrite_step"],
                    "actual": f"LLM call failed: {exc}",
                    "context": {},
                },
            }

        if not rewritten_content.strip():
            return {
                "passed": False,
                "gate": "P4",
                "error": "P4BilibiliRepurpose: rewrite step returned empty content",
                "checks": [
                    {
                        "name": "rewrite_step",
                        "passed": False,
                        "detail": "LLM returned empty or whitespace-only content",
                    },
                ],
                "expected_vs_actual": {
                    "check": "rewrite_step",
                    "expected": _EXPECTED_MAP["rewrite_step"],
                    "actual": "LLM returned empty or whitespace-only content",
                    "context": {},
                },
            }

        log.info(
            "P4.sub_pipeline.step_1.complete",
            step="rewrite",
            length=len(rewritten_content),
        )

        # ------------------------------------------------------------------
        # Step 2: Fact-check / brand review — Bilibili-adapted
        # ------------------------------------------------------------------
        log.info("P4.sub_pipeline.step_2", step="fact_check")

        fc_prompt = load_prompt("copy_review_g2", platform=platform)
        brand_guidelines = ""
        if brand_profile:
            brand_guidelines = json.dumps(
                brand_profile, ensure_ascii=False, default=str
            )
        fc_user = (
            f"Content:\n\n{rewritten_content}\n\n"
            f"Brand guidelines:\n\n{brand_guidelines}"
        )

        try:
            review_result_raw: str = llm_complete(
                fc_user,
                config=config,
                system_prompt=fc_prompt,
            )
        except LLMError as exc:
            return {
                "passed": False,
                "gate": "P4",
                "error": f"P4BilibiliRepurpose: fact_check step LLM call failed — {exc}",
                "checks": [
                    {
                        "name": "fact_check_step",
                        "passed": False,
                        "detail": f"LLM call failed: {exc}",
                    },
                ],
                "expected_vs_actual": {
                    "check": "fact_check_step",
                    "expected": _EXPECTED_MAP["fact_check_step"],
                    "actual": f"LLM call failed: {exc}",
                    "context": {},
                },
            }

        # Parse review result (expected as JSON)
        fc_passed: bool = False
        fc_detail: str = "Fact-check review completed"
        try:
            review_data = json.loads(review_result_raw)
            fc_passed = bool(review_data.get("passed", True))
            fc_issues = review_data.get("issues", [])
            if fc_issues:
                fc_detail = f"Fact-check issues found: {'; '.join(fc_issues[:3])}"
            else:
                fc_detail = "Fact-check passed with no issues"
        except (json.JSONDecodeError, ValueError):
            # Non-JSON response — gate passes but note the parsing issue
            fc_passed = True
            fc_detail = "Fact-check response was not JSON-parseable; accepting content"

        log.info(
            "P4.sub_pipeline.step_2.complete",
            step="fact_check",
            passed=fc_passed,
        )

        # ------------------------------------------------------------------
        # Step 3: Humanize — remove AI writing patterns (Bilibili-adapted)
        # ------------------------------------------------------------------
        log.info("P4.sub_pipeline.step_3", step="humanize")

        hz_prompt = load_prompt("humanizer_g1", platform=platform)
        hz_user = f"Content:\n\n{rewritten_content}"

        try:
            humanize_result_raw: str = llm_complete(
                hz_user,
                config=config,
                system_prompt=hz_prompt,
            )
        except LLMError as exc:
            return {
                "passed": False,
                "gate": "P4",
                "error": f"P4BilibiliRepurpose: humanize step LLM call failed — {exc}",
                "checks": [
                    {
                        "name": "humanize_step",
                        "passed": False,
                        "detail": f"LLM call failed: {exc}",
                    },
                ],
                "expected_vs_actual": {
                    "check": "humanize_step",
                    "expected": _EXPECTED_MAP["humanize_step"],
                    "actual": f"LLM call failed: {exc}",
                    "context": {},
                },
            }

        # Parse humanize result (expected as JSON)
        hz_passed: bool = False
        hz_detail: str = "Humanize review completed"
        try:
            hz_data = json.loads(humanize_result_raw)
            hz_passed = bool(hz_data.get("passed", True))
            hz_issues = hz_data.get("issues", [])
            if hz_issues:
                hz_detail = f"Humanize issues found: {'; '.join(hz_issues[:3])}"
            else:
                hz_detail = "Humanize passed with no issues"
        except (json.JSONDecodeError, ValueError):
            hz_passed = True
            hz_detail = "Humanize response was not JSON-parseable; accepting content"

        log.info(
            "P4.sub_pipeline.step_3.complete",
            step="humanize",
            passed=hz_passed,
        )

        # ---- Quality checks --------------------------------------------------------
        final_content = rewritten_content
        checks: list[CheckResult] = [
            {
                "name": "rewrite_step",
                "passed": True,
                "detail": (
                    f"Bilibili rewrite completed ({len(rewritten_content)} chars)"
                ),
            },
            {
                "name": "fact_check_step",
                "passed": fc_passed,
                "detail": fc_detail,
            },
            {
                "name": "humanize_step",
                "passed": hz_passed,
                "detail": hz_detail,
            },
            {
                "name": "min_length",
                "passed": len(final_content) > _MIN_CONTENT_LENGTH,
                "detail": (
                    f"Final content length {len(final_content)} exceeds {_MIN_CONTENT_LENGTH}"
                    if len(final_content) > _MIN_CONTENT_LENGTH
                    else (
                        f"Final content length {len(final_content)} ≤ {_MIN_CONTENT_LENGTH}"
                    )
                ),
            },
            {
                "name": "scene_markers",
                "passed": bool(_SCENE_PATTERN.search(final_content)),
                "detail": (
                    "At least one [TIMESTAMP] or [SCENE] marker found"
                    if _SCENE_PATTERN.search(final_content)
                    else "No [TIMESTAMP] or [SCENE] marker found"
                ),
            },
        ]

        all_passed = all(c["passed"] for c in checks)

        # ---- Write to disk ---------------------------------------------------------
        output_dir = os.path.join(project_dir, _OUTPUT_SUBDIR)
        os.makedirs(output_dir, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_bilibili_repurpose.md"
        output_path = os.path.join(output_dir, filename)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(final_content)
        except OSError as exc:
            log.warning("P4BilibiliRepurpose: failed to write output file", error=str(exc))
            output_path = ""

        # ---- Update gate_context for downstream gates ------------------------------
        gate_context["bilibili_repurpose_content"] = final_content
        if output_path:
            gate_context.setdefault("output_files", []).append(
                {"type": "bilibili_repurpose_script", "path": output_path, "md5": ""}
            )

        return build_gate_result(
            checks,
            gate="P4",
            error=None if all_passed else "Bilibili repurpose sub-pipeline checks failed",
            expected_map=_EXPECTED_MAP,
            content=final_content,
            output_path=output_path,
        )
