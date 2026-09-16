"""L2 archive-validation wiring for the two real archive entry points.

Task 12 (automedia-reinforcement): ``automedia archive`` (CLI) and MCP
``archive_project`` must invoke ``L2ArchiveValidation`` AFTER the Red Line 8
eligibility check and BEFORE the directory rename, with a context derived from
real project data (status, force, archive path, output dir, and
title/platform/created_at metadata).  ``force=True`` short-circuits BEFORE L2
is invoked, and ``automedia rollback`` is explicitly NOT wired (it has no
``--force``; gating it would make reverting an unpublished project impossible).

All tests are hermetic: synthetic ``tmp_path`` projects, a ``tmp_path`` brand
profile file, no network, and never the real ``~/.automedia/``.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app
from automedia.gates import archive_validation
from automedia.gates.archive_validation import L2ArchiveValidation

runner = CliRunner()

_CREATED_AT = "2026-07-07T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_project(
    base_dir: Path,
    *,
    project_id: str,
    status: str,
    topic: str = "Test Topic",
    brand: str = "TestBrand",
    created_at: str = _CREATED_AT,
) -> Path:
    """Create a synthetic project dir with a 00_project_info.json."""
    proj_dir = base_dir / f"20260707_{project_id}"
    proj_dir.mkdir(parents=True)
    info: dict[str, Any] = {
        "project_id": project_id,
        "topic": topic,
        "brand": brand,
        "tenant_id": "default",
        "created_at": created_at,
        "status": status,
    }
    (proj_dir / "00_project_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return proj_dir


def _write_brand_profiles(path: Path, profiles: dict[str, Any]) -> None:
    """Write a minimal brand_profiles.yaml mapping under *path*."""
    lines: list[str] = []
    for key, profile in profiles.items():
        lines.append(f"{key}:")
        for field_name, value in profile.items():
            if isinstance(value, list):
                lines.append(f"  {field_name}:")
                lines.extend(f"    - {item}" for item in value)
            else:
                lines.append(f"  {field_name}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture()
def brand_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the brand-profile loader at a tmp_path YAML file (hermetic)."""
    import automedia.manifests.brand_profile_schema as brand_mod

    profiles_path = tmp_path / "brand_profiles.yaml"
    _write_brand_profiles(
        profiles_path,
        {
            "TestBrand": {
                "brand_name": "TestBrand",
                "platforms": ["wechat", "zhihu"],
            }
        },
    )
    monkeypatch.setattr(brand_mod, "_BRAND_PROFILES_PATH", profiles_path)
    return profiles_path


@pytest.fixture()
def l2_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Spy on L2.execute, recording the context and pre-rename filesystem state.

    The spy delegates to the real implementation so the verdict is genuine.
    ``archive_dir_existed``/``project_dir_existed`` are captured at invocation
    time: before the rename the project dir exists and the archive dir does
    not, which is the order assertion.
    """
    calls: list[dict[str, Any]] = []
    real_execute = archive_validation.L2ArchiveValidation.execute

    def _spy(self: L2ArchiveValidation, context: dict[str, Any]) -> dict[str, Any]:
        calls.append(
            {
                "context": dict(context),
                "archive_dir_existed": Path(str(context.get("archive_path", ""))).exists(),
                "project_dir_existed": Path(str(context.get("output_dir", ""))).exists(),
            }
        )
        return real_execute(self, context)

    monkeypatch.setattr(archive_validation.L2ArchiveValidation, "execute", _spy)
    return calls


@pytest.fixture()
def allowlisted_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Allowlist *tmp_path* for MCP file operations; reset afterwards."""
    import automedia.mcp.server as server_mod
    from automedia.mcp.allowlist import _reset_allowlist_cache

    _reset_allowlist_cache()
    monkeypatch.setattr(server_mod, "_cached_allowlist", [str(tmp_path.resolve())])
    yield tmp_path
    _reset_allowlist_cache()


def _create_history_db(project_dir: Path, project_id: str) -> None:
    """Create a minimal history.db with one row so rollback is eligible."""
    hist_dir = project_dir / ".automedia"
    hist_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(hist_dir / "history.db"))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS pipeline_history ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " project_id TEXT NOT NULL,"
        " action TEXT NOT NULL,"
        " timestamp REAL NOT NULL,"
        " metadata_json TEXT"
        ")"
    )
    conn.execute(
        "INSERT INTO pipeline_history (project_id, action, timestamp, metadata_json) "
        "VALUES (?, ?, ?, ?)",
        (project_id, "run_started", time.time(), "{}"),
    )
    conn.commit()
    conn.close()


# =========================================================================
# CLI `automedia archive`
# =========================================================================


class TestCliArchiveL2Wiring:
    """CLI archive invokes L2 after eligibility and before the rename."""

    def test_invokes_l2_with_derived_context_before_rename(
        self,
        tmp_path: Path,
        brand_profiles: Path,
        l2_spy: list[dict[str, Any]],
    ) -> None:
        proj_dir = _make_project(
            tmp_path, project_id="pub123abc456", status="published", topic="Published Topic"
        )

        result = runner.invoke(app, ["archive", "pub123abc456", "--base-dir", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert len(l2_spy) == 1
        call = l2_spy[0]
        ctx = call["context"]

        # Derived context values.
        assert ctx["archive_status"] == "published"
        assert ctx["force"] is False
        assert ctx["output_dir"] == str(proj_dir)
        assert ctx["archive_path"] == str(proj_dir.parent / f"{proj_dir.name}_archived")
        assert ctx["archive_metadata"] == {
            "title": "Published Topic",
            "platform": "wechat, zhihu",
            "created_at": _CREATED_AT,
        }

        # Invocation order: L2 ran before the rename (archive target absent,
        # project dir still present at gate time).
        assert call["archive_dir_existed"] is False
        assert call["project_dir_existed"] is True

        # The rename did happen afterwards.
        assert (proj_dir.parent / f"{proj_dir.name}_archived").is_dir()
        assert not proj_dir.is_dir()

    def test_brand_without_platforms_uses_unspecified(
        self,
        tmp_path: Path,
        brand_profiles: Path,
        l2_spy: list[dict[str, Any]],
    ) -> None:
        _write_brand_profiles(
            brand_profiles,
            {"TestBrand": {"brand_name": "TestBrand", "platforms": []}},
        )
        _make_project(tmp_path, project_id="pub123abc456", status="published")

        result = runner.invoke(app, ["archive", "pub123abc456", "--base-dir", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert l2_spy[0]["context"]["archive_metadata"]["platform"] == "unspecified"

    def test_unknown_brand_uses_unspecified(
        self,
        tmp_path: Path,
        brand_profiles: Path,
        l2_spy: list[dict[str, Any]],
    ) -> None:
        _make_project(tmp_path, project_id="pub123abc456", status="published", brand="AbsentBrand")

        result = runner.invoke(app, ["archive", "pub123abc456", "--base-dir", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert l2_spy[0]["context"]["archive_metadata"]["platform"] == "unspecified"

    def test_force_short_circuits_before_l2(
        self,
        tmp_path: Path,
        brand_profiles: Path,
        l2_spy: list[dict[str, Any]],
    ) -> None:
        proj_dir = _make_project(tmp_path, project_id="dra123abc456", status="draft")

        result = runner.invoke(
            app,
            ["archive", "dra123abc456", "--force", "--base-dir", str(tmp_path)],
        )

        assert result.exit_code == 0, result.output
        assert l2_spy == []
        assert (proj_dir.parent / f"{proj_dir.name}_archived").is_dir()

    def test_non_published_without_force_refuses_before_l2(
        self,
        tmp_path: Path,
        brand_profiles: Path,
        l2_spy: list[dict[str, Any]],
    ) -> None:
        proj_dir = _make_project(tmp_path, project_id="dra123abc456", status="draft")

        result = runner.invoke(app, ["archive", "dra123abc456", "--base-dir", str(tmp_path)])

        assert result.exit_code == 1
        assert "Refused" in result.output
        assert l2_spy == []
        assert proj_dir.is_dir()

    def test_l2_stop_failure_refuses_before_rename(
        self,
        tmp_path: Path,
        brand_profiles: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failing L2 result with failure_mode 'stop' must block the rename."""
        proj_dir = _make_project(tmp_path, project_id="pub123abc456", status="published")

        def _failing_execute(self: L2ArchiveValidation, context: dict[str, Any]) -> dict[str, Any]:
            return {
                "gate": "L2",
                "passed": False,
                "checks": [{"name": "archive_path_exists", "passed": False, "detail": "simulated"}],
                "error": None,
            }

        monkeypatch.setattr(archive_validation.L2ArchiveValidation, "execute", _failing_execute)

        result = runner.invoke(app, ["archive", "pub123abc456", "--base-dir", str(tmp_path)])

        assert result.exit_code == 1
        assert proj_dir.is_dir()
        assert not (proj_dir.parent / f"{proj_dir.name}_archived").exists()


# =========================================================================
# MCP `archive_project`
# =========================================================================


class TestMcpArchiveProjectL2Wiring:
    """MCP archive_project invokes L2 after eligibility and before the rename."""

    def test_invokes_l2_with_derived_context_before_rename(
        self,
        allowlisted_tmp: Path,
        brand_profiles: Path,
        l2_spy: list[dict[str, Any]],
    ) -> None:
        from automedia.mcp.tools.projects import archive_project

        proj_dir = _make_project(
            allowlisted_tmp,
            project_id="pub123abc456",
            status="published",
            topic="MCP Published Topic",
        )

        result = archive_project(project_id="pub123abc456", base_dir=str(allowlisted_tmp))

        assert result["success"] is True
        assert result["archived"] is True
        assert len(l2_spy) == 1
        call = l2_spy[0]
        ctx = call["context"]

        assert ctx["archive_status"] == "published"
        assert ctx["force"] is False
        assert ctx["output_dir"] == str(proj_dir)
        assert ctx["archive_path"] == str(proj_dir.parent / f"{proj_dir.name}_archived")
        assert ctx["archive_metadata"] == {
            "title": "MCP Published Topic",
            "platform": "wechat, zhihu",
            "created_at": _CREATED_AT,
        }

        assert call["archive_dir_existed"] is False
        assert call["project_dir_existed"] is True
        assert (proj_dir.parent / f"{proj_dir.name}_archived").is_dir()

    def test_force_short_circuits_before_l2(
        self,
        allowlisted_tmp: Path,
        brand_profiles: Path,
        l2_spy: list[dict[str, Any]],
    ) -> None:
        from automedia.mcp.tools.projects import archive_project

        proj_dir = _make_project(allowlisted_tmp, project_id="dra123abc456", status="draft")

        result = archive_project(
            project_id="dra123abc456", base_dir=str(allowlisted_tmp), force=True
        )

        assert result["archived"] is True
        assert l2_spy == []
        assert (proj_dir.parent / f"{proj_dir.name}_archived").is_dir()

    def test_non_published_without_force_refuses_before_l2(
        self,
        allowlisted_tmp: Path,
        brand_profiles: Path,
        l2_spy: list[dict[str, Any]],
    ) -> None:
        from automedia.mcp.tools.projects import archive_project

        proj_dir = _make_project(allowlisted_tmp, project_id="dra123abc456", status="draft")

        result = archive_project(project_id="dra123abc456", base_dir=str(allowlisted_tmp))

        assert result["archived"] is False
        assert "Refused" in result["error"]["message"]
        assert l2_spy == []
        assert proj_dir.is_dir()


# =========================================================================
# rollback must stay untouched
# =========================================================================


class TestRollbackUnaffected:
    """``automedia rollback`` must NOT invoke L2 (no --force exists there)."""

    def test_rollback_does_not_invoke_l2(
        self,
        tmp_path: Path,
        brand_profiles: Path,
        l2_spy: list[dict[str, Any]],
    ) -> None:
        project_id = "rollback-test-001"
        proj_dir = _make_project(
            tmp_path,
            project_id=project_id,
            status="completed",
            topic="Rollback Topic",
        )
        _create_history_db(proj_dir, project_id)

        result = runner.invoke(
            app,
            ["rollback", project_id, "--base-dir", str(tmp_path)],
            input="y\n",
        )

        assert result.exit_code == 0, result.output
        assert "Rolled back" in result.output
        assert l2_spy == []
        archived = proj_dir.parent / f"{proj_dir.name}_archived"
        assert archived.is_dir()
        data = json.loads((archived / "00_project_info.json").read_text(encoding="utf-8"))
        assert data["status"] == "draft"


# =========================================================================
# L2's own metadata semantics (recorded, not assumed)
# =========================================================================


class TestL2MetadataSemantics:
    """Metadata completeness is advisory for published archives (Red Line 8)."""

    def test_published_with_incomplete_metadata_is_force_passed(self) -> None:
        """A PUBLISHED archive fails metadata completeness but is force-passed."""
        ctx: dict[str, Any] = {
            "archive_status": "published",
            "force": False,
            "archive_path": "/data/archives/x",
            "output_dir": "/data/output/x",
            "archive_metadata": {"title": "Only Title"},
        }

        result = L2ArchiveValidation().execute(ctx)

        metadata_check = next(
            c for c in result["checks"] if c["name"] == "archive_metadata_complete"
        )
        assert metadata_check["passed"] is False
        assert result["passed"] is True
        status_check = next(c for c in result["checks"] if c["name"] == "archive_status")
        assert status_check["passed"] is True
        assert "overridden by --force" in status_check["detail"]

    def test_non_published_with_incomplete_metadata_fails(self) -> None:
        """A NON-published archive with incomplete metadata fails L2."""
        ctx: dict[str, Any] = {
            "archive_status": "draft",
            "force": False,
            "archive_path": "/data/archives/x",
            "output_dir": "/data/output/x",
            "archive_metadata": {"title": "Only Title"},
        }

        result = L2ArchiveValidation().execute(ctx)

        assert result["passed"] is False


# =========================================================================
# Guard: real ~/.automedia is never read for the new tests
# =========================================================================


def test_brand_profiles_fixture_is_used(brand_profiles: Path) -> None:
    """Sanity: the brand-profile fixture actually redirects the loader."""
    import automedia.manifests.brand_profile_schema as brand_mod
    from automedia.manifests.brand_profile_schema import load_brand_profiles

    assert brand_profiles == brand_mod._BRAND_PROFILES_PATH
    profiles = load_brand_profiles()
    assert "TestBrand" in profiles
    assert profiles["TestBrand"].platforms == ["wechat", "zhihu"]
