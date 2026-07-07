"""Tests for automedia.core.doctor — Doctor dependency checker."""

from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from automedia.core.doctor import Doctor


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def doctor() -> Doctor:
    return Doctor()


# ===================================================================
# Tests
# ===================================================================


class TestDoctorResolvePath:
    """_resolve_path behaviour with shutil.which."""

    def test_returns_path_when_found(self, doctor: Doctor):
        with patch("automedia.core.doctor.shutil.which", return_value="/usr/bin/python3"):
            path = doctor._resolve_path("python")
            assert path == "/usr/bin/python3"

    def test_returns_none_when_missing(self, doctor: Doctor):
        with patch("automedia.core.doctor.shutil.which", return_value=None):
            path = doctor._resolve_path("nonexistent-tool")
            assert path is None

    def test_chrome_tries_candidates(self, doctor: Doctor):
        """Chrome resolution tries google-chrome first, then alternatives."""
        with patch(
            "automedia.core.doctor.shutil.which",
            side_effect=lambda x: f"/usr/bin/{x}" if x == "chromium" else None,
        ):
            path = doctor._resolve_path("chrome")
            assert path == "/usr/bin/chromium"


class TestDoctorGetVersion:
    """_get_version extracts version from subprocess output."""

    def test_returns_first_line_on_success(self, doctor: Doctor):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Python 3.11.4\nsome other text\n"
        mock_result.stderr = ""

        with patch.object(subprocess, "run", return_value=mock_result):
            ver = doctor._get_version(["python3", "--version"])
            assert ver == "Python 3.11.4"

    def test_uses_stderr_fallback(self, doctor: Doctor):
        """Some tools output version to stderr."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = "bun 1.2.3\n"

        with patch.object(subprocess, "run", return_value=mock_result):
            ver = doctor._get_version(["bun", "--version"])
            assert ver == "bun 1.2.3"

    def test_returns_none_on_failure(self, doctor: Doctor):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch.object(subprocess, "run", return_value=mock_result):
            ver = doctor._get_version(["bad-cmd"])
            assert ver is None

    def test_returns_none_on_timeout(self, doctor: Doctor):
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
            ver = doctor._get_version(["slow-cmd"])
            assert ver is None


class TestDoctorCheckDependencies:
    """Full check_dependencies integration."""

    def test_all_installed(self, doctor: Doctor):
        """All tools found — returns installed=True for each."""
        with (
            patch.object(doctor, "_resolve_path", return_value="/usr/bin/ok"),
            patch.object(doctor, "_get_version", return_value="1.0"),
        ):
            results = doctor.check_dependencies()
            for dep in results:
                assert dep["installed"] is True, f"{dep['name']} should be installed"
                assert dep["path"] == "/usr/bin/ok"
                if dep["name"] in ("comfyui", "chrome"):
                    assert dep["version"] is None
                else:
                    assert dep["version"] == "1.0"

    def test_all_missing(self, doctor: Doctor):
        """No tools found — returns installed=False for each."""
        with patch.object(doctor, "_resolve_path", return_value=None):
            results = doctor.check_dependencies()
            for dep in results:
                assert dep["installed"] is False
                assert dep["path"] is None
                assert dep["version"] is None

    def test_partial_installation(self, doctor: Doctor):
        """Only some tools are installed."""
        installed_names = {"python", "bun", "ffmpeg"}

        def mock_resolve(name: str) -> str | None:
            return f"/usr/bin/{name}" if name in installed_names else None

        with (
            patch.object(doctor, "_resolve_path", side_effect=mock_resolve),
            patch.object(doctor, "_get_version", return_value="1.0"),
        ):
            results = doctor.check_dependencies()

        installed = {r["name"] for r in results if r["installed"]}
        missing = {r["name"] for r in results if not r["installed"]}
        assert installed == installed_names
        assert "whisper" in missing
        assert "edge-tts" in missing
        assert "comfyui" in missing
        assert "chrome" in missing

    def test_result_structure(self, doctor: Doctor):
        """Each result dict has the required keys."""
        with (
            patch.object(doctor, "_resolve_path", return_value="/usr/bin/python3"),
            patch.object(doctor, "_get_version", return_value="3.11"),
        ):
            results = doctor.check_dependencies()

        for dep in results:
            assert "name" in dep
            assert "installed" in dep
            assert "version" in dep or dep.get("version") is None
            assert "path" in dep or dep.get("path") is None
            assert isinstance(dep["installed"], bool)
