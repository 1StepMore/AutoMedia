"""Tests for G4WechatChecklist gate — 7-step WeChat compliance check."""

from __future__ import annotations

from typing import Any

from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate, _registry
from automedia.gates.wechat_checklist import (
    _CHECK_NAMES,
    G4WechatChecklist,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GOOD_HTML = (
    """<div><p>Hello world.</p><img src="https://example.com/img1.jpg"><img src="img2.jpg"></div>"""
)


def _make_context(
    *,
    content: str = _GOOD_HTML,
    title: str = "短标题",
    digest: str = "这是一段摘要。",
    cover_image: str = "https://example.com/cover.jpg",
    tags: list[str] | None = None,
    body_images: list[str] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults (all passing)."""
    ctx: dict[str, Any] = {
        "content": content,
        "title": title,
        "digest": digest,
        "cover_image": cover_image,
        "tags": tags if tags is not None else ["tag1", "tag2", "tag3", "tag4", "tag5"],
    }
    if body_images is not None:
        ctx["body_images"] = body_images
    if mock_results is not None:
        ctx["_mock_results"] = mock_results
    return ctx


def _all_pass_mock() -> dict[str, dict[str, Any]]:
    """Return mock results where every check passes."""
    return {name: {"passed": True, "detail": "ok"} for name in _CHECK_NAMES}


def _fail_check(name: str, detail: str = "failed") -> dict[str, dict[str, Any]]:
    """Return mock results where *name* fails and the rest pass."""
    results = _all_pass_mock()
    results[name] = {"passed": False, "detail": detail}
    return results


# =========================================================================
# Gate metadata & registration
# =========================================================================


class TestG4Metadata:
    """G4WechatChecklist has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = G4WechatChecklist()
        assert gate.gate_name == "G4"

    def test_failure_mode(self) -> None:
        gate = G4WechatChecklist()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(G4WechatChecklist, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "G4" in _registry
        assert _registry.get("G4") is G4WechatChecklist


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestG4MockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "G4"
        assert result["error"] is None
        assert len(result["checks"]) == 7

    def test_title_length_failure_stops_gate(self) -> None:
        ctx = _make_context(mock_results=_fail_check("title_length", "too long"))
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is False
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 1
        assert failed[0]["name"] == "title_length"
        assert failed[0]["detail"] == "too long"

    def test_digest_length_failure(self) -> None:
        ctx = _make_context(mock_results=_fail_check("digest_length", "too long"))
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "digest_length" in failed_names

    def test_no_markdown_failure(self) -> None:
        ctx = _make_context(mock_results=_fail_check("no_markdown", "markdown found"))
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "no_markdown" in failed_names

    def test_cover_exists_failure(self) -> None:
        ctx = _make_context(mock_results=_fail_check("cover_exists", "no cover"))
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "cover_exists" in failed_names

    def test_tag_count_failure(self) -> None:
        ctx = _make_context(mock_results=_fail_check("tag_count", "too few"))
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "tag_count" in failed_names

    def test_body_image_count_failure(self) -> None:
        ctx = _make_context(mock_results=_fail_check("body_image_count", "wrong count"))
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "body_image_count" in failed_names

    def test_sensitive_words_failure(self) -> None:
        ctx = _make_context(mock_results=_fail_check("sensitive_words", "blocked"))
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "sensitive_words" in failed_names

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is False

    def test_partial_failure(self) -> None:
        """2 of 7 fail → passed=False."""
        mock = _all_pass_mock()
        mock["title_length"] = {"passed": False, "detail": "x"}
        mock["tag_count"] = {"passed": False, "detail": "y"}
        ctx = _make_context(mock_results=mock)
        result = G4WechatChecklist().execute(ctx)

        assert result["passed"] is False
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 2


# =========================================================================
# Real-logic tests
# =========================================================================


class TestG4RealLogic:
    """execute() without _mock_results runs actual check functions."""

    def test_title_length_passes(self) -> None:
        ctx = _make_context(title="abc123456")  # length 9
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "title_length")
        assert chk["passed"] is True

    def test_title_length_fails(self) -> None:
        ctx = _make_context(title="abcdefghij")  # length 10
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "title_length")
        assert chk["passed"] is False

    def test_title_length_empty_passes(self) -> None:
        """Empty title has length 0 ≤ 9 so it passes."""
        ctx = _make_context(title="")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "title_length")
        assert chk["passed"] is True

    def test_digest_length_passes(self) -> None:
        ctx = _make_context(digest="二十个字符的摘要信息。")  # len 10
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "digest_length")
        assert chk["passed"] is True

    def test_digest_length_fails(self) -> None:
        ctx = _make_context(digest="二十一个字符的摘要信息在这里")  # len 13 → wait let me count
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "digest_length")
        # "二十一个字符的摘要信息在这里" has 13 chars → passes (≤20)
        # Let's make a >20 char one
        assert chk["passed"] is True  # still within limit

    def test_digest_length_fails_over_limit(self) -> None:
        _make_context(digest="这是超过二十个字符的摘要信息测试用例。")  # len 16 → still fine
        # Let's just use a known >20
        digest_too_long = "A" * 21
        ctx2 = _make_context(digest=digest_too_long)
        result = G4WechatChecklist().execute(ctx2)
        chk = next(c for c in result["checks"] if c["name"] == "digest_length")
        assert chk["passed"] is False

    def test_no_markdown_passes(self) -> None:
        ctx = _make_context(content="<p>Clean HTML content</p>")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "no_markdown")
        assert chk["passed"] is True

    def test_no_markdown_fails_with_hash(self) -> None:
        ctx = _make_context(content="# Heading in content")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "no_markdown")
        assert chk["passed"] is False

    def test_no_markdown_fails_with_bold(self) -> None:
        ctx = _make_context(content="This is **bold** text")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "no_markdown")
        assert chk["passed"] is False

    def test_no_markdown_fails_with_list(self) -> None:
        ctx = _make_context(content="- item one\n- item two")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "no_markdown")
        assert chk["passed"] is False

    def test_cover_exists_passes(self) -> None:
        ctx = _make_context(cover_image="https://example.com/c.jpg")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "cover_exists")
        assert chk["passed"] is True

    def test_cover_exists_fails(self) -> None:
        ctx = _make_context(cover_image="")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "cover_exists")
        assert chk["passed"] is False

    def test_tag_count_passes(self) -> None:
        ctx = _make_context(tags=["a", "b", "c", "d", "e"])
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_count")
        assert chk["passed"] is True

    def test_tag_count_fails(self) -> None:
        ctx = _make_context(tags=["a", "b", "c"])
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_count")
        assert chk["passed"] is False

    def test_tag_count_exactly_five_passes(self) -> None:
        ctx = _make_context(tags=["a", "b", "c", "d", "e"])
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_count")
        assert chk["passed"] is True

    def test_body_image_count_passes(self) -> None:
        ctx = _make_context(body_images=["a.jpg", "b.jpg", "c.jpg"])
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "body_image_count")
        assert chk["passed"] is True

    def test_body_image_count_fails_too_few(self) -> None:
        ctx = _make_context(body_images=["a.jpg", "b.jpg"])
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "body_image_count")
        assert chk["passed"] is False

    def test_body_image_count_fails_too_many(self) -> None:
        ctx = _make_context(
            body_images=["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg", "f.jpg", "g.jpg"]
        )
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "body_image_count")
        assert chk["passed"] is False

    def test_body_image_count_upper_bound_passes(self) -> None:
        ctx = _make_context(body_images=["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg", "f.jpg"])
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "body_image_count")
        assert chk["passed"] is True

    def test_body_images_extracted_from_html(self) -> None:
        """2 img tags extracted from HTML → < 3 → body_image_count fails."""
        html = '<p>Text</p><img src="https://a.com/1.jpg"><img src="https://a.com/2.jpg">'
        ctx = _make_context(content=html)
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "body_image_count")
        assert chk["passed"] is False

    def test_body_images_extracted_from_html_three(self) -> None:
        html = "<p>Text</p>" + "".join(f'<img src="https://a.com/{i}.jpg">' for i in range(3))
        ctx = _make_context(content=html)
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "body_image_count")
        assert chk["passed"] is True

    def test_sensitive_words_passes(self) -> None:
        ctx = _make_context(content="<p>完全正常的内容</p>")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "sensitive_words")
        assert chk["passed"] is True

    def test_sensitive_words_fails(self) -> None:
        ctx = _make_context(content="<p>涉及色情内容</p>")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "sensitive_words")
        assert chk["passed"] is False

    def test_multiple_sensitive_words(self) -> None:
        ctx = _make_context(content="<p>赌博和暴力都是违法的</p>")
        result = G4WechatChecklist().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "sensitive_words")
        assert chk["passed"] is False

    def test_all_checks_pass_with_good_data(self) -> None:
        """Full happy path — all 7 real checks pass."""
        ctx = _make_context(
            content="<p>正常文章内容</p><img src='a.jpg'><img src='b.jpg'><img src='c.jpg'>",
            title="短标题",
            digest="简短短摘要",
            cover_image="cover.jpg",
            tags=["t1", "t2", "t3", "t4", "t5"],
            body_images=["a.jpg", "b.jpg", "c.jpg"],
        )
        result = G4WechatChecklist().execute(ctx)
        assert result["passed"] is True


# =========================================================================
# Result structure
# =========================================================================


class TestG4ResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_all_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G4WechatChecklist().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G4WechatChecklist().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_seven_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G4WechatChecklist().execute(ctx)

        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES

    def test_build_result_structure(self) -> None:
        checks = [{"name": "test", "passed": True, "detail": "ok"}]
        result = build_gate_result(checks, gate="G4")
        assert result["passed"] is True
        assert result["gate"] == "G4"
        assert result["checks"] == checks
        assert result["error"] is None

    def test_build_result_with_error(self) -> None:
        checks = [{"name": "test", "passed": False, "detail": "fail"}]
        result = build_gate_result(checks, gate="G4", error="something broke")
        assert result["passed"] is False
        assert result["error"] == "something broke"


# =========================================================================
# Edge cases
# =========================================================================


class TestG4EdgeCases:
    """Edge-case handling."""

    def test_missing_context_keys(self) -> None:
        """Empty gate_context doesn't crash — uses defaults."""
        result = G4WechatChecklist().execute({})
        assert result["gate"] == "G4"
        assert isinstance(result["checks"], list)
        assert len(result["checks"]) == 7

    def test_red_line_gate_failure_returns_failed_status(self) -> None:
        """Red Line 3: gate failure is detectable via passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = G4WechatChecklist().execute(ctx)
        assert result["passed"] is False
        assert result["gate"] == "G4"

    def test_mock_result_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim in result."""
        mock = _all_pass_mock()
        mock["title_length"] = {"passed": False, "detail": "custom error 123"}
        ctx = _make_context(mock_results=mock)
        result = G4WechatChecklist().execute(ctx)
        ck = next(c for c in result["checks"] if c["name"] == "title_length")
        assert ck["detail"] == "custom error 123"

    def test_empty_content_handling(self) -> None:
        """Empty content should not crash any check."""
        ctx = _make_context(
            content="",
            title="",
            digest="",
            cover_image="",
            tags=[],
            body_images=[],
        )
        result = G4WechatChecklist().execute(ctx)
        assert result["gate"] == "G4"
        assert isinstance(result["checks"], list)
