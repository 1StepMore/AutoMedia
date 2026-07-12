"""Tests for CookieAuth — cookie-based authentication handler."""

from __future__ import annotations

from automedia.accounts.auth.cookie import CookieAuth


class TestCookieAuth:
    """Cookie validation."""

    def test_valid_cookie_with_equals(self) -> None:
        """Cookie containing '=' is considered valid."""
        assert CookieAuth.validate_cookie("session=abc123; token=def456") is True

    def test_empty_string_invalid(self) -> None:
        """Empty cookie string is invalid."""
        assert CookieAuth.validate_cookie("") is False
        assert CookieAuth.validate_cookie("   ") is False

    def test_none_invalid(self) -> None:
        """None-like empty values are invalid."""
        assert CookieAuth.validate_cookie("") is False

    def test_no_equals_invalid(self) -> None:
        """Cookie without '=' is invalid under format check."""
        assert CookieAuth.validate_cookie("justastring") is False

    def test_single_key_value(self) -> None:
        """Single key=value pair is valid."""
        assert CookieAuth.validate_cookie("key=value") is True

    def test_with_health_check_passing(self) -> None:
        """Health check that returns True makes cookie valid."""
        assert CookieAuth.validate_cookie(
            "session=valid", health_check_fn=lambda c: True
        ) is True

    def test_with_health_check_failing(self) -> None:
        """Health check that returns False makes cookie invalid."""
        assert CookieAuth.validate_cookie(
            "session=valid", health_check_fn=lambda c: False
        ) is False

    def test_with_health_check_raising(self) -> None:
        """Health check that raises logs warning and returns False."""

        def _failing(c: str) -> bool:
            raise ConnectionError("API unreachable")

        assert (
            CookieAuth.validate_cookie("session=valid", health_check_fn=_failing)
            is False
        )
