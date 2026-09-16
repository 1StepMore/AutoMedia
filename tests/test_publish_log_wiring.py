"""L1 publish-log wiring for every publish path.

Task 11 (automedia-reinforcement): the three flows that call
``PublishEngine.publish_all`` — MCP ``publish_content``,
``adapters.distribution.distribute_to_platforms`` (MCP
``distribute_content``), and the cron runner (``_publish_to_platform`` /
``_publish_to_all_platforms``) — must resolve a publish target set, build one
``publish_log`` entry per target, validate each entry with ``L1PublishLogSchema``
before publishing, and write the entries to ``06_publish/publish_log.json``.

The target set is always the resolved targets intersected with the static
19-platform constant, so the ``feishu`` notifier (a registered adapter that is
not a publish target) is never included.  When the intersection is empty the
flow returns a ``"no publishable target"`` error and never calls
``publish_all``.

All tests are hermetic: synthetic ``tmp_path`` projects, a ``tmp_path`` brand
profile file, a ``PublishEngine.publish_all`` spy, no network, and never the
real ``~/.automedia/``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from automedia.gates.publish_log_wiring import (
    PUBLISH_PLATFORM_SET,
    PublishLogGateError,
)

_BRAND = "TestBrand"

RegisterTargets = Callable[[list[str]], None]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


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
def brand_profiles_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the brand-profile loader at a tmp_path YAML file (hermetic)."""
    import automedia.manifests.brand_profile_schema as brand_mod

    profiles_path = tmp_path / "brand_profiles.yaml"
    monkeypatch.setattr(brand_mod, "_BRAND_PROFILES_PATH", profiles_path)
    return profiles_path


@pytest.fixture()
def publish_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Spy on ``PublishEngine.publish_all`` without invoking any adapter."""
    from automedia.adapters.publish_engine import PublishEngine

    calls: list[dict[str, Any]] = []

    def _fake(
        self: PublishEngine,
        artifact_dir: str,
        project: dict[str, Any],
        account_ids: list[str] | None = None,
        automation: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        calls.append(
            {
                "artifact_dir": str(artifact_dir),
                "project": dict(project),
                "account_ids": account_ids,
                "automation": automation,
            }
        )
        return {"zhihu": {"status": "ok"}, "wechat": {"status": "ok"}}

    monkeypatch.setattr(PublishEngine, "publish_all", _fake)
    return calls


@pytest.fixture()
def registry_publish_targets() -> Iterator[RegisterTargets]:
    """Register a synthetic adapter set, then restore the built-ins."""
    from automedia.adapters import ensure_registered
    from automedia.adapters.registry import AdapterRegistry

    def _register(names: list[str]) -> None:
        AdapterRegistry.clear()
        for name in names:

            class _TestAdapter:
                platform_name = name
                is_stub = True

                def __init__(self, account_id: str = "") -> None:
                    self.account_id = account_id

                def validate(self, artifact_dir: str) -> bool:
                    return True

            AdapterRegistry.register(_TestAdapter)  # type: ignore[arg-type]

    yield _register

    AdapterRegistry.clear()
    ensure_registered()


def _make_project(
    base_dir: Path,
    *,
    project_id: str,
    topic: str = "AI Topic",
    brand: str = _BRAND,
    draft_body: str = "# AI Topic\n\nBody text for publishing.",
    media: bool = False,
) -> Path:
    """Create a synthetic project skeleton under *base_dir*."""
    proj_dir = base_dir / f"20260707_{project_id}"
    drafts = proj_dir / "01_content" / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "draft.md").write_text(draft_body, encoding="utf-8")
    (proj_dir / "06_publish").mkdir()
    if media:
        cover = proj_dir / "02_images" / "cover"
        cover.mkdir(parents=True)
        (cover / "cover.png").write_bytes(b"\x89PNG\r\n")
    info = {
        "project_id": project_id,
        "topic": topic,
        "brand": brand,
        "tenant_id": "default",
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    (proj_dir / "00_project_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return proj_dir


def _read_publish_log(proj_dir: Path) -> list[dict[str, Any]]:
    raw = (proj_dir / "06_publish" / "publish_log.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, list)
    return data


def _assert_entry_schema(entry: dict[str, Any]) -> None:
    for key in ("topic", "content", "media_paths", "platform", "created_at"):
        assert key in entry, f"publish_log entry missing {key!r}: {entry}"
    assert isinstance(entry["media_paths"], list)


# =========================================================================
# MCP publish_content
# =========================================================================


class TestPublishContentL1Wiring:
    """``publish_content`` builds + validates publish_log before publish_all."""

    def _call(
        self,
        tmp_path: Path,
        project_id: str,
        platform: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> dict[str, Any]:
        import automedia.mcp.tools.publishing as pub_mod
        from automedia.mcp.tools.publishing import publish_content

        monkeypatch.setattr(pub_mod, "_require_allowed", lambda *a, **k: None)
        monkeypatch.setattr("automedia.asset_library.db.AssetDatabase", MagicMock())
        return publish_content(project_id=project_id, platform=platform, base_dir=str(tmp_path))

    def test_zhihu_publish_is_gated_and_writes_log(
        self,
        tmp_path: Path,
        brand_profiles_path: Path,
        publish_spy: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """zhihu (outside the old enum) passes L1 and one log entry is written."""
        _write_brand_profiles(
            brand_profiles_path,
            {_BRAND: {"brand_name": _BRAND, "platforms": ["zhihu"]}},
        )
        proj_dir = _make_project(tmp_path, project_id="pub123abc456", media=True)

        result = self._call(tmp_path, "pub123abc456", "zhihu", monkeypatch)

        assert result["success"] is True
        assert result["published"] is True
        assert len(publish_spy) == 1

        entries = _read_publish_log(proj_dir)
        assert len(entries) == 1
        entry = entries[0]
        _assert_entry_schema(entry)
        assert entry["platform"] == "zhihu"
        assert entry["topic"] == "AI Topic"
        assert entry["content"].strip()
        assert any("cover.png" in p for p in entry["media_paths"])

    def test_missing_platform_aborts_before_publish(
        self,
        tmp_path: Path,
        brand_profiles_path: Path,
        publish_spy: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An entry without ``platform`` fails L1 and publish_all is never called."""
        _write_brand_profiles(
            brand_profiles_path,
            {_BRAND: {"brand_name": _BRAND, "platforms": ["zhihu"]}},
        )
        _make_project(tmp_path, project_id="pub123abc456")
        monkeypatch.setattr(
            "automedia.gates.publish_log_wiring.build_publish_log_entries",
            lambda *a, **k: [{"topic": "T", "content": "C", "media_paths": []}],
        )

        result = self._call(tmp_path, "pub123abc456", "zhihu", monkeypatch)

        assert result["success"] is False
        assert publish_spy == []

    def test_empty_target_set_returns_no_publishable_target(
        self,
        tmp_path: Path,
        brand_profiles_path: Path,
        publish_spy: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A brand declaring only feishu → empty intersection → no publish."""
        _write_brand_profiles(
            brand_profiles_path,
            {_BRAND: {"brand_name": _BRAND, "platforms": ["feishu"]}},
        )
        _make_project(tmp_path, project_id="pub123abc456")

        result = self._call(tmp_path, "pub123abc456", "feishu", monkeypatch)

        assert result["success"] is False
        assert "no publishable target" in result["error"]["message"].lower()
        assert publish_spy == []


# =========================================================================
# MCP distribute_content → distribute_to_platforms
# =========================================================================


class TestDistributeL1Wiring:
    """``distribute_to_platforms`` gates every publish on L1."""

    def test_distribute_gated_and_writes_one_entry_per_target(
        self,
        tmp_path: Path,
        registry_publish_targets: RegisterTargets,
        publish_spy: list[dict[str, Any]],
    ) -> None:
        """Explicit platforms → publish_all called once, one log entry per target."""
        from automedia.adapters.distribution import distribute_to_platforms

        registry_publish_targets(["wechat", "zhihu"])
        proj_dir = _make_project(tmp_path, project_id="dis123abc456")

        result = distribute_to_platforms(
            project_id="dis123abc456",
            platforms=["wechat", "zhihu"],
            base_dir=str(tmp_path),
        )

        assert result["dry_run"] is False
        assert len(publish_spy) == 1
        entries = _read_publish_log(proj_dir)
        assert len(entries) == 2
        assert {e["platform"] for e in entries} == {"wechat", "zhihu"}
        for entry in entries:
            _assert_entry_schema(entry)

    def test_all_platforms_excludes_feishu(
        self,
        tmp_path: Path,
        registry_publish_targets: RegisterTargets,
        publish_spy: list[dict[str, Any]],
    ) -> None:
        """``all_platforms=True`` intersects the registry with the 19-constant."""
        from automedia.adapters.distribution import distribute_to_platforms

        registry_publish_targets(["wechat", "zhihu", "feishu"])
        proj_dir = _make_project(tmp_path, project_id="dis123abc456")

        result = distribute_to_platforms(
            project_id="dis123abc456",
            all_platforms=True,
            base_dir=str(tmp_path),
        )

        assert len(publish_spy) == 1
        assert set(result["platforms"]) == {"wechat", "zhihu"}
        entries = _read_publish_log(proj_dir)
        assert {e["platform"] for e in entries} == {"wechat", "zhihu"}

    def test_distribute_gated_missing_platform_aborts(
        self,
        tmp_path: Path,
        registry_publish_targets: RegisterTargets,
        publish_spy: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A bad entry blocks publish_all on the distribute path."""
        from automedia.adapters.distribution import distribute_to_platforms

        registry_publish_targets(["wechat"])
        _make_project(tmp_path, project_id="dis123abc456")
        monkeypatch.setattr(
            "automedia.gates.publish_log_wiring.build_publish_log_entries",
            lambda *a, **k: [{"topic": "T", "content": "C", "media_paths": []}],
        )

        result = distribute_to_platforms(
            project_id="dis123abc456",
            platforms=["wechat"],
            base_dir=str(tmp_path),
        )

        assert "error" in result
        assert publish_spy == []

    def test_empty_intersection_returns_no_publishable_target(
        self,
        tmp_path: Path,
        registry_publish_targets: RegisterTargets,
        publish_spy: list[dict[str, Any]],
    ) -> None:
        """A registry containing only feishu → no publishable target."""
        from automedia.adapters.distribution import distribute_to_platforms

        registry_publish_targets(["feishu"])
        _make_project(tmp_path, project_id="dis123abc456")

        result = distribute_to_platforms(
            project_id="dis123abc456",
            all_platforms=True,
            base_dir=str(tmp_path),
        )

        assert "no publishable target" in result["summary"].lower()
        assert publish_spy == []


# =========================================================================
# cron runner
# =========================================================================


class TestCronL1Wiring:
    """The cron auto-publish helpers gate their publish_all calls on L1."""

    def test_cron_publish_to_platform_is_gated(
        self,
        tmp_path: Path,
        publish_spy: list[dict[str, Any]],
    ) -> None:
        """``_publish_to_platform`` validates + writes before publishing."""
        from automedia.cron.runner import _publish_to_platform

        proj_dir = _make_project(tmp_path, project_id="cro123abc456")

        result = _publish_to_platform(
            artifact_dir=str(proj_dir),
            project_id="cro123abc456",
            topic="AI Topic",
            brand=_BRAND,
            platform="zhihu",
        )

        assert result["status"] == "ok"
        assert len(publish_spy) == 1
        entries = _read_publish_log(proj_dir)
        assert [e["platform"] for e in entries] == ["zhihu"]

    def test_cron_publish_gated_missing_platform_aborts(
        self,
        tmp_path: Path,
        publish_spy: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A bad entry blocks publish_all on the cron single-platform path."""
        from automedia.cron.runner import _publish_to_platform

        proj_dir = _make_project(tmp_path, project_id="cro123abc456")
        monkeypatch.setattr(
            "automedia.gates.publish_log_wiring.build_publish_log_entries",
            lambda *a, **k: [{"topic": "T", "content": "C", "media_paths": []}],
        )

        with pytest.raises(PublishLogGateError):
            _publish_to_platform(
                artifact_dir=str(proj_dir),
                project_id="cro123abc456",
                topic="AI Topic",
                brand=_BRAND,
                platform="zhihu",
            )

        assert publish_spy == []

    def test_cron_publish_to_all_platforms_is_gated(
        self,
        tmp_path: Path,
        brand_profiles_path: Path,
        publish_spy: list[dict[str, Any]],
    ) -> None:
        """``_publish_to_all_platforms`` uses the brand targets ∩ 19-constant."""
        from automedia.cron.runner import _publish_to_all_platforms

        _write_brand_profiles(
            brand_profiles_path,
            {_BRAND: {"brand_name": _BRAND, "platforms": ["wechat", "zhihu", "feishu"]}},
        )
        proj_dir = _make_project(tmp_path, project_id="cro123abc456")

        results = _publish_to_all_platforms(
            artifact_dir=str(proj_dir),
            project_id="cro123abc456",
            topic="AI Topic",
            brand=_BRAND,
        )

        assert set(results) == {"wechat", "zhihu"}
        assert len(publish_spy) == 1
        entries = _read_publish_log(proj_dir)
        assert {e["platform"] for e in entries} == {"wechat", "zhihu"}

    def test_cron_empty_target_set_aborts(
        self,
        tmp_path: Path,
        brand_profiles_path: Path,
        publish_spy: list[dict[str, Any]],
    ) -> None:
        """A brand declaring only feishu → no publish_all on the cron all path."""
        from automedia.cron.runner import _publish_to_all_platforms

        _write_brand_profiles(
            brand_profiles_path,
            {_BRAND: {"brand_name": _BRAND, "platforms": ["feishu"]}},
        )
        proj_dir = _make_project(tmp_path, project_id="cro123abc456")

        with pytest.raises(PublishLogGateError, match="no publishable target"):
            _publish_to_all_platforms(
                artifact_dir=str(proj_dir),
                project_id="cro123abc456",
                topic="AI Topic",
                brand=_BRAND,
            )

        assert publish_spy == []


# =========================================================================
# The 19-constant itself
# =========================================================================


class TestPublishPlatformConstant:
    def test_constant_excludes_feishu_and_is_the_19_targets(self) -> None:
        assert len(PUBLISH_PLATFORM_SET) == 19
        assert "feishu" not in PUBLISH_PLATFORM_SET
        for name in ("wechat", "zhihu", "linkedin", "xiaohongshu", "medium"):
            assert name in PUBLISH_PLATFORM_SET
