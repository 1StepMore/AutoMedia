"""``automedia effects`` — content analytics commands.

Usage::

    automedia effects <project_id> [--output json|table] [--brand <name>]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from automedia.cli.output import OutputMode, get_output_mode, output_error

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_project_by_id(project_id: str, base_dir: str) -> dict[str, Any] | None:
    """Scan *base_dir* for a project matching *project_id*."""
    base = Path(base_dir)
    for info_file in sorted(base.glob("*/00_project_info.json")):
        try:
            data = json.loads(info_file.read_text(encoding="utf-8"))
            if data.get("project_id") == project_id:
                data["_dir"] = str(info_file.parent)
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _read_project_content(project_dir: str) -> str:
    """Read all markdown drafts from a project directory."""
    root = Path(project_dir)
    drafts_dir = root / "01_content" / "drafts"

    if not drafts_dir.is_dir():
        return ""

    parts: list[str] = []
    for md_file in sorted(drafts_dir.glob("*.md")):
        try:
            parts.append(md_file.read_text(encoding="utf-8"))
        except OSError:
            continue

    return "\n\n".join(parts)


def _compute_all_stats(text: str, brand: str = "") -> dict[str, Any]:
    """Compute all analytics stats for *text*."""
    from automedia.effects.stats import (
        brand_mention_frequency,
        readability_index,
        sentiment_score,
        word_count,
    )

    wc = word_count(text)
    ss = sentiment_score(text)
    ri = readability_index(text)
    bmf: dict[str, Any] = {"mentions": {}, "total_mentions": 0}
    if brand:
        bmf = brand_mention_frequency(text, [brand])

    return {
        "word_count": wc,
        "sentiment": ss,
        "readability": ri,
        "brand_mentions": bmf,
    }


def _empty_stats() -> dict[str, Any]:
    """Return an empty stats skeleton."""
    return {
        "word_count": {
            "word_count": 0, "char_count": 0, "char_count_no_spaces": 0,
            "sentence_count": 0, "avg_words_per_sentence": 0.0,
        },
        "sentiment": {
            "score": 0.0, "label": "neutral",
            "positive_words": 0, "negative_words": 0, "total_scored": 0,
        },
        "readability": {
            "flesch_reading_ease": 0.0, "grade_level": "N/A",
            "avg_syllables_per_word": 0.0, "avg_words_per_sentence": 0.0,
        },
        "brand_mentions": {"mentions": {}, "total_mentions": 0},
    }


# ---------------------------------------------------------------------------
# effects command (registered via LazyTyperGroup.register_fn)
# ---------------------------------------------------------------------------


def effects_cmd(
    project_id: str = typer.Argument(..., help="Project ID to analyse."),
    base_dir: str = typer.Option(
        ".",
        "--base-dir", "-d",
        help="Base directory to scan for projects.",
    ),
    brand: str = typer.Option(
        "",
        "--brand", "-b",
        help="Brand name for mention tracking.",
    ),
    output: str = typer.Option(
        "table",
        "--output", "-o",
        help="Output format: json or table.",
    ),
) -> None:
    """Compute content analytics for a project.

    Scans the project's ``01_content/drafts/`` for markdown files and
    computes word count, sentiment, readability, and brand mentions.
    """
    mode = get_output_mode()
    is_json = mode == OutputMode.JSON or output == "json"

    project = _find_project_by_id(project_id, base_dir=base_dir)
    if project is None:
        output_error(f"Project not found: {project_id}")
        return  # unreachable — output_error raises typer.Exit

    content = _read_project_content(project["_dir"])
    brand_name = brand or project.get("brand", "")

    if not content:
        stats = _empty_stats()
    else:
        stats = _compute_all_stats(content, brand_name)

    result: dict[str, Any] = {
        "status": "ok",
        "project_id": project_id,
        "topic": project.get("topic", ""),
        "brand": brand_name,
        "stats": stats,
    }

    if is_json:
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Table output
    typer.echo(f"Project: {project_id}")
    typer.echo(f"Topic:   {project.get('topic', 'N/A')}")
    typer.echo(f"Brand:   {brand_name or 'N/A'}")
    typer.echo()

    wc = stats["word_count"]
    typer.echo("--- Word Count ---")
    typer.echo(f"  Words:                {wc['word_count']}")
    typer.echo(f"  Characters:           {wc['char_count']}")
    typer.echo(f"  Characters (no WS):   {wc['char_count_no_spaces']}")
    typer.echo(f"  Sentences:            {wc['sentence_count']}")
    typer.echo(f"  Avg words/sentence:   {wc['avg_words_per_sentence']}")
    typer.echo()

    ss = stats["sentiment"]
    typer.echo("--- Sentiment ---")
    typer.echo(f"  Score:  {ss['score']}  ({ss['label']})")
    typer.echo(f"  Positive words:  {ss['positive_words']}")
    typer.echo(f"  Negative words:  {ss['negative_words']}")
    typer.echo()

    ri = stats["readability"]
    typer.echo("--- Readability ---")
    typer.echo(f"  Flesch Reading Ease:  {ri['flesch_reading_ease']}")
    typer.echo(f"  Grade level:          {ri['grade_level']}")
    typer.echo()

    bmf = stats["brand_mentions"]
    typer.echo("--- Brand Mentions ---")
    if bmf["total_mentions"] > 0:
        for name, count in bmf["mentions"].items():
            typer.echo(f"  {name}: {count}")
    else:
        typer.echo("  (none)")
