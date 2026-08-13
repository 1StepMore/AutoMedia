"""Tests for automedia.omni.allowlist — AllowlistConfig, validate_path, is_read_only."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from automedia.omni.allowlist import (
    AllowlistConfig,
    _is_subpath,
    is_read_only,
    load_allowlist,
    validate_path,
)


class TestAllowlistConfig:
    def test_default_construction(self):
        cfg = AllowlistConfig()
        assert cfg.allowed_paths == []
        assert cfg.write_paths == []

    def test_explicit_values(self):
        cfg = AllowlistConfig(
            allowed_paths=["/data/read", "/data/common"],
            write_paths=["/data/common"],
        )
        assert cfg.allowed_paths == ["/data/read", "/data/common"]
        assert cfg.write_paths == ["/data/common"]


class TestLoadAllowlist:
    def _write_allowlist(self, tmp_path, data: dict, name: str = "omni_allowlist.yaml"):
        p = tmp_path / name
        p.write_text(yaml.dump(data), encoding="utf-8")
        return p

    def test_loads_full_allowlist(self, tmp_path):
        data = {
            "allowed_paths": ["/data/read", "/data/common"],
            "write_paths": ["/data/common"],
        }
        path = self._write_allowlist(tmp_path, data)
        cfg = load_allowlist(path)
        assert cfg.allowed_paths == ["/data/read", "/data/common"]
        assert cfg.write_paths == ["/data/common"]

    def test_missing_file_returns_empty(self, tmp_path):
        """Fail-CLOSED: missing allowlist file rejects all paths."""
        path = tmp_path / "nonexistent.yaml"
        cfg = load_allowlist(path)
        assert cfg.allowed_paths == []
        assert cfg.write_paths == []

    def test_invalid_yaml_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            load_allowlist(p)

    def test_default_path_when_none(self, monkeypatch, tmp_path):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        cfg = load_allowlist()
        assert cfg.allowed_paths == []

    def test_default_path_loads_file(self, monkeypatch, tmp_path):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: fake_home)

        config_dir = fake_home / ".automedia"
        config_dir.mkdir()
        config_file = config_dir / "omni_allowlist.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "allowed_paths": ["/data/media", "/data/cache"],
                    "write_paths": ["/data/cache"],
                }
            ),
            encoding="utf-8",
        )

        cfg = load_allowlist()
        assert "/data/media" in cfg.allowed_paths
        assert "/data/cache" in cfg.write_paths


class TestValidatePath:
    def test_allowed_path_allows_read(self):
        cfg = AllowlistConfig(allowed_paths=["/data"], write_paths=[])
        assert validate_path(Path("/data/file.txt"), cfg, mode="read") is True

    def test_allowed_path_rejects_outside(self):
        cfg = AllowlistConfig(allowed_paths=["/data"], write_paths=[])
        assert validate_path(Path("/etc/passwd"), cfg, mode="read") is False

    def test_write_path_allows_write(self):
        cfg = AllowlistConfig(
            allowed_paths=["/data/read"],
            write_paths=["/data/write"],
        )
        assert validate_path(Path("/data/write/out.txt"), cfg, mode="write") is True

    def test_read_only_path_rejects_write(self):
        cfg = AllowlistConfig(
            allowed_paths=["/data/read"],
            write_paths=[],
        )
        assert validate_path(Path("/data/read/file.txt"), cfg, mode="write") is False

    def test_subdirectory_is_allowed(self):
        cfg = AllowlistConfig(allowed_paths=["/data"], write_paths=[])
        assert validate_path(Path("/data/sub/dir/file.txt"), cfg, mode="read") is True

    def test_empty_allowlist_rejects_all_read(self):
        """Fail-CLOSED: empty allowlist rejects everything."""
        cfg = AllowlistConfig()
        assert validate_path(Path("/data/file.txt"), cfg, mode="read") is False

    def test_empty_allowlist_rejects_all_write(self):
        cfg = AllowlistConfig()
        assert validate_path(Path("/data/file.txt"), cfg, mode="write") is False

    def test_write_path_also_allows_read(self):
        """A write_path is implicitly readable."""
        cfg = AllowlistConfig(allowed_paths=[], write_paths=["/data"])
        assert validate_path(Path("/data/file.txt"), cfg, mode="read") is True

    def test_exact_path_match(self):
        cfg = AllowlistConfig(allowed_paths=["/data/file.txt"], write_paths=[])
        assert validate_path(Path("/data/file.txt"), cfg, mode="read") is True
        assert validate_path(Path("/data/other.txt"), cfg, mode="read") is False


class TestIsReadOnly:
    def test_path_in_allowed_only_is_read_only(self):
        cfg = AllowlistConfig(allowed_paths=["/data/read"], write_paths=[])
        assert is_read_only(Path("/data/read/file.txt"), cfg) is True

    def test_path_in_write_is_not_read_only(self):
        cfg = AllowlistConfig(
            allowed_paths=["/data/read", "/data/write"],
            write_paths=["/data/write"],
        )
        assert is_read_only(Path("/data/write/file.txt"), cfg) is False

    def test_path_not_allowed_is_not_read_only(self):
        cfg = AllowlistConfig(allowed_paths=["/data/read"], write_paths=[])
        assert is_read_only(Path("/outside"), cfg) is False


class TestIsSubpath:
    def test_child_relative_to_parent(self):
        assert _is_subpath(Path("/data/sub/file.txt"), "/data") is True

    def test_equal_paths(self):
        assert _is_subpath(Path("/data"), "/data") is True

    def test_not_a_child(self):
        assert _is_subpath(Path("/etc"), "/data") is False
