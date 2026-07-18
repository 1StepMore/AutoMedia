"""Tests for MCP error protocol (mcp_error.py).

Covers MCPErrorCode enum, success_response, and error_response helpers.
All tests use synthetic data — zero production data.
"""

from __future__ import annotations

from automedia.mcp.mcp_error import MCPErrorCode, error_response, success_response

# ---------------------------------------------------------------------------
# MCPErrorCode
# ---------------------------------------------------------------------------


class TestMCPErrorCode:
    """Tests for the MCPErrorCode enum."""

    def test_enum_values_match_keys(self) -> None:
        """Each enum member has a value matching its name."""
        for member in MCPErrorCode:
            assert member.value == member.name, f"{member.name} should have value matching its name"

    def test_expected_members_present(self) -> None:
        """MCPErrorCode contains all expected error code members."""
        expected = {
            "INVALID_PARAM",
            "NOT_FOUND",
            "PIPELINE_ERROR",
            "ENGINE_ERROR",
            "ALLOWLIST_DENIED",
            "UNKNOWN",
        }
        actual = set(MCPErrorCode.__members__)
        assert actual == expected, f"Missing or extra members. Expected {expected}, got {actual}"

    def test_is_str_enum(self) -> None:
        """MCPErrorCode inherits from str and Enum, so members are strings."""
        for member in MCPErrorCode:
            assert isinstance(member, str)
            assert isinstance(member.value, str)

    def test_invalid_param_code(self) -> None:
        """INVALID_PARAM is present and usable as a string."""
        assert MCPErrorCode.INVALID_PARAM == "INVALID_PARAM"

    def test_not_found_code(self) -> None:
        """NOT_FOUND is present and usable as a string."""
        assert MCPErrorCode.NOT_FOUND == "NOT_FOUND"

    def test_unknown_code(self) -> None:
        """UNKNOWN is present and usable as a string."""
        assert MCPErrorCode.UNKNOWN == "UNKNOWN"

    def test_pipeline_error_code(self) -> None:
        """PIPELINE_ERROR is present and usable as a string."""
        assert MCPErrorCode.PIPELINE_ERROR == "PIPELINE_ERROR"

    def test_engine_error_code(self) -> None:
        """ENGINE_ERROR is present and usable as a string."""
        assert MCPErrorCode.ENGINE_ERROR == "ENGINE_ERROR"

    def test_allowlist_denied_code(self) -> None:
        """ALLOWLIST_DENIED is present and usable as a string."""
        assert MCPErrorCode.ALLOWLIST_DENIED == "ALLOWLIST_DENIED"


# ---------------------------------------------------------------------------
# success_response
# ---------------------------------------------------------------------------


class TestSuccessResponse:
    """Tests for the success_response helper."""

    def test_wraps_data_with_success_flag(self) -> None:
        """success_response wraps a dict with success=True."""
        result = success_response({"project_id": "abc123", "status": "ok"})
        assert result == {
            "success": True,
            "project_id": "abc123",
            "status": "ok",
        }

    def test_preserves_existing_success_key(self) -> None:
        """If data already has a 'success' key, it is returned as-is."""
        result = success_response({"success": False, "project_id": "abc123"})
        # Should not override existing success=False
        assert result == {"success": False, "project_id": "abc123"}

    def test_preserves_existing_success_true(self) -> None:
        """If data already has success=True, it is returned as-is (no duplication)."""
        result = success_response({"success": True, "data": "hello"})
        assert result == {"success": True, "data": "hello"}

    def test_empty_dict_becomes_success_true(self) -> None:
        """Passing an empty dict returns {success: True}."""
        result = success_response({})
        assert result == {"success": True}

    def test_works_with_nested_data(self) -> None:
        """success_response works with deeply nested data."""
        nested = {"items": [{"a": 1}, {"b": 2}], "meta": {"count": 2}}
        result = success_response(nested)
        assert result["success"] is True
        assert result["items"] == nested["items"]
        assert result["meta"] == nested["meta"]

    def test_multiple_keys_in_data(self) -> None:
        """All keys in the input dict are preserved in the output."""
        data = {"a": 1, "b": "two", "c": [3, 4, 5]}
        result = success_response(data)
        for key in data:
            assert result[key] == data[key]
        assert result["success"] is True


# ---------------------------------------------------------------------------
# error_response
# ---------------------------------------------------------------------------


class TestErrorResponse:
    """Tests for the error_response helper."""

    def test_returns_dict_with_success_false(self) -> None:
        """error_response always returns success=False."""
        result = error_response(MCPErrorCode.NOT_FOUND, "not found")
        assert result["success"] is False

    def test_returns_structured_error_with_code_message_resolution(self) -> None:
        """error_response returns error dict with code, message, resolution."""
        result = error_response(
            MCPErrorCode.INVALID_PARAM,
            "Invalid parameter 'mode'",
            "Choose from: auto, text_only",
        )
        error = result["error"]
        assert error["code"] == "INVALID_PARAM"
        assert error["message"] == "Invalid parameter 'mode'"
        assert error["resolution"] == "Choose from: auto, text_only"

    def test_accepts_plain_string_code(self) -> None:
        """error_response accepts a plain string as error code."""
        result = error_response("CUSTOM_ERROR", "Something went wrong")
        assert result["error"]["code"] == "CUSTOM_ERROR"

    def test_accepts_mcp_error_code_enum(self) -> None:
        """error_response accepts MCPErrorCode enum members."""
        result = error_response(MCPErrorCode.UNKNOWN, "Unknown error")
        assert result["error"]["code"] == "UNKNOWN"

    def test_without_resolution_uses_default(self) -> None:
        """error_response without resolution falls back to a generic message."""
        result = error_response(MCPErrorCode.NOT_FOUND, "Resource not found")
        assert result["error"]["resolution"] == "See documentation or contact support"

    def test_with_empty_resolution_uses_default(self) -> None:
        """error_response with empty resolution string falls back to generic."""
        result = error_response(MCPErrorCode.UNKNOWN, "fail", resolution="")
        assert result["error"]["resolution"] == "See documentation or contact support"

    def test_with_none_resolution(self) -> None:
        """error_response defaults resolution when omitted."""
        # resolution defaults to ""
        result = error_response(MCPErrorCode.UNKNOWN, "fail")
        assert result["error"]["resolution"] == "See documentation or contact support"

    def test_with_explicit_resolution_empty_string(self) -> None:
        """Passing resolution='' explicitly still uses default."""
        result = error_response(MCPErrorCode.UNKNOWN, "fail", resolution="")
        assert result["error"]["resolution"] == "See documentation or contact support"

    def test_backward_compat_has_error_message_key(self) -> None:
        """error_response response has error_message key for backward compat."""
        result = error_response(MCPErrorCode.NOT_FOUND, "not found")
        # error_message is present and equals the message
        assert "error_message" in result
        assert result["error_message"] == "not found"

    def test_error_message_matches_error_message_field(self) -> None:
        """error_message key matches the error.message field."""
        result = error_response(MCPErrorCode.INVALID_PARAM, "bad input", "fix it")
        assert result["error_message"] == result["error"]["message"]

    def test_has_success_and_error_and_message_keys(self) -> None:
        """Response dict has all expected top-level keys."""
        result = error_response(MCPErrorCode.UNKNOWN, "fail")
        assert "success" in result
        assert "error" in result
        assert "error_message" in result

    def test_resolution_is_optional_parameter(self) -> None:
        """resolution parameter defaults to empty string (then to generic)."""
        # Should not raise TypeError — resolution is optional
        result = error_response(MCPErrorCode.NOT_FOUND, "nope")
        assert result["error"]["resolution"] == "See documentation or contact support"
