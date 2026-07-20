"""AutoMedia MCP Server — stdio transport with 51 tools and 6 resources.

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

import warnings
from typing import TYPE_CHECKING, Any

from structlog import get_logger

from automedia._version import __version__ as _automedia_version

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

log = get_logger(__name__)

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
    _require_allowed,
)

# ---------------------------------------------------------------------------
# Resource imports (from resources.py)
# ---------------------------------------------------------------------------
from automedia.mcp.resources import (
    gate_info_resource,
    getting_started_resource,
    list_projects_resource,
    pipeline_metrics_resource,
    pipeline_status_resource,
    topic_pool_resource,
)

# ---------------------------------------------------------------------------
# Helper / utility imports (from tools.py)
# ---------------------------------------------------------------------------
from automedia.mcp.tools import (
    add_brand,
    add_cron_schedule,
    approve_gate,
    archive_project,
    batch_run,
    cancel_pipeline,
    configure_llm,
    engine_health,
    evaluate_content_quality,
    extract_brief,
    format_output,
    get_config,
    get_cron_health,
    get_pending_approvals,
    get_pipeline_progress,
    get_pipeline_status,
    get_project_assets,
    get_redlines,
    health_check,
    init_config,
    list_active_pipelines,
    list_brands,
    list_cron_schedules,
    list_overridable_templates,
    list_platforms,
    list_projects,
    list_topic_pool,
    list_workflows,
    localize_content,
    localize_output,
    onboard,
    pause_pipeline,
    pool_add_topic,
    publish_content,
    register_platform_adapter,
    reject_gate,
    remove_cron_schedule,
    research_topics,
    resume_pipeline,
    retry_gate,
    run_brand_strategy,
    run_pipeline,
    run_pipeline_from_strategy,
    search_assets,
    select_topic,
    skip_gate,
    test_cron_schedule,
    update_engine_config,
)

from automedia.effects.mcp import analyze_content as effects_analyze_content
from automedia.mcp.tools_distribution import distribute_content

# ---------------------------------------------------------------------------
# Public API — backward-compatible re-exports
# ---------------------------------------------------------------------------
__all__ = [
    # Server factory
    "create_server",
    "main",
    # Tool handlers
    "add_brand",
    "batch_run",
    "run_batch",
    "configure_llm",
    "evaluate_content_quality",
    "research_topics",
    "run_brand_strategy",
    "run_pipeline_from_strategy",
    "select_topic",
    "run_pipeline",
    "get_pipeline_progress",
    "get_pipeline_status",
    "init_config",
    "list_active_pipelines",
    "list_projects",
    "get_project_assets",
    "archive_project",
    "list_topic_pool",
    "pool_add_topic",
    "add_pool_topic",
    "publish_content",
    "register_platform_adapter",
    "extract_brief",
    "localize_content",
    "localize_output",
    "format_output",
    "get_config",
    "get_redlines",
    "health_check",
    "list_brands",
    # Asset library tools
    "search_assets",
    # Cron schedule tools
    "add_cron_schedule",
    "list_cron_schedules",
    "list_overridable_templates",
    "list_platforms",
    "list_workflows",
    "remove_cron_schedule",
    "test_cron_schedule",
    # Engine health tool
    "engine_health",
    "health_engine",
    # Account tools
    "connect_account",
    "list_accounts",
    "get_account_health",
    "disconnect_account",
    # Pipeline control tools
    "cancel_pipeline",
    "pause_pipeline",
    "resume_pipeline",
    "retry_gate",
    "skip_gate",
    # Approval / rejection tools (director mode)
    "approve_gate",
    "reject_gate",
    "get_pending_approvals",
    # Allowlist helpers
    "_require_allowed",
    "mcp_help",
    "help_mcp",
    # Onboarding
    "onboard",
    # Distribution
    "distribute_content",
    # Effects
    "effects_analyze_content",
]


# ---------------------------------------------------------------------------
# Tool registry cache for mcp_help — populated at registration time
# ---------------------------------------------------------------------------

_tool_registry: dict[str, dict[str, Any]] = {}

# Prefix → category mapping for dynamic tool grouping.
# The first matching prefix determines the category; unmatched tools fall
# to "Other".  Ordered with more-specific prefixes first where needed.
_CATEGORY_PREFIXES: list[tuple[str, str]] = [
    ("disconnect_", "Account Management"),
    ("connect_", "Account Management"),
    ("get_", "Get / Query"),
    ("list_", "List / Browse"),
    ("run_", "Run / Execute"),
    ("add_", "Add / Create"),
    ("remove_", "Remove / Delete"),
    ("test_", "Test / Validate"),
    ("pool_", "Topic Pool"),
    ("search_", "Search"),
    ("publish_", "Publishing"),
    ("distribute_", "Publishing"),
    ("select_", "Topic Selection"),
    ("register_", "Registration"),
    ("extract_", "Document Processing"),
    ("localize_", "Document Processing"),
    ("format_", "Document Processing"),
    ("evaluate_", "Content Quality"),
    ("analyze_", "Content Quality"),
    ("batch_", "Batch Operations"),
    ("health_", "Server / Engine"),
    ("help_", "Help / Introspection"),
    ("engine_", "Server / Engine"),
    ("research_", "Research"),
    ("archive_", "Archive"),
    ("init_", "Setup / Configuration"),
    ("onboard", "Setup / Configuration"),
    ("configure_", "Setup / Configuration"),
    ("update_", "Update"),
    ("approve_", "Approval"),
    ("reject_", "Approval"),
]


def _categorize_tool(name: str) -> str:
    """Determine the display category for a tool based on its name prefix."""
    for prefix, category in _CATEGORY_PREFIXES:
        if name.startswith(prefix):
            return category
    return "Other"


def help_mcp() -> dict[str, Any]:
    """Get a categorized listing of all available MCP tools with descriptions.

    Use this to discover what tools are available at runtime — the output is
    dynamically generated from the registered tool set rather than hardcoded.

    Returns
    -------
    dict
        ``{"categories": {...}, "tool_count": int, "hint": str}``
        where *categories* maps category name → list of ``{name, description}``
        objects sorted alphabetically within each group.
    """
    categorized: dict[str, list[dict[str, Any]]] = {}
    for name, info in _tool_registry.items():
        category = _categorize_tool(name)
        categorized.setdefault(category, []).append(
            {
                "name": name,
                "description": info["description"],
                "parameters": info.get("parameters"),
            }
        )

    sorted_categories: dict[str, list[dict[str, str]]] = {}
    for cat in sorted(categorized):
        sorted_categories[cat] = sorted(categorized[cat], key=lambda t: t["name"])

    return {
        "categories": sorted_categories,
        "tool_count": len(_tool_registry),
        "hint": (
            "Call a tool by name from the categories above. "
            "Use get_pipeline_progress to poll async tasks."
        ),
    }


def mcp_help() -> dict[str, Any]:
    """⚠️ DEPRECATED: Use :func:`help_mcp` instead.

    Get a categorized listing of all available MCP tools with descriptions.

    Use this to discover what tools are available at runtime — the output is
    dynamically generated from the registered tool set rather than hardcoded.

    Returns
    -------
    dict
        ``{"categories": {...}, "tool_count": int, "hint": str}``
        where *categories* maps category name → list of ``{name, description}``
        objects sorted alphabetically within each group.
    """
    warnings.warn(
        "mcp_help is deprecated, use help_mcp instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return help_mcp()


# ---------------------------------------------------------------------------
# Wrapper functions for renamed tools (backward-compatible aliases kept)
# ---------------------------------------------------------------------------


def add_pool_topic(
    title: str,
    category: str = "",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """Add a topic to the topic pool."""
    from automedia.mcp.tools import add_pool_topic as _impl

    return _impl(title=title, category=category, pool_db_path=pool_db_path)


def run_batch(
    topics: list[str],
    brand: str,
    mode: str = "auto",
) -> dict[str, Any]:
    """Execute pipelines for multiple topics sequentially."""
    from automedia.mcp.tools import run_batch as _impl

    return _impl(topics=topics, brand=brand, mode=mode)


def health_engine() -> dict[str, Any]:
    """Check all engine-related dependencies health."""
    from automedia.mcp.tools import health_engine as _impl

    return _impl()


# ---------------------------------------------------------------------------
# MCP Server construction
# ---------------------------------------------------------------------------


def create_server() -> FastMCP:
    """Create and configure the FastMCP server instance.

    Returns
    -------
    FastMCP
        A fully configured server with all 50 tools and 5 resources registered.
    """
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        name="AutoMedia",
        instructions="",
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
            "Return merged configuration (excluding secrets). "
            "When key is empty, returns all non-secret config keys. "
            "When key is specified (e.g. 'llm.temperature'), returns that value. "
            "Dot-notation traversal is supported. "
            "Secret keys (containing 'key', 'secret', 'password', or 'token') are redacted."
        ),
    )(get_config)

    mcp.tool(
        description=(
            "Return the list of agent red-line constraints. "
            "The 9 red lines are MUST/MUST NOT rules that agents must obey "
            "while working in this codebase — sourced from AGENTS.md §5."
        ),
    )(get_redlines)

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
            "and format recommendations. The result is ready to feed into the topic pool. "
            "Requires AUTOMEDIA_TAVILY_API_KEY for real-time trending data; "
            "defaults to simulated results when the env var is not set."
        ),
    )(research_topics)

    mcp.tool(
        description=(
            "Execute the full AutoMedia production pipeline. Returns PipelineResult as JSON. "
            "Modes: auto, text_only, text_with_cover, video_only, qa_only, "
            "image-carousel, social-thread, short-video. "
            "Accepts optional workflow name to apply workflow-level config overrides."
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
        description=(
            "Return all active and recently-finished pipelines. "
            "Reads the persistent session tracker (active_pipelines.json) "
            "and returns pipelines that are currently running, finished "
            "within the last 5 minutes, or marked 'lost' from a previous "
            "server session. Each entry includes project_id, status, "
            "current_gate, elapsed_s, mode, and topic. "
            "Survives server restarts."
        ),
    )(list_active_pipelines)

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
            "Compute content analytics for a project. "
            "Scans the project's 01_content/drafts/ for markdown files and "
            "returns word count, sentiment, readability, and brand mentions. "
            "Takes project_id and optional base_dir."
        ),
    )(effects_analyze_content)

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
            "Add a topic to the topic pool. "
            "Takes title, optional category, and optional pool_db_path. "
            "Returns the new topic id, title, category, and status."
        ),
    )(add_pool_topic)

    mcp.tool(
        name="pool_add_topic",
        description=(
            "⚠️ DEPRECATED: Use add_pool_topic instead. "
            "Add a topic to the topic pool. "
            "Takes title, optional category, and optional pool_db_path. "
            "Returns the new topic id, title, category, and status."
        ),
    )(pool_add_topic)

    # ------------------------------------------------------------------
    # Cron schedule tools
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Add a cron schedule entry. "
            "Takes a unique name, a 5-field cron expression, optional brand, "
            "category, and count. Validates the cron expression format and "
            "prevents duplicate names. Appends to cron/jobs.yaml."
        ),
    )(add_cron_schedule)

    mcp.tool(
        description=(
            "List cron schedule entries from cron/jobs.yaml "
            "with optional platform and mode filters. "
            "Returns entries sorted by name with their expression, "
            "brand, category, count, platform, and mode fields."
        ),
    )(list_cron_schedules)

    mcp.tool(
        description=(
            "Remove a cron schedule entry by name. Returns an error if the name is not found."
        ),
    )(remove_cron_schedule)

    # ------------------------------------------------------------------
    # Workflow tools
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "List all defined workflow configurations. "
            "Discovers workflow YAML files from .automedia/workflows/ "
            "and ~/.automedia/workflows/. Returns name, mode, platforms, "
            "and optional schedule/brand/gates/prompts/media for each "
            "workflow. Returns empty list when no workflows are defined."
        ),
    )(list_workflows)

    mcp.tool(
        description=(
            "Check cron system health. Validates cron/jobs.yaml schedule "
            "definitions and reports schedule counts. Does not include "
            "runtime monitoring data because AutoMedia has no built-in "
            "cron daemon — scheduling is delegated to an external crond. "
            "Returns jobs_valid, schedule_count, valid/invalid expression "
            "counts, static job definitions, and a note about limitations."
        ),
    )(get_cron_health)

    mcp.tool(
        description=(
            "Test and validate a cron expression. "
            "Returns whether the 5-field expression is syntactically valid, "
            "and if croniter is available, computes the next N trigger times. "
            "Accepts an optional count parameter (default 5, max 20)."
        ),
    )(test_cron_schedule)

    mcp.tool(
        description=(
            "List all overridable prompt templates with metadata (variables, "
            "purpose, override status). Checks ~/.automedia/overrides/prompts/ "
            "for existing overrides. Returns template names, their Jinja2 "
            "variables, purpose descriptions, and whether a user override exists."
        ),
    )(list_overridable_templates)

    mcp.tool(
        description=(
            "Publish a project to a platform. "
            "Takes project_id, platform name, optional account_id, and optional base_dir. "
            "Returns the publish result including URL."
        ),
    )(publish_content)

    mcp.tool(
        description=(
            "Distribute a project's content to one or more platforms. "
            "Takes project_id, optional comma-separated platforms (e.g. 'wechat,zhihu'), "
            "all (bool) to distribute to every registered platform, dry_run (bool) "
            "to validate without publishing, and optional base_dir. "
            "Returns a mapping of platform -> status and a summary string. "
            "When all=True, overrides the platforms parameter."
        ),
    )(distribute_content)

    mcp.tool(
        description=(
            "List all registered publishing platforms. "
            "Returns sorted list platform names and total count. "
            "Returns empty list when no adapters are registered (not an error)."
        ),
    )(list_platforms)

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
            "Execute pipelines for multiple topics sequentially. "
            "Takes a list of topics, brand, and optional mode "
            "(auto, text_only, text_with_cover, video_only, qa_only, "
            "image-carousel, social-thread, short-video). "
            "A single topic failure does not stop the batch. "
            "Returns per-topic results with a pass/fail summary."
        ),
    )(run_batch)

    mcp.tool(
        name="batch_run",
        description=(
            "⚠️ DEPRECATED: Use run_batch instead. "
            "Execute pipelines for multiple topics sequentially. "
            "Takes a list of topics, brand, and optional mode "
            "(auto, text_only, text_with_cover, video_only, qa_only, "
            "image-carousel, social-thread, short-video). "
            "A single topic failure does not stop the batch. "
            "Returns per-topic results with a pass/fail summary."
        ),
    )(batch_run)

    mcp.tool(
        description=(
            "Generate a content strategy via LLM then execute the AutoMedia "
            "production pipeline. Takes topic, brand, optional mode "
            "(auto, text_only, text_with_cover, video_only, qa_only, "
            "image-carousel, social-thread, short-video), optional "
            "strategy_context, and optional workflow name. Returns both "
            "the strategy output and the pipeline result."
        ),
    )(run_pipeline_from_strategy)

    # ------------------------------------------------------------------
    # Setup / Configuration tools (first-time setup)
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Initialize AutoMedia configuration with sensible defaults. "
            "Creates the .automedia/ directory structure and a default "
            "config.yaml.  When project_dir is provided, creates there; "
            "otherwise uses the current working directory. "
            "Returns the config directory and file paths."
        ),
    )(init_config)

    mcp.tool(
        description=(
            "Configure the LLM provider for AutoMedia. "
            "Writes provider, optional model, and optional API key to "
            "~/.automedia/model_config.yaml. "
            "WARNING: Storing API keys in config files is less secure "
            "than using AUTOMEDIA_LLM_API_KEY environment variable. "
            "Returns success status, provider, model, and config file path."
        ),
    )(configure_llm)

    mcp.tool(
        description=(
            "Create a new brand profile. "
            "Writes to ~/.automedia/brand_profiles.yaml using the brand "
            "profile schema.  The brand name is required; industry and "
            "target_audience are optional. "
            "Returns success status and brand metadata."
        ),
    )(add_brand)

    mcp.tool(
        description=(
            "One-step onboarding: configure LLM and create a brand profile. "
            "Accepts brand_name, llm_provider, llm_key, and optional base_url. "
            "Delegates to the same config-writing logic as the CLI onboard wizard. "
            "Returns success status, brand name, provider, and config directory."
        ),
    )(onboard)

    # ------------------------------------------------------------------
    # Brand tools
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "List all configured brands with full profile metadata. "
            "Returns structured list including aliases, CTA principles, "
            "blocked words, tone guidelines, brand identity, languages, "
            "industry, target audience, personality, and platforms. "
            "Returns empty list when no brands configured (not an error)."
        ),
    )(list_brands)

    mcp.tool(
        description=(
            "Search the asset library for brand assets. "
            "Performs combined SQLite keyword search and Chroma semantic search. "
            "Takes query, brand, optional limit (default 10), and optional filters "
            "(type, tags, lang, stage). "
            "Returns ranked results with relevance scores, metadata, and content. "
            "Empty query returns all assets filtered by other criteria (not an error)."
        ),
    )(search_assets)

    # ------------------------------------------------------------------
    # Account tools
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Register a new platform account for publishing. Returns the account_id and metadata."
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
        description=("Disconnect/remove a platform account. Requires account_id."),
    )(disconnect_account)

    # ------------------------------------------------------------------
    # Pipeline control tools
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Cancel a running pipeline by project_id. "
            "Sets the cancellation flag so the pipeline exits after the "
            "current gate completes."
        ),
    )(cancel_pipeline)

    mcp.tool(
        description=(
            "Pause a running pipeline by project_id. "
            "Signals the pipeline to pause after the current gate completes."
        ),
    )(pause_pipeline)

    mcp.tool(
        description=(
            "Resume a paused pipeline by project_id. "
            "Resumes execution of a previously paused pipeline."
        ),
    )(resume_pipeline)

    mcp.tool(
        description=(
            "Mark a specific gate for retry in a running pipeline. "
            "Takes project_id and gate_name (e.g. 'G0', 'V3'). "
            "The pipeline will re-execute the named gate on its next iteration."
        ),
    )(retry_gate)

    mcp.tool(
        description=(
            "Mark a specific gate for skipping in a running pipeline. "
            "Takes project_id and gate_name (e.g. 'G0', 'V3'). "
            "The pipeline will skip the named gate on its next iteration."
        ),
    )(skip_gate)

    # ------------------------------------------------------------------
    # Approval / rejection tools (director mode)
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Approve a gate output and resume pipeline execution. "
            "Finds the active engine for project_id and calls resume() "
            "with approved=True. Takes project_id, gate_name, and optional "
            "modifications dict. Returns approved status."
        ),
    )(approve_gate)

    mcp.tool(
        description=(
            "Reject a gate output and resume pipeline execution. "
            "Finds the active engine for project_id and calls resume() "
            "with approved=False. Takes project_id, gate_name, and optional "
            "reason string. Returns rejected status."
        ),
    )(reject_gate)

    mcp.tool(
        description=(
            "List gates currently awaiting approval in active pipelines. "
            "When project_id is provided, filters to that project only. "
            "Returns a list of pending approvals with gate_name and status."
        ),
    )(get_pending_approvals)

    mcp.tool(
        description=(
            "Check all engine-related dependencies (ComfyUI, hyperframes, "
            "edge-tts, whisper, FFmpeg, Bun, Chrome, LLM API) and return "
            "their installation and health status."
        ),
    )(health_engine)

    mcp.tool(
        name="engine_health",
        description=(
            "⚠️ DEPRECATED: Use health_engine instead. "
            "Check all engine-related dependencies (ComfyUI, hyperframes, "
            "edge-tts, whisper, FFmpeg, Bun, Chrome, LLM API) and return "
            "their installation and health status."
        ),
    )(engine_health)

    mcp.tool(
        description=(
            "Update an engine configuration setting. "
            "Writes a YAML override to ~/.automedia/overrides/rules/. "
            "Modality: tts, asr, image, or video. "
            "Setting: e.g. default, voice, host, port, model."
        ),
    )(update_engine_config)

    # ------------------------------------------------------------------
    # Help/introspection tool
    # ------------------------------------------------------------------

    mcp.tool(
        description=(
            "Get a categorized listing of all available MCP tools with descriptions. "
            "Use this to discover what tools are available."
        ),
    )(help_mcp)

    mcp.tool(
        name="mcp_help",
        description=(
            "⚠️ DEPRECATED: Use help_mcp instead. "
            "Get a categorized listing of all available MCP tools with descriptions. "
            "Use this to discover what tools are available."
        ),
    )(mcp_help)

    # Populate tool registry for mcp_help to introspect at call time
    _tool_registry.clear()
    for _name, _tool in mcp._tool_manager._tools.items():
        _tool_registry[_name] = {
            "name": _name,
            "description": _tool.description,
            "parameters": _tool.parameters,
        }

    # Generate dynamic instructions from the populated tool registry
    from automedia.mcp.instructions import generate_instructions

    mcp._mcp_server.instructions = generate_instructions(_tool_registry)

    # Set dynamic tool count for health_check
    from automedia.mcp.tools import set_tools_count

    set_tools_count(len(mcp._tool_manager._tools))

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

    @mcp.resource("automedia://getting_started")
    def _getting_started() -> str:
        """Return a setup checklist with steps and completion status."""
        return getting_started_resource()

    # Pass AutoMedia version to MCP protocol-level server info
    mcp._mcp_server.version = _automedia_version

    return mcp


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _shutdown_handler(signum: int, frame: object) -> None:  # noqa: ANN401 — signal handler frame is untyped
    """Clean shutdown on SIGTERM/SIGINT."""
    import signal

    from automedia.core.logging import get_logger

    log = get_logger(__name__)
    log.info("server.shutdown", signal=signum, hint="Shutting down MCP server")
    signal.signal(signum, signal.SIG_DFL)
    raise SystemExit(0)


def main() -> None:
    """Run the AutoMedia MCP server (stdio transport)."""
    import argparse
    import signal

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    parser = argparse.ArgumentParser(
        prog="python3 -m automedia.mcp.server",
        description="AutoMedia MCP Server — stdio transport with 50 tools and 5 resources.",
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
