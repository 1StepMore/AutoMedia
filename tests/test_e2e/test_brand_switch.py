"""E2E: Brand profile switching — content, CTA & blocked words update end-to-end.

Verifies that swapping ``brand_profile`` in the pipeline context correctly
propagates through ContentWriterGate (CW) and G3BrandCTA (G3), producing
brand-appropriate content, call-to-action, and blocked-word enforcement.

PRD-1 M4: "切换 brand-profile.yaml 的 brand 名称后, 全链路内容、CTA、禁止词正确更新"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from automedia.gates.base import _registry
from automedia.pipelines.gate_engine import GateEngine

# ---------------------------------------------------------------------------
# Brand profile helpers
# ---------------------------------------------------------------------------


def _build_brand_profile(
    brand_name: str,
    cta_phrase: str,
    blocked_word: str,
) -> dict[str, Any]:
    """Build a synthetic brand profile dict with distinct identity markers.

    Parameters
    ----------
    brand_name:
        Primary brand name (e.g. ``"BrandA"``).
    cta_phrase:
        A call-to-action phrase unique to this brand (e.g. ``"立即下载A"``).
    blocked_word:
        A word that *must not* appear in content for this brand
        (e.g. ``"forbiddenA"``).
    """
    return {
        "brand_name": brand_name,
        "brand_aliases": [brand_name.upper(), brand_name.lower()],
        "brand_identity": "AI内容生产",
        "tone": "professional",
        "cta_principles": [
            f"Always use '{cta_phrase}' as the primary CTA",
            "Link to product demo",
        ],
        "blocked_words": [blocked_word],
    }


# Two distinct brand profiles — different name, CTA, and blocked word
BRAND_A: dict[str, Any] = _build_brand_profile("BrandA", "立即下载A", "forbiddenA")
BRAND_B: dict[str, Any] = _build_brand_profile("BrandB", "立即下载B", "forbiddenB")


# ---------------------------------------------------------------------------
# Mock content per brand
# ---------------------------------------------------------------------------

_CONTENT_A: str = (
    "# BrandA Leads the AI Content Revolution\n\n"
    "BrandA is transforming how teams produce content at scale.\n"
    "我们的 AI内容生产 平台让创作变得前所未有的简单。\n"
    "如果您想体验下一代创作工具，立即下载A，开始您的智能创作之旅！\n"
)

_CONTENT_B: str = (
    "# BrandB: Your AI Content Engine\n\n"
    "BrandB empowers creators with cutting-edge AI technology.\n"
    "作为 AI内容生产 领域的领导者，我们不断创新。\n"
    "不要错过这个机会，立即下载B，加入未来创作的行列！\n"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GATES_TO_TEST: list[str] = ["CW", "G3"]

# Sentinel to signal "do NOT include _mock_results in the context at all"
_OMIT_MOCK: dict[str, dict[str, Any]] = {}  # type: ignore[assignment]


def _build_gates(names: list[str]) -> list[Any]:
    """Instantiate registered gates by name in order."""
    import automedia.gates  # noqa: F401 — ensure all gates are registered

    return [_registry.get(n)() for n in names]


def _build_all_pass_mock_results() -> dict[str, dict[str, Any]]:
    """Return mock results dict where every G3 check passes.

    This lets us decouple G3 gate-pass/fail from content assertions and
    focus the test on brand-profile propagation through the pipeline.
    """
    _p = {"passed": True, "detail": "mock-pass"}
    return {
        name: _p
        for name in [
            "brand_name_present",
            "cta_present",
            "brand_identity",
            "blocked_words_absent",
            "cta_direction_sync",
            "bridge_sentence",
        ]
    }


def _build_pipeline_context(
    topic: str,
    brand_profile: dict[str, Any],
    mock_results: dict[str, dict[str, Any]] | None = None,
    project_dir: str = "/projects/test_brand_switch",
) -> dict[str, Any]:
    """Build a minimal pipeline context sufficient for CW + G3 gates.

    Only includes keys that ContentWriterGate and G3BrandCTA actually
    consume, keeping the test focused and fast.
    """
    ctx: dict[str, Any] = {
        # --- Shared ---
        "topic": topic,
        "project_dir": project_dir,
        "brand_profile": brand_profile,
        "source_data": {
            "url": "https://example.com/brand-content",
            "published_date": "2025-07-01T00:00:00+00:00",
        },
        # G3 also needs `content` but ContentWriterGate sets it;
        # provide a fallback in case CW is skipped
        "content": "",
    }

    # Include _mock_results only when caller explicitly provides them.
    # Use sentinel _OMIT_MOCK to exclude it entirely (so G3 runs real checks).
    if mock_results is not _OMIT_MOCK:
        ctx["_mock_results"] = (
            _build_all_pass_mock_results() if mock_results is None else mock_results
        )

    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestBrandSwitch:
    """End-to-end brand profile switching tests.

    Every test patches ``automedia.gates.content_writer.llm_complete`` so
    that **no real LLM calls** are made.  The mock returns brand-specific
    content that lets us verify the correct brand identity flows through
    the pipeline.
    """

    # ------------------------------------------------------------------
    # BrandA
    # ------------------------------------------------------------------

    def test_brand_a_content_and_cta(
        self,
        sample_topic: str,
        tmp_path: Path,
    ) -> None:
        """Pipeline with BrandA → output contains \"BrandA\" and \"立即下载A\",
        and does NOT contain \"BrandB\" or \"forbiddenB\"."""
        gates = _build_gates(_GATES_TO_TEST)
        engine = GateEngine(gates)
        ctx = _build_pipeline_context(
            sample_topic,
            BRAND_A,
            project_dir=str(tmp_path),
        )

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=_CONTENT_A,
        ):
            success, results = engine.run(ctx)

        # --- Pipeline outcome ---
        assert success is True, f"BrandA pipeline failed. Results: {results}"

        # --- ContentWriterGate produced content ---
        content: str = ctx.get("content", "")
        assert content, "ContentWriterGate should have set gate_context['content']"

        # BrandA content should contain BrandA markers
        assert "BrandA" in content, "BrandA content should mention 'BrandA'"
        assert "立即下载A" in content, "BrandA content should contain BrandA CTA '立即下载A'"

        # BrandA content must NOT contain BrandB markers
        assert "BrandB" not in content, "BrandA content should NOT mention 'BrandB'"
        assert "立即下载B" not in content, (
            "BrandA content should NOT contain BrandB CTA '立即下载B'"
        )

        # --- G3 gate passed ---
        g3_result = results[-1] if results else {}
        assert g3_result.get("passed") is True, (
            f"G3 gate should pass for BrandA. Result: {g3_result}"
        )

        # --- CW gate passed ---
        cw_result = results[0] if results else {}
        assert cw_result.get("passed") is True, (
            f"CW gate should pass for BrandA. Result: {cw_result}"
        )

    def test_brand_a_blocked_words_enforced(
        self,
        sample_topic: str,
        tmp_path: Path,
    ) -> None:
        """Content containing a Brand-A-blocked word fails G3.

        This verifies that ``blocked_words`` from the brand profile are
        actually checked by G3 (no ``_mock_results`` override).
        """
        forbidden_content: str = (
            "# BrandA Article\n\n"
            "BrandA is an AI内容生产 leader.\n"
            "This mentions forbiddenA which BrandA disallows.\n"
            "如果您想体验，立即下载A now.\n"
        )

        gates = _build_gates(["CW", "G3"])
        engine = GateEngine(gates)
        ctx = _build_pipeline_context(
            sample_topic,
            BRAND_A,
            # Intentionally omit _mock_results so G3 runs real checks
            mock_results=_OMIT_MOCK,
            project_dir=str(tmp_path),
        )

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=forbidden_content,
        ):
            _success, results = engine.run(ctx)

        # G3 should fail because forbiddenA appears in content
        g3_result = results[-1] if results else {}
        assert g3_result.get("passed") is False, (
            f"G3 should fail when content contains blocked word 'forbiddenA'. Result: {g3_result}"
        )
        # Verify the failing check is blocked_words_absent specifically
        blocked_check = next(
            (c for c in g3_result.get("checks", []) if c["name"] == "blocked_words_absent"),
            None,
        )
        assert blocked_check is not None, "Expected blocked_words_absent check in G3 results"
        assert blocked_check["passed"] is False, (
            "blocked_words_absent should fail for BrandA with 'forbiddenA' in content"
        )

    # ------------------------------------------------------------------
    # BrandB
    # ------------------------------------------------------------------

    def test_brand_b_content_and_cta(
        self,
        sample_topic: str,
        tmp_path: Path,
    ) -> None:
        """Pipeline with BrandB → output contains \"BrandB\" and \"立即下载B\",
        and does NOT contain \"BrandA\" or \"立即下载A\"."""
        gates = _build_gates(_GATES_TO_TEST)
        engine = GateEngine(gates)
        ctx = _build_pipeline_context(
            sample_topic,
            BRAND_B,
            project_dir=str(tmp_path),
        )

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=_CONTENT_B,
        ):
            success, results = engine.run(ctx)

        assert success is True, f"BrandB pipeline failed. Results: {results}"

        content: str = ctx.get("content", "")
        assert content, "ContentWriterGate should have set gate_context['content']"

        # BrandB content should contain BrandB markers
        assert "BrandB" in content, "BrandB content should mention 'BrandB'"
        assert "立即下载B" in content, "BrandB content should contain BrandB CTA '立即下载B'"

        # BrandB content must NOT contain BrandA markers
        assert "BrandA" not in content, "BrandB content should NOT mention 'BrandA'"
        assert "立即下载A" not in content, (
            "BrandB content should NOT contain BrandA CTA '立即下载A'"
        )

        # --- G3 gate passed ---
        g3_result = results[-1] if results else {}
        assert g3_result.get("passed") is True, (
            f"G3 gate should pass for BrandB. Result: {g3_result}"
        )

        # --- CW gate passed ---
        cw_result = results[0] if results else {}
        assert cw_result.get("passed") is True, (
            f"CW gate should pass for BrandB. Result: {cw_result}"
        )

    def test_brand_b_blocked_words_enforced(
        self,
        sample_topic: str,
        tmp_path: Path,
    ) -> None:
        """Content containing a Brand-B-blocked word fails G3.

        Confirms that BrandB's ``blocked_words`` list is independently
        enforced and separate from BrandA's.
        """
        forbidden_content: str = (
            "# BrandB Article\n\n"
            "BrandB is an AI内容生产 pioneer.\n"
            "This content mentions forbiddenB which BrandB does not allow.\n"
            "如果您想体验，立即下载B now.\n"
        )

        gates = _build_gates(["CW", "G3"])
        engine = GateEngine(gates)
        ctx = _build_pipeline_context(
            sample_topic,
            BRAND_B,
            # Intentionally omit _mock_results so G3 runs real checks
            mock_results=_OMIT_MOCK,
            project_dir=str(tmp_path),
        )

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=forbidden_content,
        ):
            _success, results = engine.run(ctx)

        g3_result = results[-1] if results else {}
        assert g3_result.get("passed") is False, (
            f"G3 should fail when content contains blocked word 'forbiddenB'. Result: {g3_result}"
        )
        blocked_check = next(
            (c for c in g3_result.get("checks", []) if c["name"] == "blocked_words_absent"),
            None,
        )
        assert blocked_check is not None
        assert blocked_check["passed"] is False, (
            "blocked_words_absent should fail for BrandB with 'forbiddenB' in content"
        )
