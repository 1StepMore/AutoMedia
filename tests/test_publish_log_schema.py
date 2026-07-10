"""Tests for L1PublishLogSchema gate — JSON schema validation of publish_log."""

from __future__ import annotations

from typing import Any

from automedia.gates.base import BaseGate, _registry
from automedia.gates.publish_log_schema import _CHECK_NAMES, L1PublishLogSchema

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_context(
    *,
    publish_log: dict[str, Any] | None = None,
    mock_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a gate_context dict with sensible defaults."""
    ctx: dict[str, Any] = {
        "publish_log": publish_log
        if publish_log is not None
        else {
            "topic": "AI in Healthcare",
            "content": "AI is transforming healthcare...",
            "media_paths": ["/videos/intro.mp4", "/videos/main.mp4"],
            "platform": "wechat",
            "version": "1.0.0",
            "created_at": "2026-07-07T10:00:00",
        },
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


class TestL1Metadata:
    """L1PublishLogSchema has correct gate_name, failure_mode, and is registered."""

    def test_gate_name(self) -> None:
        gate = L1PublishLogSchema()
        assert gate.gate_name == "L1"

    def test_failure_mode(self) -> None:
        gate = L1PublishLogSchema()
        assert gate.failure_mode == "stop"

    def test_is_base_gate_subclass(self) -> None:
        assert issubclass(L1PublishLogSchema, BaseGate)

    def test_auto_registered_in_registry(self) -> None:
        assert "L1" in _registry
        assert _registry.get("L1") is L1PublishLogSchema


# =========================================================================
# Mock-driven execute() tests
# =========================================================================


class TestL1MockDriven:
    """execute() respects _mock_results for deterministic testing."""

    def test_all_checks_pass(self) -> None:
        """All 6 mock checks pass → overall passed=True."""
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L1PublishLogSchema().execute(ctx)

        assert result["passed"] is True
        assert result["gate"] == "L1"
        assert result["error"] is None
        assert len(result["checks"]) == 6

    def test_topic_present_failure_stops_gate(self) -> None:
        """topic_present failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("topic_present", "missing"))
        result = L1PublishLogSchema().execute(ctx)

        assert result["passed"] is False
        failed = [c for c in result["checks"] if not c["passed"]]
        assert len(failed) == 1
        assert failed[0]["name"] == "topic_present"
        assert failed[0]["detail"] == "missing"

    def test_platform_valid_failure(self) -> None:
        """platform_valid failure → overall passed=False."""
        ctx = _make_context(mock_results=_fail_check("platform_valid", "bad platform"))
        result = L1PublishLogSchema().execute(ctx)

        assert result["passed"] is False
        failed_names = [c["name"] for c in result["checks"] if not c["passed"]]
        assert "platform_valid" in failed_names

    def test_all_checks_fail(self) -> None:
        """All 6 checks fail → overall passed=False."""
        fail_all = {name: {"passed": False, "detail": "bad"} for name in _CHECK_NAMES}
        ctx = _make_context(mock_results=fail_all)
        result = L1PublishLogSchema().execute(ctx)

        assert result["passed"] is False
        assert all(not c["passed"] for c in result["checks"])


# =========================================================================
# Real-logic tests
# =========================================================================


class TestL1RealLogic:
    """execute() without _mock_results runs actual check functions."""

    def test_complete_publish_log_passes(self) -> None:
        """A fully valid publish_log passes all checks."""
        ctx = _make_context()
        result = L1PublishLogSchema().execute(ctx)
        assert result["passed"] is True

    def test_missing_topic_fails(self) -> None:
        """Missing topic field fails topic_present check."""
        ctx = _make_context(
            publish_log={
                "content": "some content",
                "media_paths": [],
                "platform": "wechat",
            }
        )
        result = L1PublishLogSchema().execute(ctx)
        tp = next(c for c in result["checks"] if c["name"] == "topic_present")
        assert tp["passed"] is False

    def test_empty_topic_fails(self) -> None:
        """Empty topic string fails topic_present check."""
        ctx = _make_context(
            publish_log={
                "topic": "   ",
                "content": "some content",
                "media_paths": [],
                "platform": "wechat",
            }
        )
        result = L1PublishLogSchema().execute(ctx)
        tp = next(c for c in result["checks"] if c["name"] == "topic_present")
        assert tp["passed"] is False

    def test_missing_content_fails(self) -> None:
        """Missing content field fails content_present check."""
        ctx = _make_context(
            publish_log={
                "topic": "Valid Topic",
                "media_paths": [],
                "platform": "weibo",
            }
        )
        result = L1PublishLogSchema().execute(ctx)
        cp = next(c for c in result["checks"] if c["name"] == "content_present")
        assert cp["passed"] is False

    def test_invalid_platform_fails(self) -> None:
        """Platform not in allowed list fails platform_valid check."""
        ctx = _make_context(
            publish_log={
                "topic": "Topic",
                "content": "Content",
                "media_paths": [],
                "platform": "linkedin",
            }
        )
        result = L1PublishLogSchema().execute(ctx)
        pv = next(c for c in result["checks"] if c["name"] == "platform_valid")
        assert pv["passed"] is False

    def test_media_paths_not_a_list_fails(self) -> None:
        """media_paths being a non-list fails media_paths_valid."""
        ctx = _make_context(
            publish_log={
                "topic": "Topic",
                "content": "Content",
                "media_paths": "not-a-list",
                "platform": "wechat",
            }
        )
        result = L1PublishLogSchema().execute(ctx)
        mv = next(c for c in result["checks"] if c["name"] == "media_paths_valid")
        assert mv["passed"] is False

    def test_media_paths_invalid_item_fails(self) -> None:
        """A media_paths entry that is an empty string fails."""
        ctx = _make_context(
            publish_log={
                "topic": "Topic",
                "content": "Content",
                "media_paths": ["valid.mp4", ""],
                "platform": "wechat",
            }
        )
        result = L1PublishLogSchema().execute(ctx)
        mv = next(c for c in result["checks"] if c["name"] == "media_paths_valid")
        assert mv["passed"] is False

    def test_empty_version_present_fails(self) -> None:
        """version present but empty fails version_valid."""
        ctx = _make_context(
            publish_log={
                "topic": "Topic",
                "content": "Content",
                "media_paths": [],
                "platform": "wechat",
                "version": "",
            }
        )
        result = L1PublishLogSchema().execute(ctx)
        vv = next(c for c in result["checks"] if c["name"] == "version_valid")
        assert vv["passed"] is False

    def test_valid_youtube_platform_passes(self) -> None:
        """youtube is a valid platform."""
        ctx = _make_context(
            publish_log={
                "topic": "Topic",
                "content": "Content",
                "media_paths": [],
                "platform": "youtube",
            }
        )
        result = L1PublishLogSchema().execute(ctx)
        pv = next(c for c in result["checks"] if c["name"] == "platform_valid")
        assert pv["passed"] is True


# =========================================================================
# Result structure
# =========================================================================


class TestL1ResultStructure:
    """Returned dict always has the expected keys and types."""

    def test_result_has_all_required_keys(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L1PublishLogSchema().execute(ctx)

        assert "passed" in result
        assert "gate" in result
        assert "checks" in result
        assert "error" in result

    def test_checks_have_correct_structure(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L1PublishLogSchema().execute(ctx)

        for check in result["checks"]:
            assert "name" in check
            assert "passed" in check
            assert "detail" in check
            assert isinstance(check["passed"], bool)
            assert isinstance(check["detail"], str)

    def test_all_six_checks_present(self) -> None:
        ctx = _make_context(mock_results=_all_pass_mock())
        result = L1PublishLogSchema().execute(ctx)

        check_names = [c["name"] for c in result["checks"]]
        assert check_names == _CHECK_NAMES


# =========================================================================
# Edge cases
# =========================================================================


class TestL1EdgeCases:
    """Edge-case handling."""

    def test_empty_context_does_not_crash(self) -> None:
        """Empty gate_context doesn't crash — uses defaults."""
        result = L1PublishLogSchema().execute({})
        assert result["gate"] == "L1"
        assert isinstance(result["checks"], list)
        # With empty context, all required fields are missing
        assert result["passed"] is False

    def test_missing_publish_log_uses_empty_dict(self) -> None:
        """Missing publish_log key is handled gracefully."""
        result = L1PublishLogSchema().execute({"some_other_key": 42})
        assert result["gate"] == "L1"
        assert result["passed"] is False

    def test_empty_media_paths_allowed(self) -> None:
        """Empty media_paths list is allowed."""
        ctx = _make_context(
            publish_log={
                "topic": "Topic",
                "content": "Content",
                "media_paths": [],
                "platform": "wechat",
            }
        )
        result = L1PublishLogSchema().execute(ctx)
        mv = next(c for c in result["checks"] if c["name"] == "media_paths_valid")
        assert mv["passed"] is True

    def test_mock_detail_propagated(self) -> None:
        """Mock detail strings appear verbatim in result."""
        mock = _all_pass_mock()
        mock["topic_present"] = {"passed": False, "detail": "custom error 999"}
        ctx = _make_context(mock_results=mock)
        result = L1PublishLogSchema().execute(ctx)
        tp = next(c for c in result["checks"] if c["name"] == "topic_present")
        assert tp["detail"] == "custom error 999"
