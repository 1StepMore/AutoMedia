"""Fail-closed allowlist gating for caller-supplied paths (T2-2).

Contract under test: an EXPLICIT path argument (``base_dir`` /
``source_path`` / ``project_dir``) outside ``mcp_allowlist.yaml`` is a
structured ``ALLOWLIST_DENIED`` error — never a warning-and-continue
fallback that silently uses a directory the caller did not ask for.  A
tool's own default (empty argument) is the app-chosen directory and is
not allowlist-gated.  The validation sandbox provisions its own scoped
allowlist so committed scenarios that address sandbox paths keep
passing (see tests/test_validation/test_sandbox.py).

Every test scopes the allowlist to ``<tmp>/projects`` via
``AUTOMEDIA_MCP_ALLOWLIST_PATH`` — the documented env path — so denial
and passage are both deterministic.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from automedia.effects.mcp import analyze_content
from automedia.mcp.allowlist import _reset_allowlist_cache
from automedia.mcp.tools.pipeline import run_pipeline
from automedia.mcp.tools.publishing import publish_content
from automedia.mcp.tools.setup import init_config
from automedia.mcp.tools_distribution import distribute_content


@pytest.fixture(autouse=True)
def _scoped_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Allowlist only ``<tmp>/projects`` so anything else under tmp is denied."""
    allowed = tmp_path / "projects"
    allowed.mkdir()
    allowlist = tmp_path / "allowlist.yaml"
    allowlist.write_text(f"allowed_directories:\n  - {allowed}\n", encoding="utf-8")
    monkeypatch.setenv("AUTOMEDIA_MCP_ALLOWLIST_PATH", str(allowlist))
    _reset_allowlist_cache()
    yield allowed
    _reset_allowlist_cache()


def _seed_project(projects_dir: Path, project_id: str) -> Path:
    project_dir = projects_dir / f"20260905_gate_{project_id}"
    project_dir.mkdir(parents=True)
    (project_dir / "00_project_info.json").write_text(
        json.dumps({"project_id": project_id, "topic": "t", "brand": "b"}),
        encoding="utf-8",
    )
    return project_dir


class TestRunPipelineSourcePathGate:
    def test_source_path_outside_allowlist_is_denied(self, tmp_path: Path) -> None:
        source = tmp_path / "elsewhere" / "brief.md"
        source.parent.mkdir()
        source.write_text("brief", encoding="utf-8")

        result = run_pipeline(topic="t", brand="b", source_path=str(source))

        assert result["status"] == "failed"
        assert result["error"]["code"] == "ALLOWLIST_DENIED"
        assert "source_path" in result["error"]["message"]

    def test_source_path_inside_allowlist_starts_normally(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A path inside the allowlist passes the gate; the pipeline thread
        itself is stubbed so the test proves only the gate decision."""
        import automedia.mcp.tools.pipeline as pipeline_mod

        source = tmp_path / "projects" / "brief.md"
        source.write_text("brief", encoding="utf-8")

        started: list[object] = []

        class _NoThread:
            def __init__(self, *args: object, **kwargs: object) -> None:
                started.append(kwargs or args)

            def start(self) -> None:
                return None

        monkeypatch.setattr(pipeline_mod.threading, "Thread", _NoThread)

        result = run_pipeline(topic="t", brand="b", source_path=str(source))

        assert result.get("error", {}).get("code") != "ALLOWLIST_DENIED"
        assert started, "gate passed but the pipeline launch was never reached"


class TestDistributeContentBaseDirGate:
    def test_base_dir_outside_allowlist_is_denied(self, tmp_path: Path) -> None:
        result = distribute_content(
            project_id="ghost01",
            platforms="wechat",
            all=False,
            dry_run=True,
            base_dir=str(tmp_path / "elsewhere"),
        )

        assert result["success"] is False
        assert result["error"]["code"] == "ALLOWLIST_DENIED"
        assert "base_dir" in result["error"]["message"]

    def test_base_dir_inside_allowlist_passes_the_gate(self, tmp_path: Path) -> None:
        result = distribute_content(
            project_id="ghost02",
            platforms="wechat",
            all=False,
            dry_run=True,
            base_dir=str(tmp_path / "projects"),
        )

        # The gate passed; the run itself fails later on the unknown project.
        assert result.get("error", {}).get("code") != "ALLOWLIST_DENIED"


class TestInitConfigProjectDirGate:
    def test_explicit_project_dir_outside_allowlist_is_denied(self, tmp_path: Path) -> None:
        result = init_config(project_dir=str(tmp_path / "elsewhere"))

        assert result["success"] is False
        assert result["error"]["code"] == "ALLOWLIST_DENIED"

    def test_explicit_project_dir_inside_allowlist_creates_config(self, tmp_path: Path) -> None:
        result = init_config(project_dir=str(tmp_path / "projects" / "newproj"))

        assert result["success"] is True
        assert (tmp_path / "projects" / "newproj" / ".automedia" / "config.yaml").is_file()

    def test_default_cwd_is_not_gated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = init_config()
        assert result["success"] is True


class TestAnalyzeContentBaseDirGate:
    def test_base_dir_outside_allowlist_is_denied(self, tmp_path: Path) -> None:
        result = analyze_content("ghost03", base_dir=str(tmp_path / "elsewhere"))

        assert result["status"] == "error"
        assert "allowlist" in result["error"].lower()

    def test_base_dir_inside_allowlist_reads_the_project(self, tmp_path: Path) -> None:
        project_dir = _seed_project(tmp_path / "projects", "gate-an-01")
        drafts = project_dir / "01_content" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "draft.md").write_text("正文内容，足够长以参与统计。", encoding="utf-8")

        result = analyze_content("gate-an-01", base_dir=str(tmp_path / "projects"))

        assert result["status"] == "ok"
        assert result["stats"]["word_count"]["word_count"] >= 1

    def test_default_cwd_is_not_gated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _seed_project(tmp_path, "gate-an-02")

        result = analyze_content("gate-an-02")

        assert result["status"] == "ok"


class TestPublishContentDefaultResolution:
    def test_empty_base_dir_resolves_default_then_gates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default projects dir is resolved BEFORE the allowlist check:
        with the env pointing inside the allowlist, an empty base_dir now
        reaches project discovery (previously ``_require_allowed("")``
        denied every default call)."""
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path / "projects"))

        result = publish_content(project_id="ghost04", platform="wechat")

        # Gate passed; discovery reports the unknown project.
        assert result.get("error", {}).get("code") == "NOT_FOUND"

    def test_default_outside_allowlist_is_denied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The factory posture is preserved: a resolved default outside the
        allowlist is denied, not silently scanned."""
        monkeypatch.setenv("AUTOMEDIA_PROJECTS_DIR", str(tmp_path / "elsewhere"))

        result = publish_content(project_id="ghost05", platform="wechat")

        assert result["success"] is False
        assert result["error"]["code"] == "ALLOWLIST_DENIED"
