"""MCP server instructions — dynamically generated from ``_tool_registry``."""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Category definitions for dynamic instruction generation
# ---------------------------------------------------------------------------
# Each entry: (category_title, [tool_names])
# Tools are listed under the first category that contains their name.
_TOOL_CATEGORIES: list[tuple[str, list[str]]] = [
    (
        "Core Workflow",
        [
            "select_topic",
            "run_pipeline",
            "get_pipeline_progress",
            "get_pipeline_status",
            "get_project_assets",
            "list_projects",
            "archive_project",
            "cancel_pipeline",
            "pause_pipeline",
            "resume_pipeline",
            "retry_gate",
            "skip_gate",
        ],
    ),
    (
        "Brand Strategy & Content Quality",
        [
            "run_brand_strategy",
            "run_pipeline_from_strategy",
            "research_topics",
            "evaluate_content_quality",
        ],
    ),
    (
        "Omni Triad (Document Processing)",
        [
            "extract_brief",
            "localize_content",
            "localize_output",
            "format_output",
        ],
    ),
    (
        "Topic Pool",
        [
            "list_topic_pool",
            "add_pool_topic",
            "pool_add_topic",
        ],
    ),
    (
        "Server / Engine",
        [
            "health_check",
            "health_engine",
            "engine_health",
            "update_engine_config",
        ],
    ),
    (
        "Cron / Schedule",
        [
            "add_cron_schedule",
            "list_cron_schedules",
            "remove_cron_schedule",
            "get_cron_health",
            "test_cron_schedule",
        ],
    ),
    (
        "Account Management",
        [
            "connect_account",
            "list_accounts",
            "get_account_health",
            "disconnect_account",
        ],
    ),
    (
        "Publishing",
        [
            "publish_content",
            "list_platforms",
            "register_platform_adapter",
        ],
    ),
    (
        "HITL / Director Mode",
        [
            "approve_gate",
            "reject_gate",
            "get_pending_approvals",
        ],
    ),
    (
        "Batch Operations",
        [
            "run_batch",
            "batch_run",
        ],
    ),
    (
        "Assets / Search",
        [
            "search_assets",
        ],
    ),
    (
        "Configuration",
        [
            "list_brands",
            "get_config",
            "get_redlines",
            "list_overridable_templates",
            "list_workflows",
        ],
    ),
    (
        "Help / Introspection",
        [
            "help_mcp",
            "mcp_help",
        ],
    ),
]


def generate_instructions(tool_registry: dict[str, dict[str, Any]]) -> str:
    """Generate MCP instructions dynamically from the tool registry.

    Args:
        tool_registry: Dict mapping tool names to tool metadata dicts.
            Each entry has at least ``name``, ``description``, and ``parameters``.

    Returns:
        str: Formatted instructions listing all available tools with descriptions,
            plus error handling guidance, red lines, HITL info, and example workflows.
    """
    lines: list[str] = [
        "AutoMedia — Automated Media Production Pipeline",
        "================================================",
        "",
        f"{len(tool_registry)} MCP tools for topic selection, pipeline execution, "
        "project management, Omni Triad document processing, brand strategy, "
        "cron schedule management, content quality evaluation, "
        "override management, and server health.",
        "",
    ]

    listed: set[str] = set()

    for cat_name, tool_names in _TOOL_CATEGORIES:
        available = [n for n in tool_names if n in tool_registry and n not in listed]
        if not available:
            continue

        label = f"━━━ {cat_name.upper()} ({len(available)} tool{'s' if len(available) != 1 else ''}) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        header_fill = 70 - len(label)
        if header_fill < 3:
            header_fill = 3
        lines.append(f"{label}{'━' * header_fill}")
        lines.append("")

        for name in available:
            info = tool_registry[name]
            desc = info.get("description", "").split("\n")[0].strip()
            if desc and desc[-1] not in (".", "!", "?"):
                desc += "."
            lines.append(f"  {name}()")
            lines.append(f"      {desc}")
            lines.append("")

        listed.update(available)

    remaining = [n for n in tool_registry if n not in listed]
    if remaining:
        label = f"━━━ OTHER TOOLS ({len(remaining)}) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        header_fill = 70 - len(label)
        if header_fill < 3:
            header_fill = 3
        lines.append(f"{label}{'━' * header_fill}")
        lines.append("")
        for name in sorted(remaining):
            info = tool_registry[name]
            desc = info.get("description", "").split("\n")[0].strip()
            if desc and desc[-1] not in (".", "!", "?"):
                desc += "."
            lines.append(f"  {name}()")
            lines.append(f"      {desc}")
            lines.append("")

    lines.extend([
        "━━━ ERROR HANDLING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "All tools return JSON dicts. On error the dict contains an 'error' key:",
        '  {"error": "description of what went wrong"}',
        "",
        "Common error patterns:",
        "  - 'path not allowed' — file outside the allowlist. Configure",
        "    allowed_directories in mcp_allowlist.yaml.",
        "  - 'No pending topics found' — topic pool is empty. Add topics first.",
        "  - 'No active pipeline found' — invalid project_id or pipeline finished.",
        "  - Gate failures show the gate name (G0, V3, etc.) and failure details.",
        "    See the gate info resource: automedia://gate/{gate_name}/info",
        "",
        "━━━ RED LINES (MUST OBEY) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "Red Line 8 — Archive Protection:",
        "  archive_project refuses unless project status is 'published' OR force=True.",
        "  Agents MUST NOT set force=True without explicit user instruction.",
        "  Only the user may force-archive a non-published project.",
        "",
        "Path Allowlist:",
        "  All file-path tool parameters are checked against mcp_allowlist.yaml.",
        "  Empty allowed_directories = deny all paths. Modify the YAML to permit",
        "  access to your project directories. Do NOT modify without user request.",
        "",
        "━━━ HITL & DIRECTOR MODE APPROVAL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "Certain gates may pause for human review (HITL). When a gate enters",
        "HITL state, the pipeline waits for human approval via the CLI:",
        '  automedia hitl approve <project_id> <gate_name>',
        '  automedia hitl reject <project_id> <gate_name>',
        "",
        "When director mode is enabled (pause_on_approval=True), gates with",
        "requires_approval in their context pause for MCP-level approval:",
        "  get_pending_approvals(project_id?)  → list waiting gates",
        "  approve_gate(project_id, gate_name)   → approve and resume",
        "  reject_gate(project_id, gate_name)    → reject and resume",
        "",
        "Use get_pipeline_progress to detect paused gates (status:",
        "'awaiting_hitl' with detail 'awaiting_approval'), then call",
        "approve_gate or reject_gate to continue pipeline execution.",
        "",
        "━━━ EXAMPLE MULTI-STEP WORKFLOWS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "Workflow A — Full production from topic pool:",
        "  1. select_topic(category='tech')        → get topic",
        "  2. run_pipeline(topic, brand, 'auto')    → get project_id",
        "  3. get_pipeline_progress(project_id)     → poll until done",
        "  4. get_project_assets(project_dir)       → list outputs",
        "  5. archive_project(project_id)           → clean up",
        "",
        "Workflow B — Text-only article:",
        "  1. run_pipeline('AI trends', 'my-brand', 'text_only')",
        "  2. get_pipeline_progress(project_id) until all gates pass",
        "  3. get_project_assets(project_dir) to get the draft",
        "",
        "Workflow C — Extract and translate a document:",
        "  1. extract_brief('/path/to/source.pdf')   → get md_content",
        "  2. localize_content(md_content, 'zh', 'en') → translate",
        "  3. format_output(translated_md, 'html')    → convert to HTML",
        "",
        "Workflow D — Multi-language localization:",
        "  1. localize_output(project_dir, 'en,ja,ko')",
        "     → translates all drafts into 3 languages at once",
    ])

    return "\n".join(lines) + "\n"
