"""Tests for G5HtmlHard gate — structural HTML integrity checks."""

from __future__ import annotations

from typing import Any

from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate, _registry
from automedia.gates.html_hard import (
    _CHECK_NAMES,
    G5HtmlHard,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GOOD_HTML = """<html><head><title>Test</title></head><body><div><p>Hello</p></div></body></html>"""


def _make_context(
    *,
    content: str = _GOOD_HTML,
    tags: list[str] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults (all passing)."""
    ctx: dict[str, Any] = {
        "content": content,
        "tags": tags if tags is not None else ["tag1", "tag2", "tag3", "tag4", "tag5"],
    }
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


class TestG5Metadata:
    """G5HtmlHard has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = G5HtmlHard()
        assert gate.gate_name == "G5"

    def test_failure_mode(self) -> None:
        gate = G5HtmlHard()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(G5HtmlHard, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "G5" in _registry
        assert _registry.get("G5") is G5HtmlHard


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestG5MockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G5HtmlHard().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "G5"
        assert result["error"] is None
        assert len(result["checks"]) == 3

    def test_tag_integrity_failure_stops_gate(self) -> None:
        ctx = _make_context(mock_results=_fail_check("tag_integrity", "mismatch"))
        result = G5HtmlHard().execute(ctx)

        assert result["passed"] is False
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 1
        assert failed[0]["name"] == "tag_integrity"
        assert failed[0]["detail"] == "mismatch"

    def test_no_markdown_failure(self) -> None:
        ctx = _make_context(mock_results=_fail_check("no_markdown", "markdown found"))
        result = G5HtmlHard().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "no_markdown" in failed_names

    def test_tag_count_failure(self) -> None:
        ctx = _make_context(mock_results=_fail_check("tag_count", "too few"))
        result = G5HtmlHard().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "tag_count" in failed_names

    def test_all_checks_fail(self) -> None:
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = G5HtmlHard().execute(ctx)

        assert result["passed"] is False

    def test_partial_failure(self) -> None:
        """2 of 3 fail → passed=False."""
        mock = _all_pass_mock()
        mock["tag_integrity"] = {"passed": False, "detail": "x"}
        mock["tag_count"] = {"passed": False, "detail": "y"}
        ctx = _make_context(mock_results=mock)
        result = G5HtmlHard().execute(ctx)

        assert result["passed"] is False
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 2


# =========================================================================
# Real-logic tests
# =========================================================================


class TestG5RealLogic:
    """execute() without _mock_results runs actual check functions."""

    def test_tag_integrity_passes_with_well_formed_html(self) -> None:
        html = "<html><body><div><p>text</p></div></body></html>"
        ctx = _make_context(content=html)
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_integrity")
        assert chk["passed"] is True

    def test_tag_integrity_fails_with_mismatched_tags(self) -> None:
        """Unclosed <span> causes tag count mismatch."""
        html = "<div><p>text</p></div><span>unclosed"
        ctx = _make_context(content=html)
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_integrity")
        assert chk["passed"] is False

    def test_tag_integrity_fails_with_unclosed_tag(self) -> None:
        html = "<div><p>text</div>"
        ctx = _make_context(content=html)
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_integrity")
        assert chk["passed"] is False

    def test_tag_integrity_void_tags_ignored(self) -> None:
        """Self-closing tags like <br>, <img>, <hr> are excluded from counting."""
        html = "<div><p>Line1<br>Line2<br>Line3</p></div>"
        ctx = _make_context(content=html)
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_integrity")
        assert chk["passed"] is True

    def test_tag_integrity_empty_content_passes(self) -> None:
        ctx = _make_context(content="")
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_integrity")
        assert chk["passed"] is True

    def test_no_markdown_passes_with_clean_html(self) -> None:
        ctx = _make_context(content="<p>Clean HTML</p>")
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "no_markdown")
        assert chk["passed"] is True

    def test_no_markdown_fails_with_hash(self) -> None:
        ctx = _make_context(content="# Heading in HTML")
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "no_markdown")
        assert chk["passed"] is False

    def test_no_markdown_fails_with_bold(self) -> None:
        ctx = _make_context(content="This is **bold**")
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "no_markdown")
        assert chk["passed"] is False

    def test_no_markdown_fails_with_list(self) -> None:
        ctx = _make_context(content="- item one\n- item two")
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "no_markdown")
        assert chk["passed"] is False

    def test_tag_count_passes(self) -> None:
        ctx = _make_context(tags=["a", "b", "c", "d", "e"])
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_count")
        assert chk["passed"] is True

    def test_tag_count_fails(self) -> None:
        ctx = _make_context(tags=["a", "b"])
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_count")
        assert chk["passed"] is False

    def test_tag_count_exactly_five_passes(self) -> None:
        ctx = _make_context(tags=["a", "b", "c", "d", "e"])
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_count")
        assert chk["passed"] is True

    def test_tag_count_empty_fails(self) -> None:
        ctx = _make_context(tags=[])
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_count")
        assert chk["passed"] is False

    def test_all_checks_pass_with_good_data(self) -> None:
        """Full happy path — all 3 real checks pass."""
        ctx = _make_context(
            content="<html><body><p>Good HTML</p><br><img src='a.jpg'></body></html>",
            tags=["t1", "t2", "t3", "t4", "t5"],
        )
        result = G5HtmlHard().execute(ctx)
        assert result["passed"] is True


# =========================================================================
# Result structure
# =========================================================================


class TestG5ResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_all_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G5HtmlHard().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G5HtmlHard().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_three_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = G5HtmlHard().execute(ctx)

        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES

    def test_build_result_structure(self) -> None:
        checks = [{"name": "test", "passed": True, "detail": "ok"}]
        result = build_gate_result(checks, gate="G5", expected_suffix=".")
        assert result["passed"] is True
        assert result["gate"] == "G5"
        assert result["checks"] == checks
        assert result["error"] is None

    def test_build_result_with_error(self) -> None:
        checks = [{"name": "test", "passed": False, "detail": "fail"}]
        result = build_gate_result(checks, gate="G5", expected_suffix=".", error="oops")
        assert result["passed"] is False
        assert result["error"] == "oops"


# =========================================================================
# Edge cases
# =========================================================================


class TestG5EdgeCases:
    """Edge-case handling."""

    def test_missing_context_keys(self) -> None:
        """Empty gate_context doesn't crash — uses defaults."""
        result = G5HtmlHard().execute({})
        assert result["gate"] == "G5"
        assert isinstance(result["checks"], list)
        assert len(result["checks"]) == 3

    def test_mock_result_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim in result."""
        mock = _all_pass_mock()
        mock["tag_integrity"] = {"passed": False, "detail": "custom error 456"}
        ctx = _make_context(mock_results=mock)
        result = G5HtmlHard().execute(ctx)
        ck = next(c for c in result["checks"] if c["name"] == "tag_integrity")
        assert ck["detail"] == "custom error 456"

    def test_empty_content_does_not_crash(self) -> None:
        """Empty content should not crash any check."""
        ctx = _make_context(content="", tags=[])
        result = G5HtmlHard().execute(ctx)
        assert result["gate"] == "G5"
        assert isinstance(result["checks"], list)

    def test_complex_nested_html_passes(self) -> None:
        """Properly nested complex HTML passes tag_integrity."""
        html = """<html>
            <head><title>Test</title><meta charset="utf-8"></head>
            <body>
                <div class="content">
                    <h1>Title</h1>
                    <p>Paragraph <strong>bold</strong> <em>italic</em></p>
                    <ul><li>Item 1</li><li>Item 2</li></ul>
                </div>
            </body>
        </html>"""
        ctx = _make_context(content=html)
        result = G5HtmlHard().execute(ctx)
        chk = next(c for c in result["checks"] if c["name"] == "tag_integrity")
        assert chk["passed"] is True
