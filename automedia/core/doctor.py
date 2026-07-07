"""Doctor — system dependency checker.

Verifies that all required tools and services are installed and available
on ``$PATH``.
"""

from __future__ import annotations

import subprocess
import shutil
from typing import Any


# ---------------------------------------------------------------------------
# Dependency definitions
# ---------------------------------------------------------------------------

_DEPENDENCIES: list[dict[str, Any]] = [
    {"name": "python", "check_cmd": ["python3", "--version"], "version_flag": "--version"},
    {"name": "bun", "check_cmd": ["bun", "--version"], "version_flag": "--version"},
    {"name": "ffmpeg", "check_cmd": ["ffmpeg", "-version"], "version_flag": "-version"},
    {"name": "whisper", "check_cmd": ["whisper", "--help"], "version_flag": None},
    {"name": "edge-tts", "check_cmd": ["edge-tts", "--help"], "version_flag": None},
    {"name": "comfyui", "check_cmd": None, "version_flag": None},  # web service — no CLI
    {"name": "chrome", "check_cmd": None, "version_flag": None},  # detected via shutil
]


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

class Doctor:
    """Inspect the runtime environment for required dependencies.

    Usage::

        doctor = Doctor()
        results = doctor.check_dependencies()
        for dep in results:
            print(f"{dep['name']}: {'✅' if dep['installed'] else '❌'}")
    """

    @staticmethod
    def _resolve_path(name: str) -> str | None:
        """Resolve the absolute path of *name* via ``shutil.which``.

        Special-cases common alternative binary names:
        - ``chrome`` → ``google-chrome``, ``chromium``, ``chromium-browser``, …
        """
        candidates = [name]
        if name == "chrome":
            candidates = [
                "google-chrome", "google-chrome-stable",
                "chromium", "chromium-browser",
                "chrome", "msedge",
            ]
        for c in candidates:
            path = shutil.which(c)
            if path:
                return path
        return None

    @staticmethod
    def _get_version(cmd: list[str]) -> str | None:
        """Run *cmd* and extract the first line as a version string.

        Returns ``None`` if the command fails or is not found.
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                first_line = (result.stdout or result.stderr or "").strip().split("\n")[0]
                return first_line or None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def check_dependencies(self) -> list[dict[str, Any]]:
        """Check every known dependency and return a list of status dicts.

        Each dict contains: ``name``, ``installed`` (bool), ``version``
        (str or ``None``), and ``path`` (str or ``None``).
        """
        results: list[dict[str, Any]] = []
        for dep in _DEPENDENCIES:
            name: str = dep["name"]
            path: str | None = self._resolve_path(name)

            if path is None:
                results.append({
                    "name": name,
                    "installed": False,
                    "version": None,
                    "path": None,
                })
                continue

            version: str | None = None
            if dep["check_cmd"] is not None:
                version = self._get_version(dep["check_cmd"])

            results.append({
                "name": name,
                "installed": True,
                "version": version,
                "path": path,
            })

        return results
