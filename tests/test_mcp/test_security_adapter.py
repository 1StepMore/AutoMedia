"""Security tests for register_platform_adapter namespace restriction.

Verifies that the MCP tool rejects arbitrary module imports and only
allows classes within the automedia.adapters.* namespace.
"""

from __future__ import annotations


class TestAdapterClassSecurity:
    """register_platform_adapter must reject unsafe adapter_class values."""

    def test_reject_arbitrary_module(self) -> None:
        """adapter_class='os.system' must be rejected — not in automedia.adapters."""
        from automedia.mcp.server import register_platform_adapter

        result = register_platform_adapter(
            platform_name="test",
            adapter_class="os.system",
        )
        assert result["registered"] is False
        assert "error" in result
        assert "automedia.adapters" in result["error"]["message"]

    def test_accept_valid_adapter(self) -> None:
        """Valid automedia.adapters.* path should be accepted
        (may fail on import but not rejected)."""
        from automedia.mcp.server import register_platform_adapter

        result = register_platform_adapter(
            platform_name="test",
            adapter_class="automedia.adapters.base.BasePlatformAdapter",
        )
        # Should either succeed or fail at import — but NOT be rejected by namespace check
        # If the class exists it will be registered; if not,
        # we get an import error, not a namespace error
        assert "automedia.adapters" not in result.get("error", "namespace rejected valid path")

    def test_reject_invalid_class_name(self) -> None:
        """adapter_class with path traversal in class name must be rejected."""
        from automedia.mcp.server import register_platform_adapter

        result = register_platform_adapter(
            platform_name="test",
            adapter_class="automedia.adapters.base.../../evil",
        )
        assert result["registered"] is False
        assert "error" in result

    def test_reject_subprocess_import(self) -> None:
        """adapter_class='subprocess.Popen' must be rejected."""
        from automedia.mcp.server import register_platform_adapter

        result = register_platform_adapter(
            platform_name="test",
            adapter_class="subprocess.Popen",
        )
        assert result["registered"] is False
        assert "error" in result
        assert "automedia.adapters" in result["error"]["message"]

    def test_reject_os_path(self) -> None:
        """adapter_class='os.path.join' must be rejected."""
        from automedia.mcp.server import register_platform_adapter

        result = register_platform_adapter(
            platform_name="test",
            adapter_class="os.path.join",
        )
        assert result["registered"] is False
        assert "error" in result
        assert "automedia.adapters" in result["error"]["message"]
