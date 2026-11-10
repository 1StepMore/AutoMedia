"""PublishEngine dry-run and record/replay (#456).

``dry_run=True`` walks the full pre-flight state machine — adapter
resolution, enabled/credential check, automation resolution, ``validate()`` —
but never calls ``adapter.publish()``, so no network request can be issued.
Every result carries ``dry_run=True`` and disabled adapters are reported as
``skipped`` instead of silently omitted, so one dry run doubles as an
executable credential matrix.

``record_dir`` writes each per-platform result to JSON — the evidence channel
for a future first real publish and the replay source for tests.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from automedia.adapters.publish_engine import PublishEngine
from automedia.adapters.registry import AdapterRegistry
from tests.test_adapters.test_platform_contracts import REAL_CLASSES


@pytest.fixture()
def _no_credentials_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local zero-credential force (mirrors the contract suite fixture)."""
    from tests.test_adapters.test_platform_contracts import (
        _CRED_NAMES,
        _load_all_platform_modules,
    )

    def _none_loader(*args: Any, **kwargs: Any) -> Any:
        return None

    def _env_lookup(_names: Any, default: str = "", **kwargs: Any) -> str:
        _ = _names, kwargs
        return default

    for mod in _load_all_platform_modules():
        for name in _CRED_NAMES:
            if hasattr(mod, name):
                monkeypatch.setattr(
                    mod,
                    name,
                    _env_lookup if name == "env_lookup" else _none_loader,
                    raising=True,
                )


@pytest.mark.usefixtures("_no_credentials_local")
class TestDryRun:
    def test_dry_run_covers_every_platform(self, tmp_path: Any) -> None:
        engine = PublishEngine()
        results = engine.publish_all(
            str(tmp_path / "artifact"),
            {"topic": "dry-run"},
            dry_run=True,
        )
        # 零凭证下没有任何适配器被静默略过——干跑即凭证矩阵（#456）。
        assert len(results) >= 20
        assert all(r.get("dry_run") is True for r in results.values())

    def test_disabled_adapters_reported_not_omitted(self, tmp_path: Any) -> None:
        engine = PublishEngine()
        results = engine.publish_all(
            str(tmp_path / "artifact"),
            {"topic": "dry-run"},
            dry_run=True,
        )
        skipped = [r for r in results.values() if r["status"] == "skipped"]
        assert skipped, "zero-credential machines must report every disabled platform"
        assert all("credentials" in r["reason"] for r in skipped)

    def test_real_adapter_never_publishes_in_dry_run(self, tmp_path: Any) -> None:
        """The real-automation adapters must not be given publish() at all.

        Proof: with credentials forced absent their ``enabled`` is False, so
        a dry run records ``skipped`` — and even if a pre-flight passed, the
        dry-run branch returns before ``adapter.publish()``.  Either way no
        adapter's publish() side effect can occur.
        """
        engine = PublishEngine()
        results = engine.publish_all(
            str(tmp_path / "artifact"),
            {"topic": "dry-run"},
            dry_run=True,
        )
        for cls in REAL_CLASSES:
            name = cls().platform_name
            result = results.get(name, {})
            assert result.get("dry_run") is True, (name, result)
            assert result["status"] in ("ok", "skipped")
            assert result["status"] != "ok" or "not called" in result["reason"]

    def test_pre_flight_passing_adapter_never_reaches_publish(self, tmp_path: Any) -> None:
        """The dry-run ``ok`` branch must return BEFORE ``adapter.publish()``.

        A fake registry supplies an adapter whose pre-flight passes (enabled,
        validate → True) and whose ``publish()`` raises — a real network
        would fire here.  The dry run must come back ``ok`` without ever
        touching it.
        """
        from automedia.adapters.base import BasePlatformAdapter

        calls: list[str] = []

        class _WouldGoLive(BasePlatformAdapter):
            is_stub = False

            @property
            def platform_name(self) -> str:
                return "would-go-live"

            def validate(self, artifact_dir: str) -> bool:
                return True

            def publish(
                self, artifact_dir: str, project: dict[str, Any], draft_only: bool = False
            ) -> dict[str, Any]:
                calls.append(artifact_dir)
                return {"status": "ok"}

        class _FakeRegistry(AdapterRegistry):
            @classmethod
            def list(cls) -> list[str]:
                return ["would-go-live"]

            @classmethod
            def get(cls, platform_name: str) -> type[BasePlatformAdapter]:
                return _WouldGoLive

        engine = PublishEngine()
        engine.registry_class = _FakeRegistry
        results = engine.publish_all(
            str(tmp_path / "artifact"),
            {"topic": "dry-run"},
            dry_run=True,
        )
        assert calls == [], "publish() must never be called in a dry run (#456)"
        assert results["would-go-live"]["status"] == "ok"
        assert results["would-go-live"]["dry_run"] is True
        assert "not called" in results["would-go-live"]["reason"]


@pytest.mark.usefixtures("_no_credentials_local")
class TestRecordReplay:
    def test_dry_run_results_recorded_as_fixtures(self, tmp_path: Any) -> None:
        engine = PublishEngine()
        record_dir = tmp_path / "records"
        engine.publish_all(
            str(tmp_path / "artifact"),
            {"topic": "dry-run"},
            dry_run=True,
            record_dir=str(record_dir),
        )
        files = list(record_dir.glob("*.json"))
        assert len(files) >= 20
        sample = json.loads(files[0].read_text(encoding="utf-8"))
        assert sample["dry_run"] is True

    def test_recorded_result_replays(self, tmp_path: Any) -> None:
        engine = PublishEngine()
        record_dir = tmp_path / "records"
        engine.publish_all(
            str(tmp_path / "artifact"),
            {"topic": "dry-run"},
            dry_run=True,
            record_dir=str(record_dir),
        )
        first = sorted(record_dir.glob("*.json"))[0]
        replayed = engine.load_recorded_result(first.stem, str(record_dir))
        assert replayed is not None
        assert replayed == json.loads(first.read_text(encoding="utf-8"))

    def test_load_missing_recording_returns_none(self, tmp_path: Any) -> None:
        assert PublishEngine.load_recorded_result("nope", str(tmp_path)) is None
