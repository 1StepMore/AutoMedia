"""``automedia ui`` — minimal local Web UI over the SDK (#358).

A single-page app (no build chain, plain fetch) served by uvicorn on
``127.0.0.1`` only. Four zones:

- **Config** — merged config view + doctor dependency status.
- **Run** — start one pipeline run in a background thread and poll its
  ``PipelineProgress`` live.
- **Results** — project list with a JSON detail view.
- **Accounts** — list registered accounts (capture/connect stay terminal
  commands: they need a real TTY or a headed browser).

Security posture: this is a local convenience, NOT a SaaS — no auth, loopback
binding only; do not expose the port.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

import typer

logger = logging.getLogger(__name__)

app = typer.Typer(help="Minimal local web UI (loopback only).")

_DEFAULT_PORT = 8765
_INDEX_HTML_PATH = Path(__file__).parent / "ui_static" / "index.html"

_PROJECT_INFO_NAME = "00_project_info.json"

_SECRET_MARKERS = ("key", "secret", "password", "token")


def _redact(value: object) -> object:
    """Recursively redact values whose mapping key names look secret-bearing."""
    if isinstance(value, dict):
        return {
            k: (
                "…"
                if isinstance(k, str) and any(m in k.lower() for m in _SECRET_MARKERS)
                else _redact(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value

#: Run-state shared between the run thread and the progress endpoint.
_run_state: dict[str, Any] = {
    "running": False,
    "finished": True,
    "status": "",
    "progress": {},
}


def _projects_root() -> Path:
    from automedia.core.env_overlay import env_lookup

    return Path(env_lookup("AUTOMEDIA_PROJECTS_DIR", "") or os.getcwd())


def _scan_projects() -> list[dict[str, Any]]:
    """One-level project scan (same info file the projects CLI uses)."""
    items: list[dict[str, Any]] = []
    for info_file in sorted(_projects_root().glob(f"*/{_PROJECT_INFO_NAME}")):
        try:
            data = json.loads(info_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        data["_dir"] = str(info_file.parent)
        items.append(data)
    return items


def create_app() -> FastAPI:
    """Build the FastAPI app (import-gated: fastapi is an optional extra)."""
    try:
        from fastapi import Body, FastAPI, HTTPException
        from fastapi.responses import HTMLResponse
    except ImportError as exc:  # pragma: no cover - exercised via CLI hint
        raise RuntimeError("the [webui] extra is required: pip install '.[webui]'") from exc

    web = FastAPI(title="AutoMedia local UI", docs_url=None, redoc_url=None)

    @web.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML_PATH.read_text(encoding="utf-8")

    @web.get("/api/config")
    def config_view() -> dict[str, Any]:
        from automedia.core.config_loader import load_config
        from automedia.core.doctor import Doctor

        deps = [
            {"name": d["name"], "installed": d["installed"]} for d in Doctor().check_dependencies()
        ]
        try:
            cfg = load_config()
            redacted = _redact(cfg)
        except Exception:
            redacted = {}
        return {"config": redacted, "dependencies": deps}

    @web.post("/api/run")
    def run_pipeline(
        topic: str = Body(...),
        mode: str = Body("text_only"),
        brand: str = Body("default"),
    ) -> dict[str, Any]:
        if _run_state["running"]:
            raise HTTPException(status_code=409, detail="a run is already in progress")

        from automedia import run_full_pipeline
        from automedia.pipelines.gate_types import PipelineProgress

        progress = PipelineProgress()
        _run_state.update(
            running=True,
            finished=False,
            status="",
            progress=progress.get_progress(),
            tracker=progress,
        )

        def _worker() -> None:
            try:
                result = run_full_pipeline(
                    topic=topic,
                    brand=brand or "default",
                    mode=mode,
                    progress=progress,
                )
                _run_state["status"] = str(getattr(result, "status", ""))
            except Exception as exc:  # surfaced to the UI verbatim
                logger.warning("ui.run_failed: %s", exc)
                _run_state["status"] = f"failed: {exc}"
            finally:
                _run_state["running"] = False
                _run_state["finished"] = True

        threading.Thread(target=_worker, daemon=True).start()
        return {"started": True, "message": "pipeline started"}

    @web.get("/api/run/progress")
    def run_progress() -> dict[str, Any]:
        state = dict(_run_state)
        tracker = state.pop("tracker", None)
        if tracker is not None:
            state["progress"] = tracker.get_progress()
        return state

    @web.get("/api/projects")
    def projects() -> dict[str, Any]:
        items = [
            {
                "id": p.get("project_id", "?"),
                "status": p.get("status", ""),
                "topic": p.get("topic", ""),
                "dir": p.get("_dir", ""),
            }
            for p in _scan_projects()
        ]
        return {"projects": items}

    @web.get("/api/projects/{project_id}")
    def project_detail(project_id: str) -> dict[str, Any]:
        for p in _scan_projects():
            if str(p.get("project_id")) == project_id:
                safe = {
                    k: v
                    for k, v in p.items()
                    if "key" not in k.lower() and "secret" not in k.lower()
                }
                return safe
        raise HTTPException(status_code=404, detail="project not found")

    @web.get("/api/accounts")
    def accounts() -> dict[str, Any]:
        from automedia.accounts.registry import AccountRegistry

        try:
            accounts_list = AccountRegistry().list()
        except ValueError:
            return {
                "accounts": [],
                "warning": "AUTOMEDIA_MASTER_KEY 未配置，账号功能不可用",
            }
        items = [
            {
                "account_id": a["account_id"],
                "platform": a.get("platform", ""),
                "label": a.get("label", ""),
                "auth_type": a.get("auth_type", ""),
                "status": a.get("status", ""),
            }
            for a in accounts_list
        ]
        return {"accounts": items}

    return web


@app.command()
def ui(
    port: int = typer.Option(_DEFAULT_PORT, "--port", help="Local port (loopback only)"),
) -> None:
    """Serve the minimal local web UI on 127.0.0.1 (no auth — do not expose)."""
    try:
        import uvicorn
    except ImportError:
        typer.echo("The [webui] extra is required:\n  pip install '.[webui]'")
        raise typer.Exit(1) from None

    typer.echo(f"Serving AutoMedia UI on http://127.0.0.1:{port} (loopback only)")
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
