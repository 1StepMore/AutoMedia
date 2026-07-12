"""AutoMedia MCP Server — stdio transport with 22 tools and 5 resources.

Provides an MCP-compliant server exposing AutoMedia pipeline operations
as LLM-callable tools.  All file-system operations are gated behind a
path allowlist loaded from ``mcp_allowlist.yaml``.

.. note::

   **Dual-allowlist architecture:** This module implements the *MCP server*
   allowlist (``mcp_allowlist.yaml`` — ``allowed_directories`` schema).
   There is a separate *Omni adapter* allowlist at ``~/.automedia/omni_allowlist.yaml``
   (``allowed_paths`` / ``write_paths`` schema) consumed by
   :mod:`automedia.omni.allowlist`.  The two serve different layers — MCP
   file-access gating vs. Omni adapter file operations — and should not be
   confused.

Usage::

    # Install with the ``mcp`` extra
    pip install -e ".[mcp]"

    # Run the server (stdio transport)
    python3 -m automedia.mcp.server

    # Or show help
    python3 -m automedia.mcp.server --help
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Shared state imports (from _state.py)
# ---------------------------------------------------------------------------
from automedia.mcp._state import (
    _SERVER_START,
    _lock,
    _pipeline_tracker,
)

# ---------------------------------------------------------------------------
# Tool handler imports (from tools.py)
# ---------------------------------------------------------------------------
from automedia.mcp.accounts import (
    connect_account,
    disconnect_account,
    get_account_health,
    list_accounts,
)

# ---------------------------------------------------------------------------
# Allowlist imports (from allowlist.py)
# ---------------------------------------------------------------------------
from automedia.mcp.allowlist import (
    _ALLOWED_OUTPUT_FORMATS,
    _ALLOWLIST_FILE,
    _cached_allowlist,
    _load_allowlist,
    _require_allowed,
    _reset_allowlist_cache,
    check_path_allowed,
)

# ---------------------------------------------------------------------------
# Resource imports (from resources.py)
# ---------------------------------------------------------------------------
from automedia.mcp.resources import (
    gate_info_resource,
    list_projects_resource,
    pipeline_metrics_resource,
    pipeline_status_resource,
    topic_pool_resource,
)

# ---------------------------------------------------------------------------
# Helper / utility imports (from tools.py)
# ---------------------------------------------------------------------------
from automedia.mcp.tools import (
    _discover_projects,
    _pipeline_result_to_dict,
    _project_assets,
    _resolve_projects_dir,
    archive_project,
    evaluate_content_quality,
    extract_brief,
    format_output,
    get_pipeline_progress,
    get_pipeline_status,
    get_project_assets,
    health_check,
    list_projects,
    list_topic_pool,
    localize_content,
    localize_output,
    register_platform_adapter,
    research_topics,
    run_brand_strategy,
    run_pipeline,
    run_pipeline_from_strategy,
    select_topic,
)

# ---------------------------------------------------------------------------
# Public API — backward-compatible re-exports
# ---------------------------------------------------------------------------
__all__ = [
    # Server factory
    "create_server",
    "main",
    # Tool handlers
    "evaluate_content_quality",
    "research_topics",
    "run_brand_strategy",
    "run_pipeline_from_strategy",
    "select_topic",
    "run_pipeline",
    "get_pipeline_progress",
    "get_pipeline_status",
    "list_projects",
    "get_project_assets",
    "archive_project",
    "list_topic_pool",
    "register_platform_adapter",
    "extract_brief",
    "localize_content",
    "localize_output",
    "format_output",
    "health_check",
    # Account tools
    "connect_account",
    "list_accounts",
    "get_account_health",
    "disconnect_account",
    # Allowlist helpers
    "check_path_allowed",
    "_require_allowed",
    "_load_allowlist",
    "_reset_allowlist_cache",
    "_ALLOWED_OUTPUT_FORMATS",
    "_ALLOWLIST_FILE",
    "_cached_allowlist",
    # Helper utilities
    "_resolve_projects_dir",
    "_discover_projects",
    "_project_assets",
    "_pipeline_result_to_dict",
    # Shared state
    "_pipeline_tracker",
    "_lock",
    "_SERVER_START",
]


# ---------------------------------------------------------------------------
# MCP Server construction
# ---------------------------------------------------------------------------


def create_server() -> Any:  # noqa: ANN401 — FastMCP type
    """Create and configure the FastMCP server instance.

    Returns
    -------
    FastMCP
        A fully configured server with all 22 tools and 5 resources registered.
    """
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="AutoMedia",
        instructions=(
            "AutoMedia — Automated Media Production Pipeline\n"
            "================================================\n"
            "\n"
            "22 MCP tools for topic selection, pipeline execution, project\n"
            "management, Omni Triad document processing, brand strategy,\n"
            "content quality evaluation, and server health.\n"
            "\n"
            "━━━ CORE WORKFLOW (5 tools) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "Standard production pipeline (execute in order):\n"
            "\n"
            "  Step 1  select_topic(category?, tenant_id?)\n"
            "          Pick the highest-scored pending topic from the pool.\n"
            "          Returns {selected, remaining_count}. If null, add topics first.\n"
            "\n"
            "  Step 2  run_pipeline(topic, brand, mode?, resume_from?)\n"
            "          Launch the full production pipeline in a background thread.\n"
            "          Returns {project_id, status: 'started'} immediately.\n"
            "          Use the project_id to poll progress.\n"
            "\n"
            "  Step 3  get_pipeline_progress(project_id)\n"
            "          Poll gate-by-gate progress. Returns {current_gate, events[], error}.\n"
            "          Events include 'start', 'passed', 'failed' per gate.\n"
            "          Keep polling until all gates finish or an error appears.\n"
            "\n"
            "  Step 4  get_pipeline_status(project_id, base_dir?)\n"
            "          After completion, inspect the project's metadata and subdirectories.\n"
            "\n"
            "  Step 5  get_project_assets(project_dir)\n"
            "          List all generated files (MP4, SRT, cover images, drafts, etc.).\n"
            "\n"
            "  Step 6  list_projects(base_dir?, status?)\n"
            "          Browse all projects, optionally filtered by status.\n"
            "\n"
            "  Step 7  archive_project(project_id, base_dir?, force?)\n"
            "          Archive a completed project. SEE RED LINE 8 BELOW.\n"
            "\n"
            "━━━ PIPELINE MODES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "  auto        Full pipeline: copy gates (G0-G5) + video gates (V0-V7)\n"
            "              + lifecycle gates (L1-L4).\n"
            "              Use for complete end-to-end production.\n"
            "\n"
            "  text_only   Copy gates only (G0-G5 + L1-L4). Skips video/audio.\n"
            "              Use when you only need a written article or social post.\n"
            "\n"
            "  video_only  Video gates only (V0-V7 + L1-L4). Assumes text already exists.\n"
            "              Use when the draft is ready and you only need video output.\n"
            "\n"
            "  qa_only     Quality-assurance pass — runs selected QA gates on existing\n"
            "              content without generating new assets. Use for re-validation.\n"
            "\n"
            "━━━ STRATEGY & CONTENT QUALITY (4 tools) ━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "  run_brand_strategy(brand_name, industry, target_audience, context?)\n"
            "      Generate a brand strategy using LLM-driven analysis.\n"
            "      Returns {brand_positioning, audience_analysis,\n"
            "      competitive_landscape, key_differentiators, suggested_messaging}.\n"
            "\n"
            "  run_pipeline_from_strategy(topic, brand, mode?, strategy_context?)\n"
            "      Generate a content strategy via LLM then execute the pipeline.\n"
            "      Returns {strategy: {...}, pipeline_result: {...}}.\n"
            "\n"
            "  research_topics(category, count?, trending?)\n"
            "      Research trending/high-potential topics using LLM.\n"
            "      Returns structured list with angles, confidence scores, and\n"
            "      format recommendations.\n"
            "\n"
            "  evaluate_content_quality(content, criteria?, brand?)\n"
            "      Score content against specified criteria using LLM evaluation.\n"
            "      Returns {quality_score, issues[], suggestions[], overall_assessment}.\n"
            "\n"
            "━━━ OMNI TRIAD TOOLS (4 tools) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "Document processing pipeline (extract → translate → convert):\n"
            "\n"
            "  extract_brief(file_path, source_lang?, target_lang?)\n"
            "      Extract structured markdown + manifest JSON from a document (PDF, DOCX…).\n"
            "      Returns {md_content, manifest_json, warnings}.\n"
            "\n"
            "  localize_content(md_content, source_lang, target_lang)\n"
            "      Translate markdown text via OL shield → LLM → repair → unshield pipeline.\n"
            "      Returns {translated_md, xliff_path?, warnings}.\n"
            "\n"
            "  localize_output(project_dir, target_langs)\n"
            "      Batch-translate all drafts in a project into multiple languages.\n"
            "      target_langs is comma-separated (e.g. 'en,ja,ko').\n"
            "      Reads from 01_content/drafts/, writes to 05_publish/{lang}/.\n"
            "\n"
            "  format_output(content, target_format)\n"
            "      Convert markdown to another format. Supported: html, pdf, docx, md.\n"
            "      Returns {output_path, output_format, warnings}.\n"
            "\n"
            "━━━ TOPIC POOL (2 tools) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "  list_topic_pool(status?, category?, pool_db_path?)\n"
            "      List topics with optional filters. Use to browse available topics\n"
            "      before calling select_topic.\n"
            "\n"
            "  register_platform_adapter(platform_name, adapter_class?)\n"
            "      Register a publish adapter. STUB — returns instructions for future use.\n"
            "\n"
            "━━━ SERVER (1 tool) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "  health_check()\n"
            "      Returns {status, version, uptime_s, tools_count}. No parameters.\n"
            "\n"
            "━━━ ACCOUNT TOOLS (4 tools) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "  connect_account(platform, auth_type?, credentials?, label?)\n"
            "      Register a new platform account for publishing.\n"
            "      Returns {account_id, platform, status}.\n"
            "\n"
            "  list_accounts(platform?, status?)\n"
            "      List all registered accounts with optional filters.\n"
            "      Returns {accounts[], count}.\n"
            "\n"
            "  get_account_health(account_id)\n"
            "      Check an account's session health.\n"
            "      Returns {account_id, platform, status, last_health_check}.\n"
            "\n"
            "  disconnect_account(account_id)\n"
            "      Remove a platform account.\n"
            "      Returns {success, account_id, platform}.\n"
            "\n"
            "━━━ ERROR HANDLING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "All tools return JSON dicts. On error the dict contains an 'error' key:\n"
            "  {\"error\": \"description of what went wrong\"}\n"
            "\n"
            "Common error patterns:\n"
            "  - 'path not allowed' — file outside the allowlist. Configure\n"
            "    allowed_directories in mcp_allowlist.yaml.\n"
            "  - 'No pending topics found' — topic pool is empty. Add topics first.\n"
            "  - 'No active pipeline found' — invalid project_id or pipeline finished.\n"
            "  - Gate failures show the gate name (G0, V3, etc.) and failure details.\n"
            "    See the gate info resource: automedia://gate/{gate_name}/info\n"
            "\n"
            "━━━ RED LINES (MUST OBEY) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "Red Line 8 — Archive Protection:\n"
            "  archive_project refuses unless project status is 'published' OR force=True.\n"
            "  Agents MUST NOT set force=True without explicit user instruction.\n"
            "  Only the user may force-archive a non-published project.\n"
            "\n"
            "Path Allowlist:\n"
            "  All file-path tool parameters are checked against mcp_allowlist.yaml.\n"
            "  Empty allowed_directories = deny all paths. Modify the YAML to permit\n"
            "  access to your project directories. Do NOT modify without user request.\n"
            "\n"
            "━━━ HITL (HUMAN-IN-THE-LOOP) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "Certain gates may pause for human review (HITL). When a gate enters\n"
            "HITL state, the pipeline waits for human approval via the CLI:\n"
            "  automedia hitl approve <project_id> <gate_name>\n"
            "  automedia hitl reject <project_id> <gate_name>\n"
            "\n"
            "If get_pipeline_progress shows a gate in 'awaiting_hitl' status,\n"
            "notify the user that human review is needed before proceeding.\n"
            "\n"
            "━━━ EXAMPLE MULTI-STEP WORKFLOWS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n"
            "Workflow A — Full production from topic pool:\n"
            "  1. select_topic(category='tech')        → get topic\n"
            "  2. run_pipeline(topic, brand, 'auto')    → get project_id\n"
            "  3. get_pipeline_progress(project_id)     → poll until done\n"
            "  4. get_project_assets(project_dir)       → list outputs\n"
            "  5. archive_project(project_id)           → clean up\n"
            "\n"
            "Workflow B — Text-only article:\n"
            "  1. run_pipeline('AI trends', 'my-brand', 'text_only')\n"
            "  2. get_pipeline_progress(project_id) until all gates pass\n"
            "  3. get_project_assets(project_dir) to get the draft\n"
            "\n"
            "Workflow C — Extract and translate a document:\n"
            "  1. extract_brief('/path/to/source.pdf')   → get md_content\n"
            "  2. localize_content(md_content, 'zh', 'en') → translate\n"
            "  3. format_output(translated_md, 'html')    → convert to HTML\n"
            "\n"
            "Workflow D — Multi-language localization:\n"
            "  1. localize_output(project_dir, 'en,ja,ko')\n"
            "     → translates all drafts into 3 languages at once\n"
        ),
    )

    # Register all tools
    mcp.tool(
        description=(
            "Return server health status — version, uptime in seconds, "
            "and the number of registered tools."
        ),
    )(health_check)

    mcp.tool(
        description=(
            "Select the highest-scored pending topic from the pool. "
            "Returns the selected topic and remaining count."
        ),
    )(select_topic)

    mcp.tool(
        description=(
            "Research trending or high-potential topics within a category using LLM. "
            "Takes a category name, optional count (default 5), and optional trending "
            "data. Returns a structured list of topics with angles, confidence scores, "
            "and format recommendations. The result is ready to feed into the topic pool."
        ),
    )(research_topics)

    mcp.tool(
        description=(
            "Execute the full AutoMedia production pipeline. Returns PipelineResult as JSON."
        ),
    )(run_pipeline)

    mcp.tool(
        description=(
            "Get the current progress of a running pipeline by project_id. "
            "Returns the current gate, all gate progress events (start / "
            "passed / failed), and any errors captured from the background "
            "thread. Poll this after run_pipeline to observe execution."
        ),
    )(get_pipeline_progress)

    mcp.tool(
        description=("Return the current status / progress of a pipeline run by project ID."),
    )(get_pipeline_status)

    mcp.tool(
        description=(
            "List all projects found under a base directory, optionally filtered by status."
        ),
    )(list_projects)

    mcp.tool(
        description=("Return the list of asset files inside a project directory."),
    )(get_project_assets)

    mcp.tool(
        description=(
            "Archive a project. Red Line 8: refuses unless status is 'published' or force=True."
        ),
    )(archive_project)

    mcp.tool(
        description=("List topics in the pool, optionally filtered by status or category."),
    )(list_topic_pool)

    mcp.tool(
        description=(
            "Register a platform adapter (stub). Provide platform_name "
            "and optional adapter_class dotted path."
        ),
    )(register_platform_adapter)

    # ------------------------------------------------------------------
    # Omni tools
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Extract a content brief from a document file using OPP. "
            "Processes the document through OPPAdapter.extract() and "
            "returns structured markdown content, a manifest JSON with "
            "segment metadata, and any warnings encountered."
        ),
    )(extract_brief)

    mcp.tool(
        description=(
            "Translate markdown content from source to target language. "
            "Delegates to OLAdapter.translate() which uses the OL shield "
            "→ LLM-translate → repair → unshield pipeline. Returns the "
            "translated markdown, optional XLIFF path, and warnings."
        ),
    )(localize_content)

    mcp.tool(
        description=(
            "Convert content to the specified output format. "
            "Delegates to ORFAdapter.convert() to transform content "
            "into the requested format. Returns the output path, "
            "format identifier, and any warnings or errors."
        ),
    )(format_output)

    mcp.tool(
        description=(
            "Translate all project drafts into multiple target languages. "
            "Reads markdown from 01_content/drafts/, translates via OLAdapter, "
            "writes translated files to 05_publish/{lang}/. "
            "Returns a mapping of language code to list of output file paths."
        ),
    )(localize_output)

    # ------------------------------------------------------------------
    # Content quality evaluation tool
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Evaluate content quality using an LLM. Scores content against "
            "specified criteria (clarity, accuracy, brand voice, etc.) and "
            "returns a quality score (0.0-1.0), issues with severity prefixes, "
            "concrete suggestions, and an overall assessment with verdict."
        ),
    )(evaluate_content_quality)

    # ------------------------------------------------------------------
    # Strategy tools
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Generate a brand strategy using LLM-driven analysis. "
            "Takes brand_name, industry, target_audience, and optional context. "
            "Returns a structured strategy with brand positioning, audience "
            "analysis, competitive landscape, key differentiators, and "
            "suggested messaging."
        ),
    )(run_brand_strategy)

    mcp.tool(
        description=(
            "Generate a content strategy via LLM then execute the AutoMedia "
            "production pipeline. Takes topic, brand, optional mode, and "
            "optional strategy_context. Returns both the strategy output and "
            "the pipeline result."
        ),
    )(run_pipeline_from_strategy)

    # ------------------------------------------------------------------
    # Account tools
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Register a new platform account for publishing. "
            "Returns the account_id and metadata."
        ),
    )(connect_account)

    mcp.tool(
        description=(
            "List all registered accounts with optional platform/status filters. "
            "Returns account metadata."
        ),
    )(list_accounts)

    mcp.tool(
        description=(
            "Check an account's health status. "
            "Returns status, platform, and last health check time."
        ),
    )(get_account_health)

    mcp.tool(
        description=(
            "Disconnect/remove a platform account. Requires account_id."
        ),
    )(disconnect_account)

    # ------------------------------------------------------------------
    # MCP resources
    # ------------------------------------------------------------------

    @mcp.resource("automedia://projects")
    def _projects_resource() -> str:
        """List all projects as a JSON array of summaries."""
        return list_projects_resource()

    @mcp.resource("automedia://pipeline/{project_id}")
    def _pipeline_status(project_id: str) -> str:
        """Get pipeline status for a specific project by ID."""
        return pipeline_status_resource(project_id)

    @mcp.resource("automedia://pool")
    def _pool_resource() -> str:
        """List all topics in the pool as a JSON array."""
        return topic_pool_resource()

    @mcp.resource("automedia://pipeline/{project_id}/metrics")
    def _pipeline_metrics(project_id: str) -> str:
        """Get live pipeline metrics (gate timing, status) for a project."""
        return pipeline_metrics_resource(project_id)

    @mcp.resource("automedia://gate/{gate_name}/info")
    def _gate_info(gate_name: str) -> str:
        """Get gate description, failure mode, common causes, and fixes."""
        return gate_info_resource(gate_name)

    return mcp


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the AutoMedia MCP server (stdio transport)."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python3 -m automedia.mcp.server",
        description="AutoMedia MCP Server — stdio transport with 22 tools and 5 resources.",
    )
    parser.add_argument(
        "--show-tools",
        action="store_true",
        help="List registered tool names and exit.",
    )
    args = parser.parse_args()

    server = create_server()

    if args.show_tools:
        # FastMCP stores tools internally; print names for quick inspection
        print("Registered MCP tools:")
        for name in sorted(server._tool_manager._tools.keys()):
            print(f"  - {name}")
        print("\nRegistered MCP resources:")
        for uri in sorted(server._resource_manager._resources.keys()):
            print(f"  - {uri}")
        for uri in sorted(server._resource_manager._templates.keys()):
            print(f"  - {uri}  (template)")
        return

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
