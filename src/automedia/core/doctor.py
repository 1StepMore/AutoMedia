"""Doctor — system dependency checker.

Verifies that all required tools and services are installed and available
on ``$PATH`` (or reachable via HTTP in the case of ComfyUI).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
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
    {
        "name": "comfyui_upscale_model",
        "check_cmd": None,
        "version_flag": None,
    },  # model file presence (informational)
    {"name": "chrome", "check_cmd": None, "version_flag": None},  # detected via shutil
    {"name": "llm_api", "check_cmd": None, "version_flag": None},  # API connectivity test
]

logger = structlog.get_logger(__name__)

# Bounded LLM probe: cap the whole probe so a hanging provider cannot block
# ``automedia doctor`` for the SDK's default multi-retry × 600 s timeout.
_LLM_PROBE_TIMEOUT_S = 15.0
_LLM_PROBE_MAX_ATTEMPTS = 1

# ``hyperframes browser path`` is a local lookup; bound it so a wedged process
# cannot hang ``automedia doctor``.
_HYPERFRAMES_BROWSER_TIMEOUT_S = 15.0

# LLM task slots whose ``provider`` must never be an explicit empty string
# (issue #208). Slots absent from the config are skipped by
# ``_iter_provider_specs``, so only an explicitly blank provider is reported.
_LLM_TASK_SLOTS = ("text_generation", "vision", "subtitle_proofread", "translation")

# ---------------------------------------------------------------------------
# OS-specific install instructions
# ---------------------------------------------------------------------------

_INSTALL_INSTRUCTIONS: dict[str, dict[str, str]] = {
    "python": {
        "Linux": "sudo apt install python3.11  # or: sudo dnf install python3.11",
        "Darwin": "brew install python@3.11  # or download from https://www.python.org/downloads/",
        "Windows": "Download from https://www.python.org/downloads/  "
        "# or: winget install Python.Python.3.11",
    },
    "bun": {
        "Linux": "curl -fsSL https://bun.sh/install | bash",
        "Darwin": "brew install oven-sh/bun/bun  # or: curl -fsSL https://bun.sh/install | bash",
        "Windows": 'powershell -c "irm bun.sh/install.ps1 | iex"  # or: scoop install bun',
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
        "Linux": "npm install -g hyperframes  # or: bun install -g hyperframes\n"
        "Required for auto/video_only pipeline modes (video production).",
        "Darwin": "npm install -g hyperframes  # or: bun install -g hyperframes\n"
        "Required for auto/video_only pipeline modes (video production).",
        "Windows": "npm install -g hyperframes  # or: bun install -g hyperframes\n"
        "Required for auto/video_only pipeline modes (video production).",
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
    "comfyui_upscale_model": {
        "Linux": (
            "Download RealESRGAN_x4plus.pth from\n"
            "  https://github.com/xinntao/Real-ESRGAN/releases\n"
            "and place it in <ComfyUI>/models/upscale_models/.\n"
            "Then set image.comfyui.comfyui_models_path in .automedia/config.yaml\n"
            "so 'automedia doctor' can verify it."
        ),
        "Darwin": (
            "Download RealESRGAN_x4plus.pth from\n"
            "  https://github.com/xinntao/Real-ESRGAN/releases\n"
            "and place it in <ComfyUI>/models/upscale_models/.\n"
            "Then set image.comfyui.comfyui_models_path in .automedia/config.yaml\n"
            "so 'automedia doctor' can verify it."
        ),
        "Windows": (
            "Download RealESRGAN_x4plus.pth from\n"
            "  https://github.com/xinntao/Real-ESRGAN/releases\n"
            "and place it in <ComfyUI>\\models\\upscale_models\\.\n"
            "Then set image.comfyui.comfyui_models_path in .automedia/config.yaml\n"
            "so 'automedia doctor' can verify it."
        ),
    },
}

# ---------------------------------------------------------------------------
# Headless Chrome dependencies (per-platform)
# ---------------------------------------------------------------------------

_HEADLESS_CHROME_DEPENDENCIES: dict[str, str] = {
    "Linux": (
        "sudo apt install -y libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 "
        "libcups2t64 libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 "
        "libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64"
    ),
    "Darwin": "Chrome headless should work out of the box on macOS.",
    "Windows": "Chrome headless should work out of the box on Windows.",
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
    def _hyperframes_browser_path() -> str | None:
        """Return the Chrome executable hyperframes will actually render with.

        hyperframes manages its own headless shell, so it — not ``$PATH`` — is
        the authority for the real render path.  Under WSL the ``google-chrome``
        on ``$PATH`` is frequently a shim that ``exec``s a Windows ``chrome.exe``
        which cannot run headless; asking hyperframes sidesteps that false alarm.

        Returns ``None`` when hyperframes is absent, errors/times out, or
        reports a path that does not exist on disk.
        """
        exe = shutil.which("hyperframes")
        if exe is None:
            return None
        try:
            result = subprocess.run(  # noqa: S603 — trusted internal command
                [exe, "browser", "path"],
                capture_output=True,
                text=True,
                timeout=_HYPERFRAMES_BROWSER_TIMEOUT_S,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        for line in reversed((result.stdout or "").splitlines()):
            candidate = line.strip()
            if candidate and Path(candidate).is_file():
                return candidate
        return None

    def _resolve_chrome(self) -> str | None:
        """Resolve the Chrome that will actually be used for rendering.

        Ask hyperframes first (the render authority); fall back to ``$PATH``
        probing only when hyperframes is unavailable.
        """
        return self._hyperframes_browser_path() or self._resolve_path("chrome")

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
            import httpx
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
    def _check_comfyui_upscale_model() -> tuple[bool | None, str | None]:
        """Check whether the ComfyUI upscale model file is present on disk.

        The built-in SD1.5 workflow generates at the model's native resolution
        and then upscales with an ESRGAN model (``image.comfyui.upscale_model``,
        default ``RealESRGAN_x4plus.pth``). A missing model is **not** silently
        degraded by the engine — ComfyUI errors and the pipeline raises
        ``EngineExecutionError``. This check surfaces that requirement up front.

        Returns ``(ok, message)`` where *ok* is tri-state:

        - ``True``  — the configured models path is set and the file exists.
        - ``False`` — the path is set but the file is missing (actionable).
        - ``None``  — ``comfyui_models_path`` is not configured, so presence
          cannot be determined. This is deliberately *not* reported as a
          failure: ComfyUI may run remotely, in Docker, or on another host, and
          guessing a filesystem location would produce false alarms.

        To make this check meaningful, set the models path::

            engines:
              image:
                comfyui:
                  comfyui_models_path: /opt/ComfyUI/models
        """
        from automedia.core.config_loader import load_config

        try:
            config = load_config()
        except Exception:
            return None, "config unavailable; cannot verify upscale model"

        comfyui_cfg = ((config.get("engines") or {}).get("image") or {}).get("comfyui") or {}
        model_name = str(comfyui_cfg.get("upscale_model") or "RealESRGAN_x4plus.pth")
        models_path = comfyui_cfg.get("comfyui_models_path")

        if not models_path:
            return None, (
                f"cannot verify {model_name}: set engines.image.comfyui.comfyui_models_path "
                "to your ComfyUI models directory"
            )

        candidate = Path(str(models_path)) / "upscale_models" / model_name
        if candidate.is_file():
            return True, f"upscale model present: {candidate}"
        return False, (
            f"upscale model missing: {candidate} — the ComfyUI image pipeline "
            "will fail at generation time until this file exists"
        )

    @staticmethod
    def _empty_provider_slots(config: dict[str, Any]) -> list[str]:
        """Return the LLM slots whose ``provider`` is an explicit empty string.

        Issue #208: ``provider: ''`` used to pass silently.  An empty provider
        resolves at runtime through the environment/credential lookup, so a
        clobbered ``model_config.yaml`` still produced "API reachable" from
        ``automedia doctor`` — the corruption was invisible in the one check
        an operator runs after a bad automated write.

        A slot that omits ``provider`` entirely is *not* reported here: the
        runtime implies "openai" for it, so it is not the broken state this
        check exists to surface.
        """
        from automedia.core.llm_client import _iter_provider_specs

        empty: list[str] = []
        for slot in _LLM_TASK_SLOTS:
            for spec in _iter_provider_specs(config, slot):
                provider = spec.get("provider")
                if "provider" in spec and not str(provider or "").strip():
                    empty.append(slot)
                    break
        return empty

    @staticmethod
    def _check_llm_chain(config: dict[str, Any]) -> tuple[bool, str | None]:
        """Dry-run build every spec in the ``text_generation`` provider chain.

        ``_build_client`` is called for each spec — construction only, no
        request is sent.  This turns a silently-broken fallback (the kind that
        an empty ``api_key: ''`` used to produce) into an up-front
        ``automedia doctor`` failure instead of a surprise when the chain
        actually fails over.

        The primary spec (index 0) is probed live by :meth:`_check_llm_api`;
        a construction failure there is left to that probe so it cannot mask a
        primary the live probe would otherwise resolve.  Every fallback spec is
        validated strictly and named in the returned message by
        provider/model/base_url.

        An explicitly empty ``provider`` is the exception: it is reported here
        even on the primary, because the live probe would resolve it through
        the environment fallback and mask the corruption (issue #208).
        """
        from automedia.core.llm_client import _build_client, _iter_provider_specs

        empty_slots = Doctor._empty_provider_slots(config)
        if empty_slots:
            return False, (
                f"llm.{empty_slots[0]}.provider is empty in the resolved model "
                "config — set a real provider (e.g. openai, deepseek) in "
                "model_config.yaml or via the AUTOMEDIA_* credential env vars; "
                "an empty provider resolves to nothing at runtime."
            )

        specs = _iter_provider_specs(config, "text_generation")
        for index, spec in enumerate(specs):
            try:
                _build_client(config, task_type="text_generation", provider_spec=spec)
            except Exception as exc:
                if index == 0:
                    # Primary: the live probe below owns this failure.
                    continue
                provider = spec.get("provider") or "?"
                model = spec.get("model") or "?"
                base_url = spec.get("base_url") or "(default)"
                return False, (
                    f"fallback[{index}] provider={provider!r} model={model!r} "
                    f"base_url={base_url!r} cannot be constructed: {exc}"
                )
        return True, None

    @staticmethod
    def _check_llm_api() -> tuple[bool, str | None]:
        """Check LLM API connectivity by sending a minimal completion.

        Gracefully degrades when the ``openai`` package is not installed.
        Returns ``(installed, version)`` where *version* is a human-readable
        status message or error detail.

        The probe is bounded: each provider spec gets a single attempt with a
        ``_LLM_PROBE_TIMEOUT_S`` timeout, so a blackholing host cannot hang the
        whole ``doctor`` run.  Fake-LLM mode is resolved from the *same* merged
        config the probe would use (env var OR ``llm.fake_mode``), and is
        reported as not-reachable rather than a false-positive "API reachable".

        Before contacting the network, every fallback spec in the chain is
        dry-run built by :meth:`_check_llm_chain` so an unusable fallback is
        reported instead of silently dropped.
        """
        try:
            from automedia.core.llm_client import _is_fake_mode, llm_complete
        except ImportError:
            return False, "openai package not installed"

        from automedia.core.config_loader import load_config

        try:
            config = load_config()
        except Exception as exc:
            msg = str(exc).strip()
            if len(msg) > 120:
                msg = msg[:117] + "..."
            return False, msg or "config load failed"

        if _is_fake_mode(config):
            return False, "fake LLM mode active — provider API not contacted"

        chain_ok, chain_message = Doctor._check_llm_chain(config)
        if not chain_ok:
            return False, chain_message

        try:
            llm_complete(
                prompt="Reply with exactly 'OK'.",
                max_tokens=10,
                temperature=0.0,
                timeout=_LLM_PROBE_TIMEOUT_S,
                max_attempts=_LLM_PROBE_MAX_ATTEMPTS,
            )
            return True, "API reachable"
        except Exception as exc:
            msg = str(exc).strip()
            if len(msg) > 120:
                msg = msg[:117] + "..."
            return False, msg or "API check failed"

    @staticmethod
    def _check_chrome_headless(chrome_path: str) -> tuple[bool, str | None]:
        """Verify *chrome_path* can start in headless mode.

        Runs ``chrome --headless --no-sandbox --disable-gpu --dump-dom about:blank``
        with a 10-second timeout. Returns ``(True, None)`` on success, or
        ``(False, error_message)`` on any failure.
        """
        try:
            result = subprocess.run(  # noqa: S603 — trusted internal command
                [
                    chrome_path,
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--dump-dom",
                    "about:blank",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True, None
            return False, (
                f"headless check failed (exit {result.returncode}): {result.stderr[:200].strip()}"
            )
        except FileNotFoundError:
            return False, "chrome binary not found at resolved path"
        except subprocess.TimeoutExpired:
            return False, "headless check timed out after 10s"
        except Exception as exc:
            return False, f"headless check error: {exc}"

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

    @classmethod
    def get_headless_chrome_instructions(cls) -> str | None:
        """Return OS-appropriate install instructions for headless Chrome deps."""
        system = platform.system()
        return _HEADLESS_CHROME_DEPENDENCIES.get(system)

    @staticmethod
    def _is_wsl() -> bool:
        """Best-effort detection of a Windows Subsystem for Linux environment."""
        if "microsoft" in platform.release().lower():
            return True
        return bool(os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"))

    @staticmethod
    def _is_windows_side_chrome(path: str) -> bool:
        """Whether *path* points at a Windows Chrome (or a shim that execs one).

        Covers the two shapes seen under WSL: a direct ``/mnt/c/.../chrome.exe``
        and a tiny shell script (e.g. ``~/.local/bin/google-chrome``) whose body
        invokes ``chrome.exe``.  Such a binary cannot run headless from WSL.
        """
        if not path:
            return False
        normalised = path.replace("\\", "/").lower()
        if normalised.endswith(".exe") or normalised.startswith("/mnt/"):
            return True
        try:
            if os.path.isfile(path) and os.path.getsize(path) < 8192:
                with open(path, "rb") as fh:
                    head = fh.read(8192).decode("utf-8", "ignore").lower()
                if "chrome.exe" in head:
                    return True
        except OSError:
            pass
        return False

    @classmethod
    def chrome_remediation(cls, dep: dict[str, Any]) -> str | None:
        """Return an actionable next step for the chrome check's outcome.

        Distinguishes the two failure shapes surfaced by
        :meth:`check_dependencies`:

        * browser not found at all; and
        * browser found but unable to run headless.

        Under WSL either shape, when caused by a Windows-side Chrome, must point
        at a Linux browser (or hyperframes' bundled headless shell) instead of
        the unrelated Linux shared-library ``apt`` advice.
        """
        path = str(dep.get("path") or "")
        if not dep.get("installed"):
            if cls._is_wsl():
                return (
                    "No Linux Chrome/Chromium found. A Windows browser cannot be "
                    "driven headless from WSL — install a Linux Chrome/Chromium, "
                    "or rely on hyperframes' bundled headless shell: "
                    "`hyperframes browser ensure`."
                )
            return None
        if dep.get("headless_ok") is False:
            if cls._is_wsl() and cls._is_windows_side_chrome(path):
                return (
                    "Only a Windows-side Chrome was found, which cannot run "
                    "headless from WSL. Install a Linux Chrome/Chromium — or just "
                    "use hyperframes' bundled headless shell: "
                    "`hyperframes browser ensure`."
                )
            return cls.get_headless_chrome_instructions()
        return None

    def check_dependencies(self) -> list[dict[str, Any]]:
        """Check every known dependency and return a list of status dicts.

        Each dict contains: ``name``, ``installed`` (bool), ``version``
        (str or ``None``), and ``path`` (str or ``None``).
        """
        results: list[dict[str, Any]] = []
        for dep in _DEPENDENCIES:
            name: str = dep["name"]
            path: str | None = None

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
                results.append(
                    {
                        "name": name,
                        "installed": installed,
                        "version": version,
                        "path": None,
                    }
                )
                continue

            # --- ComfyUI upscale model presence (informational) -----------
            if name == "comfyui_upscale_model":
                ok, message = self._check_comfyui_upscale_model()
                results.append(
                    {
                        "name": name,
                        # ``ok`` is tri-state. Never report an unverifiable
                        # model as installed=False: ComfyUI may be remote or in
                        # Docker, so a guess here would raise false alarms.
                        "installed": ok is not False,
                        "version": None,
                        "path": None,
                        "model_present": ok,
                        "model_message": message,
                    }
                )
                continue

            # --- Chrome headless probe --------------------------------------
            if name == "chrome":
                path = self._resolve_chrome()
                if path is None:
                    results.append(
                        {
                            "name": name,
                            "installed": False,
                            "version": None,
                            "path": None,
                            "headless_ok": False,
                            "headless_message": None,
                        }
                    )
                    continue

                headless_ok, headless_message = self._check_chrome_headless(path)
                results.append(
                    {
                        "name": name,
                        "installed": True,
                        "version": None,
                        "path": path,
                        "headless_ok": headless_ok,
                        "headless_message": headless_message,
                    }
                )
                continue

            # --- Standard CLI-based check ---------------------------------
            path = self._resolve_path(name)
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
