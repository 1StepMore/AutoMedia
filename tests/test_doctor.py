"""Tests for automedia.core.doctor — Doctor dependency checker."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

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
        with patch.object(
            subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)
        ):
            ver = doctor._get_version(["slow-cmd"])
            assert ver is None


class TestDoctorChromeHeadless:
    """_check_chrome_headless behaviour."""

    def test_headless_success(self, doctor: Doctor):
        """Returncode 0 → (True, None)."""
        with patch.object(subprocess, "run") as m_run:
            m_run.return_value = MagicMock(returncode=0, stdout="<html></html>", stderr="")
            ok, msg = doctor._check_chrome_headless("/usr/bin/google-chrome")
            assert ok is True
            assert msg is None

    def test_headless_failure(self, doctor: Doctor):
        """Returncode 1 → (False, error message)."""
        with patch.object(subprocess, "run") as m_run:
            m_run.return_value = MagicMock(returncode=1, stdout="", stderr="missing libnss3")
            ok, msg = doctor._check_chrome_headless("/usr/bin/google-chrome")
            assert ok is False
            assert msg is not None
            assert "missing libnss3" in msg

    def test_headless_timeout(self, doctor: Doctor):
        """TimeoutExpired → (False, 'timed out')."""
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=10)):
            ok, msg = doctor._check_chrome_headless("/usr/bin/google-chrome")
            assert ok is False
            assert msg is not None
            assert "timed out" in msg

    def test_headless_file_not_found(self, doctor: Doctor):
        """FileNotFoundError → (False, 'not found')."""
        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            ok, msg = doctor._check_chrome_headless("/usr/bin/google-chrome")
            assert ok is False
            assert msg is not None
            assert "not found" in msg


class TestDoctorCheckDependencies:
    """Full check_dependencies integration."""

    def test_all_installed(self, doctor: Doctor):
        """All tools found — returns installed=True for each."""
        with (
            patch.object(doctor, "_resolve_path", return_value="/usr/bin/ok"),
            patch.object(doctor, "_get_version", return_value="1.0"),
            patch.object(doctor, "_check_comfyui_http", return_value=(True, "ComfyUI reachable")),
            patch.object(doctor, "_check_llm_api", return_value=(True, "API reachable")),
            patch.object(doctor, "_check_chrome_headless", return_value=(True, None)),
        ):
            results = doctor.check_dependencies()
            for dep in results:
                assert dep["installed"] is True, f"{dep['name']} should be installed"
                if dep["name"] == "comfyui":
                    assert dep["path"] is None
                    assert dep["version"] == "ComfyUI reachable"
                elif dep["name"] == "llm_api":
                    assert dep["path"] is None
                    assert dep["version"] == "API reachable"
                elif dep["name"] == "chrome":
                    assert dep["path"] == "/usr/bin/ok"
                    assert dep["version"] is None
                    assert dep["headless_ok"] is True
                    assert dep.get("headless_message") is None
                else:
                    assert dep["path"] == "/usr/bin/ok"
                    assert dep["version"] == "1.0"

    def test_all_missing(self, doctor: Doctor):
        """No tools found — returns installed=False for each."""
        with (
            patch.object(doctor, "_resolve_path", return_value=None),
            patch.object(doctor, "_check_comfyui_http", return_value=(False, None)),
            patch.object(doctor, "_check_llm_api", return_value=(False, "no API key")),
        ):
            results = doctor.check_dependencies()
            for dep in results:
                assert dep["installed"] is False
                assert dep["path"] is None
                if dep["name"] == "chrome":
                    assert dep["headless_ok"] is False
                    assert dep.get("headless_message") is None
                assert dep["version"] is None or dep["name"] == "llm_api"

    def test_partial_installation(self, doctor: Doctor):
        """Only some tools are installed."""
        installed_names = {"python", "bun", "ffmpeg"}

        def mock_resolve(name: str) -> str | None:
            return f"/usr/bin/{name}" if name in installed_names else None

        with (
            patch.object(doctor, "_resolve_path", side_effect=mock_resolve),
            patch.object(doctor, "_get_version", return_value="1.0"),
            patch.object(doctor, "_check_comfyui_http", return_value=(False, None)),
            patch.object(doctor, "_check_llm_api", return_value=(False, "no API key")),
        ):
            results = doctor.check_dependencies()

        installed = {r["name"] for r in results if r["installed"]}
        missing = {r["name"] for r in results if not r["installed"]}
        assert installed == installed_names
        assert "whisper" in missing
        assert "edge-tts" in missing
        assert "comfyui" in missing
        assert "chrome" in missing
        assert "llm_api" in missing

    def test_result_structure(self, doctor: Doctor):
        """Each result dict has the required keys."""
        with (
            patch.object(doctor, "_resolve_path", return_value="/usr/bin/python3"),
            patch.object(doctor, "_get_version", return_value="3.11"),
            patch.object(doctor, "_check_comfyui_http", return_value=(True, "ok")),
            patch.object(doctor, "_check_llm_api", return_value=(True, "API reachable")),
        ):
            results = doctor.check_dependencies()

        for dep in results:
            assert "name" in dep
            assert "installed" in dep
            assert "version" in dep or dep.get("version") is None
            assert "path" in dep or dep.get("path") is None
            if dep["name"] == "chrome":
                assert "headless_ok" in dep
                assert "headless_message" in dep
            assert isinstance(dep["installed"], bool)

    def test_get_headless_chrome_instructions(self, doctor: Doctor):
        """Returns platform-specific string or None."""
        instructions = doctor.get_headless_chrome_instructions()
        assert instructions is None or isinstance(instructions, str)


class TestDoctorPythonResolution:
    """Regression: doctor must detect python3 when only python3 is on PATH.

    Many Linux distros ship only ``python3`` (not ``python``). The Doctor's
    dep table lists ``name="python"`` with ``check_cmd=["python3", ...]``,
    so the version-fetch works, but existence-check uses
    ``shutil.which("python")`` which returns None. This test exercises
    the REAL (unmocked) resolver to catch the bug.
    """

    def test_resolve_path_python_finds_python3(self, doctor: Doctor):
        """_resolve_path("python") should also try "python3" as a fallback."""
        # Real call (no mock) — depends on python3 being on PATH.
        path = doctor._resolve_path("python")
        assert path is not None, (
            "doctor._resolve_path('python') returned None even though "
            "python3 is on PATH — the resolver must also try 'python3' "
            "as a fallback for systems that ship only python3."
        )
        assert "python" in path.lower(), f"unexpected path: {path}"

    def test_check_dependencies_reports_python_installed(self, doctor: Doctor):
        """When python3 is on PATH, the 'python' dep must show installed=True."""
        results = doctor.check_dependencies()
        python_dep = next((r for r in results if r["name"] == "python"), None)
        assert python_dep is not None, "no 'python' dep in results"
        assert python_dep["installed"] is True, (
            f"python dep reported installed=False even though python3 is on PATH: {python_dep}"
        )
        assert python_dep["path"] is not None
        assert "python" in python_dep["path"].lower()
