"""Tests: deprecated MCP alias tools emit DeprecationWarning.

Each deprecated alias must warn the caller while still functioning
identically to its replacement.
"""

from __future__ import annotations

import warnings

import pytest

from automedia.mcp.server import mcp_help
from automedia.mcp.tools import batch_run, engine_health, pool_add_topic


class TestPoolAddTopicDeprecation:
    """pool_add_topic → add_pool_topic"""

    def test_emits_deprecation_warning(self) -> None:
        """Calling pool_add_topic emits a DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="pool_add_topic is deprecated"):
            try:
                pool_add_topic("test", "test-cat")
            except Exception:
                pass

    def test_replacement_no_warning(self) -> None:
        """Calling add_pool_topic does NOT emit a DeprecationWarning."""
        from automedia.mcp.tools import add_pool_topic

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                add_pool_topic("test", "test-cat")
            except Exception:
                pass
            dep = [
                x
                for x in w
                if issubclass(x.category, DeprecationWarning)
                and ("pool_add_topic" in str(x.message) or "add_pool_topic" in str(x.message))
            ]
            assert len(dep) == 0, f"Unexpected alias DeprecationWarning(s): {dep}"


class TestBatchRunDeprecation:
    """batch_run → run_batch"""

    def test_emits_deprecation_warning(self) -> None:
        """Calling batch_run emits a DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="batch_run is deprecated"):
            try:
                batch_run(["test"], brand="test", mode="auto")
            except Exception:
                pass

    def test_replacement_no_warning(self) -> None:
        """Calling run_batch does NOT emit a DeprecationWarning."""
        from automedia.mcp.tools import run_batch

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                run_batch(["test"], brand="test", mode="auto")
            except Exception:
                pass
            dep = [
                x
                for x in w
                if issubclass(x.category, DeprecationWarning)
                and ("batch_run" in str(x.message) or "run_batch" in str(x.message))
            ]
            assert len(dep) == 0, f"Unexpected alias DeprecationWarning(s): {dep}"


class TestEngineHealthDeprecation:
    """engine_health → health_engine"""

    def test_emits_deprecation_warning(self) -> None:
        """Calling engine_health emits a DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="engine_health is deprecated"):
            try:
                engine_health()
            except Exception:
                pass

    def test_replacement_no_warning(self) -> None:
        """Calling health_engine does NOT emit a DeprecationWarning."""
        from automedia.mcp.tools import health_engine

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                health_engine()
            except Exception:
                pass
            dep = [
                x
                for x in w
                if issubclass(x.category, DeprecationWarning)
                and ("engine_health" in str(x.message) or "health_engine" in str(x.message))
            ]
            assert len(dep) == 0, f"Unexpected alias DeprecationWarning(s): {dep}"


class TestMcpHelpDeprecation:
    """mcp_help → help_mcp"""

    def test_emits_deprecation_warning(self) -> None:
        """Calling mcp_help emits a DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="mcp_help is deprecated"):
            try:
                mcp_help()
            except Exception:
                pass

    def test_replacement_no_warning(self) -> None:
        """Calling help_mcp does NOT emit a DeprecationWarning."""
        from automedia.mcp.server import help_mcp

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                help_mcp()
            except Exception:
                pass
            dep = [
                x
                for x in w
                if issubclass(x.category, DeprecationWarning)
                and ("mcp_help" in str(x.message) or "help_mcp" in str(x.message))
            ]
            assert len(dep) == 0, f"Unexpected alias DeprecationWarning(s): {dep}"
