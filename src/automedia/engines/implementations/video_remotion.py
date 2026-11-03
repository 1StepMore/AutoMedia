"""Remotion video engine — the motion-track renderer (#351).

Renders the narration-aligned storyboard through Remotion (React), executing
Node-side tooling inside WSL when the host is Windows (``engines.video.
remotion.wsl_dist``) or natively when Node/remotion live on this machine.

Workspace layout (``engines.video.remotion.project_dir``, default
``~/.automedia/remotion-workspace`` — one ``npm i remotion @remotion/cli``
install reused by every render):

    workspace/
      node_modules/…           installed once (npm mirror in CN setups)
      src/index.ts             entry (shipped template)
      src/Root.tsx             composition registration (shipped template)
      src/composition.tsx      motion-grammar composition (shipped template)
      input/storyboard.json    per-render storyboard (regenerated)
      input/public/…           per-render media + audio (regenerated)

Rendering: ``npx remotion render AutoMedia <out> --props input/storyboard.json``
with the browser pinned to a machine-local Chromium via
``--browser-executable`` (Remotion's own Chrome-for-Testing download is
unreachable from some networks).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from typing_extensions import override

from automedia.engines.base import BaseVideoEngine
from automedia.engines.errors import EngineExecutionError

logger = logging.getLogger(__name__)

_DEFAULT_WORKSPACE = Path.home() / ".automedia" / "remotion-workspace"
_PROVISION_TIMEOUT: int = 120
_RENDER_TIMEOUT: int = 900


def _wsl_arg_paths(paths: list[str]) -> list[str]:
    """Translate Windows paths to WSL form for a wsl.exe invocation."""
    translated: list[str] = []
    pattern = re.compile(r"^([A-Za-z]):[\\/](.*)$")
    for p in paths:
        m = pattern.match(p)
        if m:
            drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
            translated.append(f"/mnt/{drive}/{rest}")
        else:
            translated.append(p)
    return translated


class VideoRemotionEngine(BaseVideoEngine):
    """Video engine backed by a Remotion workspace (WSL or native Node).

    Attributes
    ----------
    engine_name : str
        Registration key in the :class:`EngineRegistry` (``"remotion"``).
    modality : str
        Modality grouping (``"video"``).
    """

    engine_name: ClassVar[str] = "remotion"
    modality: ClassVar[str] = "video"

    # ------------------------------------------------------------------
    # Environment resolution
    # ------------------------------------------------------------------

    def _workspace(self) -> Path:
        return Path(str(self._config.get("project_dir") or _DEFAULT_WORKSPACE))

    def _wsl_dist(self) -> str | None:
        """Return the WSL distro to execute Node in, or None for native Node.

        ``wsl_dist: ""`` forces native Node; unset on a Windows host selects
        the default distro automatically.
        """
        explicit = self._config.get("wsl_dist")
        if explicit is not None:
            return str(explicit) or None
        if os.name == "nt" and shutil.which("wsl.exe"):
            return "Ubuntu"
        return None

    def _browser_flag(self) -> bool:
        """A usable browser was configured (Windows file or WSL-side path)."""
        browser = self._config.get("browser_executable")
        if not browser:
            return False
        s = str(browser)
        # posix-absolute paths live inside the WSL filesystem — the Windows
        # side cannot stat them; trust the config (check_available-style
        # diagnostics surface errors from remotion itself).
        return s.startswith("/") or Path(s).is_file()

    def _browser_arg(self) -> str:
        """The browser path as the Node side should see it."""
        browser = str(self._config.get("browser_executable") or "")
        if browser.startswith("/"):
            return browser
        return _wsl_arg_paths([browser])[0]

    def _node_cmd(
        self, args: list[str], cwd: Path, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        """Run a Node-side command in the workspace (WSL or native)."""
        dist = self._wsl_dist()
        if dist:
            wsl_args = _wsl_arg_paths([str(cwd), *args])
            # cd INSIDE the bash script: wsl.exe --cd chokes on non-ASCII
            # paths (Wsl/ERROR_PATH_NOT_FOUND), while a UTF-8 script body is
            # safe. -e executes directly (no extra shell re-parsing).
            script = (
                f"cd {shlex.quote(wsl_args[0])} && "
                "export PATH=$HOME/.local/bin:$HOME/.npm-global/bin:$PATH && "
                + " ".join(shlex.quote(a) for a in wsl_args[1:])
            )
            cmd = [
                "wsl.exe",
                "-d",
                dist,
                "-e",
                "bash",
                "-lc",
                script,
            ]
        else:
            cmd = args
        env = os.environ.copy()
        browser: Any = self._config.get("browser_executable")
        if self._browser_flag():
            env["REMOTION_BROWSER_EXECUTABLE"] = str(browser)
        return subprocess.run(  # noqa: S603 — argv assembled from config
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=None if dist else str(cwd),
            env=env,
        )

    def _provision_workspace_sources(self) -> None:
        """Copy the shipped template sources into the workspace (idempotent)."""
        import importlib.resources

        templates = importlib.resources.files("automedia.templates.remotion")
        src_dir = self._workspace() / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        for name in ("index.ts", "Root.tsx", "composition.tsx"):
            content = templates.joinpath(name).read_text(encoding="utf-8")
            (src_dir / name).write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Dependency check
    # ------------------------------------------------------------------

    @override
    def check_available(self) -> tuple[bool, str]:
        """Verify WSL/Node + workspace + remotion install, with diagnostics."""
        dist = self._wsl_dist()
        workspace = self._workspace()
        if dist is None and not shutil.which("node"):
            return False, "node not found on PATH (and no WSL distro configured)"

        probe = self._node_cmd(["node", "--version"], workspace, timeout=60)
        if probe.returncode != 0:
            return False, (
                f"node probe failed inside {'WSL(' + dist + ')' if dist else 'native'}: "
                f"{(probe.stderr or probe.stdout or '').strip()[:200]}"
            )

        if not (workspace / "node_modules" / "remotion").is_dir():
            return False, (
                f"remotion is not installed in the workspace {workspace} — "
                "run: npm i remotion @remotion/cli react react-dom "
                "(npm mirror: --registry=https://registry.npmmirror.com)"
            )
        return True, f"remotion workspace ready at {workspace} (node {probe.stdout.strip()})"

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    @override
    def render(self, assets: dict[str, Any], output_path: str) -> str:
        """Render the narration-aligned storyboard through Remotion.

        ``assets`` follows the HyperFrames contract plus the #351 timeline:

        - ``scenes``: per-scene ``{index, text, start, duration, ...}`` in
          **seconds** (from ``video_timeline.build_scene_timeline``) — required;
          without a timeline the engine refuses (the legacy even-split shape is
          the hyperframes track's job).
        - ``audio``: narration track path; ``scene_media``: per-scene images;
          ``title``: film title.
        """
        scenes: list[dict[str, Any]] = list(assets.get("scenes") or [])
        if not scenes:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=(
                    "remotion render requires a narration-aligned scene timeline "
                    "(assets['scenes'] from video_timeline.build_scene_timeline)"
                ),
            )

        available, why = self.check_available()
        if not available:
            raise EngineExecutionError(engine_name=self.engine_name, details=why)

        fps = int(self._config.get("fps", 30))
        width = int(self._config.get("width", 1920))
        height = int(self._config.get("height", 1080))
        scene_media = list(assets.get("scene_media") or [])
        audio_path = str(assets.get("audio") or "")

        workspace = self._workspace()
        self._provision_workspace_sources()

        input_dir = workspace / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        # Remotion serves staticFile() from <workspace>/public — the input/
        # subdir only holds the storyboard (its path is passed via --props).
        public_dir = workspace / "public"
        public_dir.mkdir(parents=True, exist_ok=True)

        # media + audio into the workspace public dir (remotion staticFile root)
        # staticFile() resolves against the public dir — store BARE names
        public_files: dict[str, str] = {}
        for i, media in enumerate(scene_media):
            if media and os.path.isfile(media):
                dest = f"media-{i + 1:02d}{os.path.splitext(media)[1] or '.png'}"
                shutil.copy2(media, public_dir / dest)
                public_files[i] = dest
        audio_name = ""
        if audio_path and os.path.isfile(audio_path):
            audio_name = "narration" + (os.path.splitext(audio_path)[1] or ".mp3")
            shutil.copy2(audio_path, public_dir / audio_name)

        storyboard: dict[str, Any] = {
            "fps": fps,
            "width": width,
            "height": height,
            "audio": audio_name,
            "scenes": [
                {
                    "index": int(s.get("index", i + 1)),
                    "text": str(s.get("text", "")),
                    "title": str(s.get("text", ""))[:24],
                    "startFrame": round(float(s.get("start", 0.0)) * fps),
                    "durationFrames": max(1, round(float(s.get("duration", 0.0)) * fps)),
                    "media": public_files.get(i, ""),
                }
                for i, s in enumerate(scenes)
            ],
        }
        storyboard_file = input_dir / "storyboard.json"
        # --props replaces the component's TOP-LEVEL props — the composition
        # reads props.storyboard, so wrap the payload accordingly.
        storyboard_file.write_text(
            json.dumps({"storyboard": storyboard}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        browser_flag = ["--browser-executable", self._browser_arg()] if self._browser_flag() else []

        out_wsl = _wsl_arg_paths([output_path])[0]
        render_args = [
            "npx",
            "remotion",
            "render",
            "AutoMedia",
            out_wsl,
            "--props",
            "input/storyboard.json",
            "--log",
            "error",
            *browser_flag,
        ]
        logger.info(
            "remotion render: %d scenes, %.1fs storyboard → %s",
            len(storyboard["scenes"]),
            sum(float(s.get("duration", 0.0)) for s in scenes),
            output_path,
        )
        timeout = int(self._config.get("timeout", _RENDER_TIMEOUT))
        try:
            result = self._node_cmd(render_args, workspace, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=f"remotion render timed out after {timeout}s",
            ) from exc
        if result.returncode != 0 or not os.path.isfile(output_path):
            raise EngineExecutionError(
                engine_name=self.engine_name,
                details=(
                    f"remotion render failed (exit {result.returncode}).\n"
                    f"stdout: {(result.stdout or '')[-800:]}\n"
                    f"stderr: {(result.stderr or '')[-800:]}"
                ),
            )
        logger.info("remotion render succeeded (%s)", output_path)
        return os.path.abspath(output_path)
