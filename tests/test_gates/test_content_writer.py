"""Tests for CW — Content Writer Gate.

Covers ``ContentWriterGate.execute()`` with:
- Happy path (minimal valid gate_context)
- Empty topic (edge case)
- Missing brand configuration (edge case)
- Missing project directory (edge case)
- LLM failure scenario
- Gate metadata and registry registration
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

from automedia.gates.base import BaseGate, _registry
from automedia.gates.content_writer import ContentWriterGate
from tests.fixtures.synth.gate_contexts import load_brand_profile

# =========================================================================
# Constants
# =========================================================================

MOCK_ARTICLE: str = (
    "# AI Technology Trends in 2025\n\n"
    "Artificial intelligence continues to transform industries worldwide. "
    "In 2025, we see several key trends emerging.\n\n"
    "## Key Trends\n\n"
    "1. **Generative AI** becomes mainstream in enterprise workflows.\n"
    "2. **AI regulation** takes shape globally.\n"
    "3. **Edge AI** brings intelligence to IoT devices.\n\n"
    "## Conclusion\n\n"
    "Businesses that embrace these trends will stay ahead of the curve."
)

# =========================================================================
# Helpers
# =========================================================================


def _make_context(
    *,
    topic: str = "AI technology trends in 2025",
    brand: str = "testbrand",
    project_dir: str | None = None,
    config: dict[str, Any] | None = None,
    brand_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal gate_context dict with sensible defaults."""
    ctx: dict[str, Any] = {
        "topic": topic,
        "brand": brand,
    }
    if project_dir is not None:
        ctx["project_dir"] = project_dir
    if config is not None:
        ctx["config"] = config
    if brand_profile is not None:
        ctx["brand_profile"] = brand_profile
    return ctx


def _minimal_config() -> dict[str, Any]:
    """Minimal LLM config for mocked test — never contacts a real LLM."""
    return {
        "llm": {
            "text_generation": {
                "provider": "test",
                "model": "test-model",
                "api_key": "test-key",
            }
        }
    }


# =========================================================================
# Gate metadata & registration
# =========================================================================


class TestCWMetadata:
    """ContentWriterGate has correct gate metadata and is auto-registered."""

    def test_gate_name(self) -> None:
        gate = ContentWriterGate()
        assert gate.gate_name == "CW"

    def test_failure_mode(self) -> None:
        gate = ContentWriterGate()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(ContentWriterGate, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "CW" in _registry
        assert _registry.get("CW") is ContentWriterGate


# =========================================================================
# ContentWriterGate.execute()
# =========================================================================


class TestExecute:
    """ContentWriterGate.execute() behavior for various input conditions."""

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_happy_path(self, tmp_path: Path) -> None:
        """Minimal valid gate_context produces a draft file with content.

        Verifies the full round-trip:
        - LLM is called with the correct topic/brand
        - Returned dict has ``passed=True``, ``content``, ``output_path``
        - Draft file is written to ``project_dir/01_content/drafts/``
        - ``gate_context`` is updated with content and output_files for
          downstream gates
        """
        ctx = _make_context(
            project_dir=str(tmp_path),
            config=_minimal_config(),
            brand_profile=load_brand_profile("testbrand"),
        )
        gate = ContentWriterGate()

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=MOCK_ARTICLE,
        ) as mock_llm:
            result = gate.execute(ctx)

        # --- Result structure ---
        assert result["passed"] is True, f"Expected passed=True, got: {result}"
        assert result["gate"] == "CW"
        assert result["content"] == MOCK_ARTICLE
        assert "output_path" in result

        # LLM was called with the topic and brand (article + SEO scoring = 2 calls)
        assert mock_llm.call_count >= 2
        user_msg = mock_llm.call_args_list[0][0][0]
        assert "AI technology trends in 2025" in user_msg
        assert "testbrand" in user_msg

        # --- Draft file written to disk ---
        output_path: str = result["output_path"]
        assert output_path.startswith(str(tmp_path)), (
            f"output_path {output_path!r} should be under tmp_path {tmp_path!r}"
        )
        assert output_path.endswith("_draft.md"), (
            f"output_path {output_path!r} should end with _draft.md"
        )
        assert os.path.isfile(output_path)
        with open(output_path, encoding="utf-8") as f:
            assert f.read() == MOCK_ARTICLE

        # --- gate_context updated for downstream gates ---
        assert ctx["content"] == MOCK_ARTICLE
        assert len(ctx["output_files"]) == 1
        assert ctx["output_files"][0] == {
            "type": "article",
            "path": output_path,
            "md5": "",
        }

    # ------------------------------------------------------------------
    # Brand CTA principles
    # ------------------------------------------------------------------

    def test_cta_principles_injected_into_writer_prompt(self, tmp_path: Path) -> None:
        """``brand_profile["cta_principles"]`` guides the call-to-action in the prompt.

        中文说明：健康度整改（P1-3）之前 ``cta_principles`` 有设定却无消费者。
        CW 门现在把它注入写作 prompt —— 这是「指导 CTA 怎么写」的本意，且
        进入 prompt 即确定性生效，无假停机风险。
        """
        ctx = _make_context(
            project_dir=str(tmp_path),
            config=_minimal_config(),
            brand_profile={
                "voice": "warm",
                "cta_principles": ["Lead with the benefit", "Never use urgency"],
            },
        )
        gate = ContentWriterGate()

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=MOCK_ARTICLE,
        ) as mock_llm:
            result = gate.execute(ctx)

        assert result["passed"] is True, f"Expected passed=True, got: {result}"
        user_msg = mock_llm.call_args_list[0][0][0]
        assert "Lead with the benefit" in user_msg
        assert "Never use urgency" in user_msg

    def test_no_cta_principles_means_no_prompt_section(self, tmp_path: Path) -> None:
        """Given no ``cta_principles``, When writing, Then the CTA section is absent."""
        ctx = _make_context(
            project_dir=str(tmp_path),
            config=_minimal_config(),
            brand_profile={"voice": "warm"},
        )
        gate = ContentWriterGate()

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=MOCK_ARTICLE,
        ) as mock_llm:
            result = gate.execute(ctx)

        assert result["passed"] is True, f"Expected passed=True, got: {result}"
        user_msg = mock_llm.call_args_list[0][0][0]
        assert "Brand tone/voice: warm" in user_msg
        assert "CTA principles" not in user_msg

    def test_cta_principles_tolerates_yaml_mapping_entries(self, tmp_path: Path) -> None:
        """A mapping entry (unquoted colon in YAML) is rendered, not crashed on.

        中文说明：``- Use action verbs: 立即体验`` 这类未加引号的行会被 YAML 解析成
        mapping 而非字符串（synth fixture ``testbrand.yaml`` 就是如此）。门必须
        照常渲染该条原则，而不是抛 ``TypeError`` 或悄悄丢掉它。
        """
        ctx = _make_context(
            project_dir=str(tmp_path),
            config=_minimal_config(),
            brand_profile={
                "cta_principles": [
                    "Link to product demo page",
                    {"Use action verbs": "立即体验, 免费试用"},
                ]
            },
        )
        gate = ContentWriterGate()

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=MOCK_ARTICLE,
        ) as mock_llm:
            result = gate.execute(ctx)

        assert result["passed"] is True, f"Expected passed=True, got: {result}"
        user_msg = mock_llm.call_args_list[0][0][0]
        assert "Link to product demo page" in user_msg
        assert "Use action verbs: 立即体验, 免费试用" in user_msg

    # ------------------------------------------------------------------
    # Edge case: empty topic
    # ------------------------------------------------------------------

    def test_empty_topic(self, tmp_path: Path) -> None:
        """Empty ``topic`` returns ``passed=False`` with topic_present check.

        The gate should short-circuit before any LLM call or file write.
        """
        ctx = _make_context(
            topic="",
            project_dir=str(tmp_path),
            config=_minimal_config(),
        )
        gate = ContentWriterGate()

        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "CW"
        assert "topic" in result["error"].lower()
        assert result["expected_vs_actual"]["check"] == "topic_present"
        assert result["expected_vs_actual"]["actual"] == "topic is empty or missing"

    # ------------------------------------------------------------------
    # Edge case: missing project directory
    # ------------------------------------------------------------------

    def test_missing_project_dir(self) -> None:
        """Missing ``project_dir`` returns ``passed=False``.

        The gate short-circuits before any LLM call or file write.
        """
        ctx = _make_context(
            topic="AI trends",
            config=_minimal_config(),
            # project_dir intentionally omitted
        )
        gate = ContentWriterGate()

        result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "CW"
        assert "project_dir" in result["error"].lower()
        assert result["expected_vs_actual"]["check"] == "project_dir_present"

    # ------------------------------------------------------------------
    # Edge case: missing brand configuration
    # ------------------------------------------------------------------

    def test_missing_brand_config(self, tmp_path: Path) -> None:
        """Missing brand / config / brand_profile keys still works.

        The gate uses default empty values for brand and config, and
        ``llm_complete`` is only called with the topic information.
        """
        ctx: dict[str, Any] = {
            "topic": "AI technology trends in 2025",
            "project_dir": str(tmp_path),
        }
        gate = ContentWriterGate()

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=MOCK_ARTICLE,
        ) as mock_llm:
            result = gate.execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "CW"
        assert result["content"] == MOCK_ARTICLE

        # LLM was called with the topic (brand defaults to empty; article + SEO = 2 calls)
        assert mock_llm.call_count >= 2
        user_msg = mock_llm.call_args_list[0][0][0]
        assert "AI technology trends in 2025" in user_msg

        # Draft file was written
        assert os.path.isfile(result["output_path"])

    # ------------------------------------------------------------------
    # LLM failure
    # ------------------------------------------------------------------

    def test_llm_failure_returns_error(self, tmp_path: Path) -> None:
        """When ``llm_complete`` raises ``LLMError``, gate returns failure.

        This tests the error-handling path — the gate must not crash
        and must return a descriptive ``expected_vs_actual``.
        """
        from automedia.core.llm_client import LLMError

        ctx = _make_context(
            project_dir=str(tmp_path),
            config=_minimal_config(),
        )
        gate = ContentWriterGate()

        with patch(
            "automedia.gates.content_writer.llm_complete",
            side_effect=LLMError("Simulated API failure for testing"),
        ):
            result = gate.execute(ctx)

        assert result["passed"] is False
        assert result["gate"] == "CW"
        assert "LLM" in result["error"]
        assert result["expected_vs_actual"]["check"] == "llm_success"

    # ------------------------------------------------------------------
    # Writer system prompt override
    # ------------------------------------------------------------------

    def test_writer_system_prompt_override(self, tmp_path: Path) -> None:
        """When config has ``llm.writer.system_prompt``, it overrides the
        default prompt."""
        custom_prompt = "Custom system prompt for testing"
        ctx = _make_context(
            project_dir=str(tmp_path),
            config={
                "llm": {
                    "writer": {
                        "system_prompt": custom_prompt,
                    },
                    "text_generation": {
                        "provider": "test",
                        "model": "test-model",
                        "api_key": "test-key",
                    },
                }
            },
        )
        gate = ContentWriterGate()

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=MOCK_ARTICLE,
        ) as mock_llm:
            result = gate.execute(ctx)

        assert result["passed"] is True
        # System prompt should be the custom one
        _call_system_prompt = mock_llm.call_args_list[0][1].get("system_prompt")
        assert _call_system_prompt == custom_prompt, (
            f"Expected system_prompt={custom_prompt!r}, got {_call_system_prompt!r}"
        )


# =========================================================================
# Brand profile field injection (schema field names) — #149
# =========================================================================

_CTA_FORMS: tuple[str, ...] = (
    "立即注册",
    "立即体验",
    "免费试用",
    "免费领取",
    "扫码…了解更多",
    "点击…注册",
    "联系我们",
    "了解更多详情",
    "sign up",
    "learn more",
    "get started",
)


class TestBrandProfileFieldInjection:
    """CW must read brand fields by their schema names (#149).

    中文说明：``brand_profile`` 到达门里时是 ``asdict(BrandProfile)``，键名等于
    schema 字段名（``tone_guidelines`` / ``brand_identity``）。生成侧此前读的是
    不存在的 ``voice``，导致语气指引静默失效、``brand_identity`` 从未注入。
    """

    def _build_user_message(self, tmp_path: Path, brand_profile: dict[str, Any]) -> str:
        """Run CW with a mocked LLM and return the user message it was given."""
        ctx = _make_context(
            project_dir=str(tmp_path),
            config=_minimal_config(),
            brand_profile=brand_profile,
        )
        gate = ContentWriterGate()

        with patch(
            "automedia.gates.content_writer.llm_complete",
            return_value=MOCK_ARTICLE,
        ) as mock_llm:
            result = gate.execute(ctx)

        assert result["passed"] is True, f"Expected passed=True, got: {result}"
        return str(mock_llm.call_args_list[0][0][0])

    def test_schema_tone_and_identity_are_injected(self, tmp_path: Path) -> None:
        """``tone_guidelines`` and ``brand_identity`` reach the writer prompt."""
        user_msg = self._build_user_message(
            tmp_path,
            {
                "brand_name": "TestBrand",
                "tone_guidelines": "友好、口语化",
                "brand_identity": "菲律宾外卖平台",
            },
        )

        assert "友好、口语化" in user_msg
        assert "菲律宾外卖平台" in user_msg
        assert "Brand tone/voice: 友好、口语化" in user_msg
        assert "菲律宾外卖平台" in user_msg.split("Brand identity", 1)[-1]

    def test_legacy_voice_key_is_still_honoured(self, tmp_path: Path) -> None:
        """A profile without ``tone_guidelines`` falls back to legacy ``voice``."""
        user_msg = self._build_user_message(
            tmp_path,
            {"brand_name": "TestBrand", "voice": "老风格"},
        )

        assert "老风格" in user_msg
        assert "Brand tone/voice: 老风格" in user_msg

    def test_empty_fields_produce_no_empty_injection(self, tmp_path: Path) -> None:
        """Empty ``tone_guidelines`` / ``brand_identity`` inject nothing, no crash."""
        user_msg = self._build_user_message(
            tmp_path,
            {
                "brand_name": "TestBrand",
                "tone_guidelines": "",
                "brand_identity": "",
                "voice": "",
            },
        )

        assert "Brand tone" not in user_msg
        assert "Brand identity" not in user_msg
        for line in user_msg.splitlines():
            if line.startswith(("Brand tone", "Brand identity")):
                value = line.split(": ", 1)[-1] if ": " in line else ""
                assert value.strip(), f"empty brand field injected: {line!r}"

    def test_cta_forms_are_listed_verbatim(self, tmp_path: Path) -> None:
        """The accepted CTA forms are spelled out as literal prompt examples."""
        user_msg = self._build_user_message(tmp_path, {"brand_name": "TestBrand"})

        for form in _CTA_FORMS:
            assert form in user_msg, f"CTA form {form!r} missing from writer prompt"
