"""Doctor — system dependency checker.

Verifies that all required tools and services are installed and available
on ``$PATH`` (or reachable via HTTP in the case of ComfyUI).
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Dependency definitions
# ---------------------------------------------------------------------------

_DEPENDENCIES: list[dict[str, Any]] = [
    {"name": "python", "check_cmd": ["python3", "--version"], "version_flag": "--version"},
    {"name": "bun", "check_cmd": ["bun", "--version"], "version_flag": "--version"},
    {"name": "ffmpeg", "check_cmd": ["ffmpeg", "-version"], "version_flag": "-version"},
    {"name": "whisper", "check_cmd": ["whisper", "--help"], "version_flag": None},
    {"name": "edge-tts", "check_cmd": ["edge-tts", "--help"], "version_flag": None},
    {"name": "hyperframes", "check_cmd": ["hyperframes", "--version"], "version_flag": "--version"},
    {"name": "comfyui", "check_cmd": None, "version_flag": None},  # HTTP service check
    {"name": "chrome", "check_cmd": None, "version_flag": None},  # detected via shutil
    {"name": "llm_api", "check_cmd": None, "version_flag": None},  # API connectivity test
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# OS-specific install instructions
# ---------------------------------------------------------------------------

_INSTALL_INSTRUCTIONS: dict[str, dict[str, str]] = {
    "python": {
        "Linux": "sudo apt install python3.11  # or: sudo dnf install python3.11",
        "Darwin": "brew install python@3.11  # or download from https://www.python.org/downloads/",
        "Windows": "Download from https://www.python.org/downloads/  # or: winget install Python.Python.3.11",
    },
    "bun": {
        "Linux": "curl -fsSL https://bun.sh/install | bash",
        "Darwin": "brew install oven-sh/bun/bun  # or: curl -fsSL https://bun.sh/install | bash",
        "Windows": "powershell -c \"irm bun.sh/install.ps1 | iex\"  # or: scoop install bun",
    },
    "ffmpeg": {
        "Linux": "sudo apt install ffmpeg  # or: sudo dnf install ffmpeg",
        "Darwin": "brew install ffmpeg",
        "Windows": "winget install ffmpeg  # or: scoop install ffmpeg",
    },
    "whisper": {
        "Linux": "pip install faster-whisper",
        "Darwin": "pip install faster-whisper",
        "Windows": "pip install faster-whisper",
    },
    "edge-tts": {
        "Linux": "pip install edge-tts",
        "Darwin": "pip install edge-tts",
        "Windows": "pip install edge-tts",
    },
    "hyperframes": {
        "Linux": "npm install -g hyperframes  # or: bun install -g hyperframes",
        "Darwin": "npm install -g hyperframes  # or: bun install -g hyperframes",
        "Windows": "npm install -g hyperframes  # or: bun install -g hyperframes",
    },
    "chrome": {
        "Linux": "sudo apt install google-chrome-stable  # or: sudo apt install chromium-browser",
        "Darwin": "brew install --cask google-chrome",
        "Windows": "winget install Google.Chrome",
    },
    "comfyui": {
        "Linux": "See https://github.com/comfyanonymous/ComfyUI#installing",
        "Darwin": "See https://github.com/comfyanonymous/ComfyUI#installing",
        "Windows": "See https://github.com/comfyanonymous/ComfyUI#installing",
    },
}


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
        - ``python`` → ``python3`` (for distros that ship only ``python3``)
        """
        candidates = [name]
        if name == "chrome":
            candidates = [
                "google-chrome",
                "google-chrome-stable",
                "chromium",
                "chromium-browser",
                "chrome",
                "msedge",
            ]
        elif name == "python":
            candidates = ["python", "python3"]
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
            result = subprocess.run(  # noqa: S603 — trusted internal command
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

    @staticmethod
    def _check_comfyui_http(
        host: str = "127.0.0.1",
        port: int = 8188,
        timeout: int = 5,
    ) -> tuple[bool, str | None]:
        """Check whether ComfyUI is reachable via its HTTP API.

        Tries a ``GET`` to the root endpoint and returns ``(installed, version)``.
        Gracefully degrades when *httpx* is not installed.
        """
        try:
            import httpx  # noqa: F811
        except ImportError:
            from automedia.core._import_helpers import warn_missing_optional

            warn_missing_optional("httpx", feature="cannot check ComfyUI")
            return False, None

        base_url = f"http://{host}:{port}"
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
                resp = client.get(base_url)
                resp.raise_for_status()
                return True, f"ComfyUI API reachable at {base_url}"
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
            logger.warning("ComfyUI not reachable (%s)", exc)
            return False, None

    @staticmethod
    def _check_llm_api() -> tuple[bool, str | None]:
        """Check LLM API connectivity by sending a minimal completion.

        Gracefully degrades when the ``openai`` package is not installed.
        Returns ``(installed, version)`` where *version* is a human-readable
        status message or error detail.
        """
        try:
            from automedia.core.llm_client import llm_complete
        except ImportError:
            return False, "openai package not installed"

        try:
            llm_complete(
                prompt="Reply with exactly 'OK'.",
                max_tokens=10,
                temperature=0.0,
            )
            return True, "API reachable"
        except Exception as exc:
            msg = str(exc).strip()
            if len(msg) > 120:
                msg = msg[:117] + "..."
            return False, msg or "API check failed"

    @staticmethod
    def get_install_instructions(dep_name: str) -> str | None:
        """Return an OS-appropriate install instruction for *dep_name*.

        Returns ``None`` if no instruction is available for the dependency
        or the current OS.
        """
        instructions = _INSTALL_INSTRUCTIONS.get(dep_name)
        if instructions is None:
            return None
        system = platform.system()
        return instructions.get(system)

    def check_dependencies(self) -> list[dict[str, Any]]:
        """Check every known dependency and return a list of status dicts.

        Each dict contains: ``name``, ``installed`` (bool), ``version``
        (str or ``None``), and ``path`` (str or ``None``).
        """
        results: list[dict[str, Any]] = []
        for dep in _DEPENDENCIES:
            name: str = dep["name"]
            path: str | None = self._resolve_path(name)

            # --- Special case: ComfyUI is an HTTP service ------------------
            if name == "comfyui":
                installed, version = self._check_comfyui_http()
                results.append(
                    {
                        "name": name,
                        "installed": installed,
                        "version": version,
                        "path": None,
                    }
                )
                continue

            # --- LLM API connectivity check -------------------------------
            if name == "llm_api":
                installed, version = self._check_llm_api()
                results.append({
                    "name": name,
                    "installed": installed,
                    "version": version,
                    "path": None,
                })
                continue

            # --- Standard CLI-based check ---------------------------------
            if path is None:
                results.append(
                    {
                        "name": name,
                        "installed": False,
                        "version": None,
                        "path": None,
                    }
                )
                continue

            dep_version: str | None = None
            if dep["check_cmd"] is not None:
                dep_version = self._get_version(dep["check_cmd"])

            results.append(
                {
                    "name": name,
                    "installed": True,
                    "version": dep_version,
                    "path": path,
                }
            )

        return results
