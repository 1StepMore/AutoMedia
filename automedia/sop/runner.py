"""SOP Runner — generates execution handbooks, daily tasks, and progress reports."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

TEMPLATES_DIR = Path(__file__).parent / "templates"
DEFAULT_OVERRIDES_DIR = Path.home() / ".automedia" / "sop" / "overrides"

# Regex to find template tags: {{ expr }}, {% statement %}
_TAG_RE = re.compile(r"\{\{.+?\}\}|\{%.+?%\}")


def _render_template(template_name: str, context: dict[str, Any]) -> str:
    """Simple inline template renderer (no Jinja2 dependency required).

    Supports ``{{ key }}`` variable substitution, ``{% for item in list %}``
    loops, and ``{% if var %}`` conditionals (with ``{% endif %}`` closing).
    If blocks may wrap for blocks.
    """
    text = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    return _render_string(text, context)


def _render_string(text: str, context: dict[str, Any]) -> str:
    """Render a template string with the given *context*."""
    out: list[str] = []
    pos = 0

    while pos < len(text):
        # Find the next tag
        m = _TAG_RE.search(text, pos)
        if not m:
            out.append(text[pos:])
            break

        # Emit literal text before the tag
        out.append(text[pos : m.start()])

        tag = m.group(0)

        # ── Variable substitution ──────────────────────────────────────
        if tag.startswith("{{"):
            key = tag[2:-2].strip()
            out.append(str(context.get(key, tag)))
            pos = m.end()
            continue

        # ── Block tags ─────────────────────────────────────────────────
        #   {% if <var> %}        ...   {% endif %}
        #   {% for <x> in <y> %}  ...   {% endfor %}
        tag_content = tag[2:-2].strip()

        # --- if / endif ---
        if tag_content.startswith("if "):
            cond_var = tag_content.split(maxsplit=1)[1]
            # Find matching {% endif %}
            endif_pos = _find_matching_block(text, m.end(), "endif")
            body = text[m.end() : endif_pos] if endif_pos >= 0 else ""
            # Advance past {% endif %}
            endif_tag_end = endif_pos + len("{% endif %}") if endif_pos >= 0 else m.end()

            if context.get(cond_var):
                out.append(_render_string(body, context))
            pos = endif_tag_end
            continue

        # --- for / endfor ---
        if tag_content.startswith("for "):
            for_parts = tag_content.split()
            if len(for_parts) >= 4 and for_parts[2] == "in":
                item_var = for_parts[1]
                list_var = for_parts[3]
                endfor_pos = _find_matching_block(text, m.end(), "endfor")
                body = text[m.end() : endfor_pos] if endfor_pos >= 0 else ""
                endfor_tag_end = endfor_pos + len("{% endfor %}") if endfor_pos >= 0 else m.end()

                items = context.get(list_var, [])
                for idx, item in enumerate(items):
                    item_ctx = dict(context)
                    item_ctx["loop"] = {"index": idx + 1}
                    if isinstance(item, dict):
                        item_ctx.update(item)
                    else:
                        item_ctx[item_var] = item
                    out.append(_render_string(body, item_ctx))
                pos = endfor_tag_end
                continue

        # Unknown / unhandled tag — emit as-is
        out.append(tag)
        pos = m.end()

    return "".join(out)


def _find_matching_block(text: str, start: int, block_name: str) -> int:
    """Find the next ``{% <block_name> %}`` in *text* starting at *start*.

    Returns the position of the opening ``{%%`` (not past it), or -1.
    Handles simple nesting of if/for blocks to find the correct matching close.
    """
    depth = 0
    openers = {"if", "for"}
    pos = start
    while pos < len(text):
        m = _TAG_RE.search(text, pos)
        if not m:
            return -1
        t = m.group(0)
        if t.startswith("{%"):
            inner = t[2:-2].strip()
            kw = inner.split(maxsplit=1)[0] if inner else ""
            if kw in openers:
                depth += 1
            elif kw == block_name:
                if depth == 0:
                    return m.start()
                depth -= 1
            elif kw in ("endfor", "endif"):
                # A close tag for a nested block — decrement depth
                depth -= 1
        pos = m.end()
    return -1


class SOPRunner:
    """Generates SOP documents (execution handbook, daily tasks, progress report).

    Parameters
    ----------
    brand:
        Brand identifier used in all generated documents.
    artifacts:
        Optional list of decision artifacts that may influence
        recommendations and overrides.
    overrides_dir:
        Directory to scan for ``*.yaml`` override files.  Defaults to
        ``~/.automedia/sop/overrides/``.
    """

    def __init__(
        self,
        brand: str,
        artifacts: list[Any] | None = None,
        overrides_dir: str | Path | None = None,
    ) -> None:
        self._brand = brand
        self._artifacts = artifacts or []
        self._overrides_dir = Path(overrides_dir) if overrides_dir else DEFAULT_OVERRIDES_DIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_execution_handbook(self) -> str:
        """Return the full execution handbook as a Markdown string."""
        overrides = self._load_overrides()
        context: dict[str, Any] = {
            "brand": self._brand,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ab_sample_size": 100,
            "ab_confidence_level": "95%",
            "overrides": overrides or None,
        }
        return _render_template("handbook.md.j2", context)

    def generate_daily_tasks(self, date: str = "") -> str:
        """Return a YAML string with the daily task list for *date*."""
        overrides = self._load_overrides()
        context: dict[str, Any] = {
            "date": date or "YYYY-MM-DD",
            "brand": self._brand,
            "tasks": [
                "Content review",
                "Performance monitoring",
                "Social media scheduling",
            ],
            "overrides": overrides or None,
        }
        return _render_template("daily_task.yaml.j2", context)

    def generate_progress_report(self) -> str:
        """Return a Markdown progress report with KPI metrics and recommendations."""
        overrides = self._load_overrides()
        context: dict[str, Any] = {
            "brand": self._brand,
            "kpis": {
                "content_produced": "N",
                "total_engagement": "N",
                "platform_distribution": "...",
            },
            "top_content": [
                {"title": "Title 1", "metric": "metric"},
                {"title": "Title 2", "metric": "metric"},
                {"title": "Title 3", "metric": "metric"},
            ],
            "recommendations": [
                "Recommendation 1",
                "Recommendation 2",
            ],
            "overrides": overrides or None,
        }
        return _render_template("progress_report.md.j2", context)

    # ------------------------------------------------------------------
    # Overrides mechanism  (W5-T06)
    # ------------------------------------------------------------------

    def _load_overrides(self) -> dict[str, Any]:
        """Scan ``overrides_dir`` for ``*.yaml`` files and merge them.

        Returns a single flat dict.  If a key appears in multiple files
        the last file (sorted alphabetically) wins.
        """
        merged: dict[str, Any] = {}
        if not self._overrides_dir.is_dir():
            return merged

        for yaml_path in sorted(self._overrides_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            except Exception:
                continue  # skip malformed files
            if isinstance(data, dict):
                merged.update(data)
        return merged
