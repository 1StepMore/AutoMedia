"""Tests for ``automedia adapter list`` real/stub/json filters.

Covers the P1-1 platform-audit surface (plan: productization-roadmap-20260902,
todo 11): ``--real``, ``--stub``, ``--json`` on the deprecated-but-auditable
``adapter list`` command, backed by the existing
``AdapterRegistry.list_publishable_platforms()``.

The registry is a process-wide singleton; other tests may register extra
adapters or clear it.  These tests therefore never assert on a hard-coded
partition — they snapshot the registry's own real/stub split per test and
assert the CLI output matches it exactly.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner, Result

from automedia.adapters.registry import AdapterRegistry

runner = CliRunner()


def _invoke(*args: str) -> Result:
    """Invoke ``automedia adapter list`` with the given extra args."""
    return runner.invoke(_app(), ["adapter", "list", *args])


def _app() -> object:
    """Import the root CLI app lazily (keeps collection cheap)."""
    from automedia.cli.app import app

    return app


def _snapshot() -> tuple[list[str], list[str]]:
    """Return (real_names, stub_names) as the registry itself partitions them."""
    platforms = AdapterRegistry().list_publishable_platforms()
    real = sorted(p["name"] for p in platforms if not p["is_stub"])
    stub = sorted(p["name"] for p in platforms if p["is_stub"])
    return real, stub


# =========================================================================
# Re-registration after AdapterRegistry.clear() (todo 11 regression)
# =========================================================================


class TestAdapterListReRegistration:
    """``adapter list`` re-registers built-ins after the singleton is cleared.

    Regression: the CLI used to ``import automedia.adapters.platforms`` to
    trigger registration, but that package is empty — all adapters register at
    the parent ``automedia.adapters`` level.  Once the parent package was
    imported (always true in the CLI), the import was a cached no-op, so after
    any ``AdapterRegistry.clear()`` the command listed an empty registry.
    ``clear()`` empties the singleton and ``ensure_registered()`` re-adds
    exactly the 20 built-ins, so this test is deterministic regardless of any
    prior test leakage.
    """

    _BUILTIN_PLATFORMS = (
        "wechat",
        "zhihu",
        "youtube",
        "twitter",
        "reddit",
        "tiktok",
        "facebook",
        "instagram",
        "linkedin",
        "medium",
        "wordpress",
        "feishu",
        "douyin",
        "kuaishou",
        "baijiahao",
        "bilibili",
        "weibo",
        "toutiao",
        "juejin",
        "xiaohongshu",
    )

    def test_cleared_registry_relists_all_builtins(self) -> None:
        AdapterRegistry.clear()
        result = _invoke()
        assert result.exit_code == 0
        for name in self._BUILTIN_PLATFORMS:
            assert name in result.output
        assert "No adapters registered." not in result.output


# =========================================================================
# Default (no flag): all platforms with a real/stub status column
# =========================================================================


class TestAdapterListDefault:
    def test_lists_all_with_status_column(self) -> None:
        real, stub = _snapshot()
        result = _invoke()
        assert result.exit_code == 0
        for name in (*real, *stub):
            assert name in result.output
        assert len(real) + len(stub) > 0
        # Status column: every line naming a platform is tagged real or stub.
        listed = [
            line for line in result.output.splitlines() if any(n in line for n in (*real, *stub))
        ]
        assert listed, "expected at least one listed platform row"
        assert all(("real" in line or "stub" in line) for line in listed)

    def test_default_line_count_matches_registry(self) -> None:
        real, stub = _snapshot()
        result = _invoke()
        listed = [
            line for line in result.output.splitlines() if any(n in line for n in (*real, *stub))
        ]
        assert len(listed) == len(real) + len(stub)


# =========================================================================
# --real / --stub filters
# =========================================================================


class TestAdapterListFilters:
    def test_real_lists_exactly_registry_reals(self) -> None:
        real, stub = _snapshot()
        result = _invoke("--real")
        assert result.exit_code == 0
        for name in real:
            assert name in result.output
        for name in stub:
            assert name not in result.output

    def test_stub_lists_exactly_registry_stubs(self) -> None:
        real, stub = _snapshot()
        result = _invoke("--stub")
        assert result.exit_code == 0
        for name in stub:
            assert name in result.output
        for name in real:
            assert name not in result.output

    def test_partitions_disjoint(self) -> None:
        """--real and --stub outputs share no platform names (12/8 split sanity)."""
        real_out = _invoke("--real").output
        stub_out = _invoke("--stub").output
        real, stub = _snapshot()
        assert not (set(real) & set(stub))
        for name in real:
            assert name not in stub_out
        for name in stub:
            assert name not in real_out


# =========================================================================
# --json
# =========================================================================


class TestAdapterListJson:
    def test_json_real_parses_and_matches(self) -> None:
        real, stub = _snapshot()
        result = _invoke("--json", "--real")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] == len(real)
        names = [a["name"] for a in data["adapters"]]
        assert names == real
        assert all(a["is_stub"] is False for a in data["adapters"])

    def test_json_stub_parses_and_matches(self) -> None:
        real, stub = _snapshot()
        result = _invoke("--json", "--stub")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] == len(stub)
        names = [a["name"] for a in data["adapters"]]
        assert names == stub
        assert all(a["is_stub"] is True for a in data["adapters"])

    def test_json_default_lists_all(self) -> None:
        real, stub = _snapshot()
        result = _invoke("--json")
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["count"] == len(real) + len(stub)
        assert len(data["adapters"]) == len(real) + len(stub)


# =========================================================================
# Mutual exclusion: --real --stub → clear error, exit code 1
# =========================================================================


class TestAdapterListMutualExclusion:
    def test_real_and_stub_error_exit_1(self) -> None:
        result = _invoke("--real", "--stub")
        assert result.exit_code == 1
        assert "cannot be combined" in result.output

    def test_real_and_stub_json_mode_error_is_json(self) -> None:
        result = runner.invoke(_app(), ["--json", "adapter", "list", "--real", "--stub"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert "cannot be combined" in data["error"]


# =========================================================================
# Deprecation note stays accurate (P1-1 constraint)
# =========================================================================


class TestDeprecationNotePreserved:
    def test_module_docstring_keeps_deprecation(self) -> None:
        from automedia.cli.commands import adapter as adapter_mod

        assert "deprecated" in adapter_mod.__doc__.lower()
        assert "automedia account" in adapter_mod.__doc__
