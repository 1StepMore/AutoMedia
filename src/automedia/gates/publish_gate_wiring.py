"""Shared G4/G5 wechat pre-publish wiring for every publish path.

Mirrors :mod:`automedia.gates.publish_log_wiring` (L1): one place builds the
gate contexts from real project data and runs the two checklist gates — G5
HTML hard (structural integrity of the rendered article HTML) and G4 WeChat
checklist (7-step compliance) — so the MCP ``publish_content`` flow,
``distribute_to_platforms``, and the cron runner cannot drift apart.  Both
gates are ``stop``-mode: a failed check raises
:class:`WechatChecklistGateError` and blocks the publish attempt before any
platform API call.

Issue #609 (owner decision: wiring).  The two gates were registered but sat
in no preset and on no command path (the audit's ``unreachable_gates``); the
wechat publish path is the surface the owner chose.  The wiring runs AFTER
``prepare_publish_log`` (L1) and BEFORE ``PublishEngine.publish_all``,
credential-free: content compliance is checked before any credential or
network step.  Run-tested by ``scenarios/lifecycle/g4-wechat-checklist-gate.yaml``
and ``scenarios/lifecycle/g5-html-hard-gate.yaml`` (the #585 L1-L4 precedent).

Context resolution (first non-empty wins):

* ``title`` — ``project["title"]``, ``00_project_info.json["title"]``,
  ``project["topic"]``, ``00_project_info.json["topic"]`` (the same order the
  wechat publisher's ``_read_content`` uses).
* ``content`` — ``drafts/*.html`` preferred, else ``drafts/*.md`` converted
  with the publisher's own ``_md_to_html`` (lazy import: the adapter package
  imports gates only lazily, so no module-level cycle).
* ``digest`` / ``tags`` — ``project``, then ``00_project_info.json``.
* ``cover_image`` — ``project["cover_image"]``, then
  ``00_project_info.json["cover_image"]``, then the layout convention
  ``02_images/cover/cover.png`` when it exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from automedia.core.layout import COVER_FILE, DRAFTS
from automedia.gates.base import BaseGate
from automedia.gates.html_hard import G5HtmlHard
from automedia.gates.wechat_checklist import G4WechatChecklist

_INFO_FILENAME = "00_project_info.json"


class WechatChecklistGateError(RuntimeError):
    """Raised when G4 or G5 blocks a wechat publish (stop-mode failure)."""


def _load_info(artifact_dir: str | Path) -> dict[str, Any]:
    """Read ``00_project_info.json``; a missing or broken file yields ``{}``."""
    info_path = Path(artifact_dir) / _INFO_FILENAME
    if not info_path.is_file():
        return {}
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(data, dict):
        return data
    return {}


def _resolve_cover_image(artifact_dir: Path, project: dict[str, Any], info: dict[str, Any]) -> str:
    """Resolve the cover image path for the G4 cover check."""
    raw = project.get("cover_image")
    if not raw:
        raw = info.get("cover_image")
    if not raw:
        cover_path = artifact_dir / COVER_FILE
        if cover_path.is_file():
            return str(cover_path)
        return ""
    return str(raw)


def read_article_html(artifact_dir: str | Path) -> str:
    """Read the article body the way the wechat publisher will publish it.

    ``drafts/*.html`` preferred; ``drafts/*.md`` converted with the
    publisher's own ``_md_to_html`` lazy-imported from the wechat publisher
    (the adapter package touches gates only lazily itself, so a module-level
    import here would create an import cycle).
    """
    drafts_dir = Path(artifact_dir) / DRAFTS
    if not drafts_dir.is_dir():
        return ""
    html_files = sorted(drafts_dir.glob("*.html"))
    if html_files:
        return html_files[0].read_text(encoding="utf-8")
    md_files = sorted(drafts_dir.glob("*.md"))
    if not md_files:
        return ""
    md_content = md_files[0].read_text(encoding="utf-8")
    from automedia.adapters.platforms.wechat_publisher import _md_to_html

    return _md_to_html(md_content)


def build_g4_wechat_context(artifact_dir: str | Path, project: dict[str, Any]) -> dict[str, Any]:
    """Build the G4/G5 gate context from real project data."""
    safe_project: dict[str, Any] = dict(project or {})
    info = _load_info(artifact_dir)

    raw_title = safe_project.get("title")
    if not raw_title:
        raw_title = info.get("title")
    if not raw_title:
        raw_title = safe_project.get("topic")
    if not raw_title:
        raw_title = info.get("topic")
    title = str(raw_title or "")

    raw_digest = safe_project.get("digest")
    if not raw_digest:
        raw_digest = info.get("digest")
    digest = str(raw_digest or "")

    raw_tags = safe_project.get("tags")
    if not raw_tags:
        raw_tags = info.get("tags")
    tags = [str(tag) for tag in (raw_tags or [])]

    return {
        "content": read_article_html(artifact_dir),
        "title": title,
        "digest": digest,
        "cover_image": _resolve_cover_image(Path(artifact_dir), safe_project, info),
        "tags": tags,
    }


def _failed_check_names(result: dict[str, Any]) -> str:
    """Render the failed check names of a gate result for the error message."""
    names = [
        str(check.get("name", "?"))
        for check in result.get("checks", [])
        if not check.get("passed", False)
    ]
    if not names:
        return "unknown checks"
    return ", ".join(names)


def _run_checklist_gate(gate: BaseGate, context: dict[str, Any]) -> dict[str, Any]:
    """Run one checklist gate; raise on a stop-mode failure."""
    # Protocol dispatch: ``type(gate).execute`` is the BaseGate contract
    # (every checklist gate shares the one signature).  Bound to a local name
    # so the dispatch reads as the gate-protocol call it is.
    protocol = type(gate).execute
    result = protocol(gate, dict(context))
    if not bool(result.get("passed", False)) and gate.failure_mode == "stop":
        gate_label = str(getattr(gate, "gate_name", type(gate).__name__))
        detail = ", ".join([gate_label, "blocked the wechat publish", _failed_check_names(result)])
        raise WechatChecklistGateError(detail)
    return result


def prepare_wechat_publish_gates(
    artifact_dir: str | Path,
    project: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Run the wechat pre-publish checklist gates (G5 then G4).

    Called by every wechat publish path after ``prepare_publish_log`` (L1)
    and before ``PublishEngine.publish_all``.  Raises
    :class:`WechatChecklistGateError` naming the failed checks when either
    gate fails (both are ``stop``-mode); returns both verdicts otherwise.
    """
    context = build_g4_wechat_context(artifact_dir, project)
    g5_context = {"content": context["content"], "tags": context["tags"]}
    g5_result = _run_checklist_gate(G5HtmlHard(), g5_context)
    g4_result = _run_checklist_gate(G4WechatChecklist(), context)
    return {"G5": g5_result, "G4": g4_result}
