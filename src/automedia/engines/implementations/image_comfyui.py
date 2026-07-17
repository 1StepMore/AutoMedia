"""ComfyUI image generation engine — HTTP API client.

Extracted from :mod:`automedia.pipelines.image_pipeline` and converted
to a proper :class:`BaseImageEngine` subclass with **no PIL fallback**.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any, ClassVar

from automedia.engines.base import BaseImageEngine
from automedia.engines.errors import EngineExecutionError

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


class ComfyUIImageEngine(BaseImageEngine):
    """Image generation engine that drives ComfyUI via its HTTP API.

    Sends a workflow JSON to ``POST /prompt``, polls for completion, and
    downloads the resulting image.  **Never** falls back to PIL — raises
    :class:`EngineExecutionError` on any failure.

    Config keys (read from ``self._config``):

    * ``host`` (default ``"127.0.0.1"``)
    * ``port`` (default ``8188``)
    * ``protocol`` (default ``"http"``)
    * ``timeout`` (default ``300``)
    """

    engine_name: ClassVar[str] = "comfyui"
    modality: ClassVar[str] = "image"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_available(self) -> tuple[bool, str]:
        """Check whether the ComfyUI server is reachable.

        Performs an HTTP GET to ``{protocol}://{host}:{port}``.
        Returns ``(True, ...)`` on success, ``(False, ...)`` on any failure.
        """
        host = self._config.get("host", "127.0.0.1")
        port = self._config.get("port", 8188)
        protocol = self._config.get("protocol", "http")
        base_url = f"{protocol}://{host}:{port}"

        try:
            import httpx  # noqa: F811
        except ImportError as exc:
            return False, f"httpx not installed: {exc}"

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(base_url)
                resp.raise_for_status()
                return True, f"ComfyUI reachable at {base_url}"
        except Exception as exc:
            return False, f"ComfyUI not reachable at {base_url}: {exc}"

    def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        output_path: str,
    ) -> str:
        """Generate an image via the ComfyUI HTTP API.

        Args:
            prompt: Text description of the desired image.
            width: Desired image width in pixels.
            height: Desired image height in pixels.
            output_path: Path where the generated image is saved.

        Returns:
            The absolute path to the generated image.

        Raises:
            EngineExecutionError: If httpx is missing, ComfyUI is
                unreachable, or the workflow fails at any step.
        """
        host = self._config.get("host", "127.0.0.1")
        port = self._config.get("port", 8188)
        protocol = self._config.get("protocol", "http")
        timeout = self._config.get("timeout", 300)
        base_url = f"{protocol}://{host}:{port}"

        # ---- Lazy import httpx ----
        try:
            import httpx  # noqa: F811
        except ImportError as exc:
            raise EngineExecutionError(
                self.engine_name,
                f"httpx is required for ComfyUI: {exc}",
            ) from exc

        # ---- Build workflow ----
        workflow = self._build_workflow(prompt, width, height)

        # ---- Execute via ComfyUI HTTP API ----
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
                # a) POST workflow to /prompt
                resp = client.post(f"{base_url}/prompt", json={"prompt": workflow})
                resp.raise_for_status()
                prompt_data = resp.json()
                prompt_id = prompt_data.get("prompt_id")
                if not prompt_id:
                    raise RuntimeError(
                        f"No prompt_id in ComfyUI response: {prompt_data}"
                    )

                # b) Poll /history/{prompt_id} until completed
                self._poll_comfyui(client, base_url, prompt_id, timeout)

                # c) Get output filename from history
                history_resp = client.get(f"{base_url}/history/{prompt_id}")
                history_resp.raise_for_status()
                history = history_resp.json()
                output_filename = self._extract_output_filename(history, prompt_id)

                # d) Download image via /view
                download_resp = client.get(
                    f"{base_url}/view",
                    params={"filename": output_filename},
                )
                download_resp.raise_for_status()

                # e) Write image to disk
                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(download_resp.content)

                logger.info("ComfyUI generated image → %s", output_path)
                return os.path.abspath(output_path)

        except EngineExecutionError:
            raise
        except httpx.TimeoutException as exc:
            raise EngineExecutionError(
                self.engine_name,
                f"ComfyUI at {host}:{port}: request timed out after {timeout}s",
                cause=exc,
            ) from exc
        except httpx.ConnectError as exc:
            raise EngineExecutionError(
                self.engine_name,
                f"ComfyUI at {host}:{port}: connection refused",
                cause=exc,
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise EngineExecutionError(
                self.engine_name,
                f"ComfyUI at {host}:{port}: HTTP {exc.response.status_code}",
                cause=exc,
            ) from exc
        except Exception as exc:
            raise EngineExecutionError(
                self.engine_name,
                f"ComfyUI at {host}:{port}: {exc}",
                cause=exc,
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_workflow(
        self,
        prompt: str,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        """Build a ComfyUI workflow dict from *prompt* and dimensions.

        Subclasses may override to customise the node graph structure.

        Returns a dict with keys ``prompt``, ``width``, ``height``, and
        ``filename`` (a timestamped unique filename).
        """
        return {
            "prompt": prompt,
            "width": width,
            "height": height,
            "filename": f"comfyui_{int(time.time())}.png",
        }

    @staticmethod
    def _poll_comfyui(
        client: httpx.Client,  # noqa: F821  — guarded by TYPE_CHECKING
        base_url: str,
        prompt_id: str,
        timeout: int,
    ) -> None:
        """Poll the ComfyUI ``/history`` endpoint until the prompt completes.

        Raises:
            TimeoutError: If the prompt does not complete within *timeout* seconds.
        """
        start = time.monotonic()
        poll_interval = 1.0

        while (time.monotonic() - start) < timeout:
            resp = client.get(f"{base_url}/history/{prompt_id}")
            resp.raise_for_status()
            history = resp.json()
            prompt_entry = history.get(prompt_id, {})
            if prompt_entry.get("status", {}).get("completed") is True:
                return
            time.sleep(poll_interval)

        raise TimeoutError(
            f"ComfyUI prompt {prompt_id} did not complete within {timeout}s",
        )

    @staticmethod
    def _extract_output_filename(history: dict[str, Any], prompt_id: str) -> str:
        """Extract the first output image filename from a ComfyUI history response."""
        outputs = history.get(prompt_id, {}).get("outputs", {})
        for _node_id, node_output in outputs.items():
            images = node_output.get("images", [])
            if images:
                filename = images[0].get("filename")
                if filename:
                    return filename
        raise RuntimeError(
            f"No output image found in ComfyUI history for prompt {prompt_id}",
        )
