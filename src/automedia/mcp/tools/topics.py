"""Topic pool MCP tools — selection, research, pool management."""

from __future__ import annotations

import os
import warnings
from typing import Any

from pydantic import ValidationError
from structlog import get_logger

from automedia.core.llm_client import LLMError
from automedia.exceptions import AutoMediaError
from automedia.mcp.tools._shared import (
    MCPErrorCode,
    ResearchPattern,
    _require_allowed,
    error_response,
    success_response,
    validation_error_response,
)

log = get_logger(__name__)

__all__ = [
    "add_pool_topic",
    "list_topic_pool",
    "pool_add_topic",
    "research_topics",
    "select_topic",
]


def select_topic(
    category: str = "",
    tenant_id: str = "default",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """Select the highest-scored pending topic from the pool.

    Parameters
    ----------
    category:
        Optional category filter (e.g. ``"tech"``, ``"finance"``).
    tenant_id:
        Tenant / namespace identifier.
    pool_db_path:
        Explicit path to the topic pool SQLite database.  When
        empty the default location is used.

    Returns
    -------
    dict
        ``{"selected": {...}, "remaining_count": int}`` or
        ``{"selected": null, "remaining_count": 0, "error": {...}}``
        where the error dict contains ``code``, ``message``, ``resolution`` keys.
    """
    try:
        from automedia.pool.db import PoolDB, default_pool_path

        if pool_db_path:
            _require_allowed(pool_db_path, tool_name="select_topic")
            db = PoolDB(pool_db_path)
        else:
            db = PoolDB(default_pool_path())

        topics = db.list_topics(status="pending")
        if category:
            topics = [t for t in topics if t.get("category") == category]
        if tenant_id and tenant_id != "default":
            topics = [t for t in topics if t.get("tenant_id") == tenant_id]

        if not topics:
            return {
                "selected": None,
                "remaining_count": 0,
                **error_response(
                    MCPErrorCode.NOT_FOUND,
                    "No pending topics found",
                    "Add topics to the pool first",
                ),
            }

        # Sort by score descending
        topics.sort(key=lambda t: t.get("score", 0.0), reverse=True)
        chosen = topics[0]
        db.mark_selected(chosen["id"])
        db.close()
        return success_response({"selected": chosen, "remaining_count": len(topics) - 1})

    except ImportError as exc:
        return {"selected": None, **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except AutoMediaError as exc:
        return {"selected": None, **error_response(MCPErrorCode.PIPELINE_ERROR, str(exc))}
    except Exception as exc:
        return {"selected": None, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def _fetch_tavily_trending(category: str) -> str:
    api_key = os.environ.get("AUTOMEDIA_TAVILY_API_KEY", "")
    if not api_key:
        return ""

    try:
        import httpx
    except ImportError:
        return ""

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": category,
                    "search_depth": "advanced",
                    "max_results": 8,
                    "include_domains": [],
                    "exclude_domains": [],
                },
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
    except Exception:
        return ""

    results = data.get("results", [])
    if not results:
        return ""

    lines: list[str] = []
    for item in results[:8]:
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "")[:200]
        if title:
            lines.append(f"- {title}")
            if content:
                lines.append(f"  {content}")
    return "\n".join(lines) if lines else ""


def _persist_researched_topics(topics: list[dict[str, Any]], category: str) -> int:
    """Insert researched topics into the default pool, deduped by title.

    Mirrors the CLI's ``pool-collect`` insert pattern (``cli/commands/cron.py``):
    a :class:`TopicDeduplicator` skips any title similar to one already in the
    pool, and each newly inserted title is appended to the in-batch comparison
    set so duplicates *within* one response are skipped too.

    Returns
    -------
    int
        Number of rows actually inserted (duplicates skipped).
    """
    from automedia.pool.db import PoolDB, default_pool_path
    from automedia.pool.dedup import TopicDeduplicator

    db = PoolDB(default_pool_path())
    try:
        dedup = TopicDeduplicator()
        existing_titles = [str(t.get("title", "")) for t in db.list_topics()]
        inserted = 0
        for topic in topics:
            title = str(topic.get("title", "")).strip()
            if not title or dedup.is_duplicate(title, existing_titles):
                continue
            raw_score = topic.get("confidence_score", 0.0)
            db.add_topic(
                {
                    "title": title,
                    "category": str(topic.get("category", "") or category),
                    "source": "research_topics",
                    "score": float(raw_score) if isinstance(raw_score, (int, float)) else 0.0,
                    "status": "pending",
                }
            )
            existing_titles.append(title)
            inserted += 1
        return inserted
    finally:
        db.close()


def research_topics(
    category: str,
    count: int = 5,
    trending_data: str = "",
    pattern: ResearchPattern = "b",
) -> dict[str, Any]:
    """Research trending or high-potential topics within a category using LLM.

    Uses the ``topic_research`` prompt template and the
    :class:`TopicResearchOutput` Pydantic model to produce a structured
    list of topic suggestions with angles, confidence scores, and format
    recommendations.  The result is ready to feed into the topic pool.

    When ``AUTOMEDIA_TAVILY_API_KEY`` is configured, the function first
    fetches real-time trending signals from the Tavily Search API and
    passes them as ``trending_data`` to the LLM, providing up-to-date
    context beyond the LLM's training data cutoff.

    Parameters
    ----------
    category:
        Content category to research (e.g. ``"AI Tools"``, ``"Finance"``).
    count:
        Number of topics to generate (default 5).
    trending_data:
        Optional context — trending signals, audience data, or keywords
        to steer the LLM toward relevant topics.  When Tavily is
        configured, real-time data is merged into this field.
    pattern:
        When ``"a"``, return raw input data without calling the LLM.
        When ``"b"`` (default), use the LLM as usual.

    Returns
    -------
    dict
        ``{"topics": [...], "category": str, "total_found": int}``
        or an error dict on failure.
    """
    if pattern == "a":
        return success_response(
            {
                "topics": [],
                "category": category,
                "total_found": 0,
                "note": "pattern_a_raw_data",
            }
        )
    try:
        from automedia.core.llm_client import llm_complete_structured_safe
        from automedia.decision.pydantic import TopicResearchOutput
        from automedia.prompts import load_prompt

        if not trending_data:
            tavily_data = _fetch_tavily_trending(category)
            if tavily_data:
                trending_data = f'Real-time search results for "{category}":\n{tavily_data}'

        prompt = load_prompt(
            "topic_research",
            category=category,
            count=count,
            trending_data=trending_data,
        )
        result = llm_complete_structured_safe(
            prompt,
            response_format=TopicResearchOutput,
        )
        payload = result.model_dump()
        payload["persisted"] = _persist_researched_topics(payload.get("topics", []), category)
        return success_response(payload)
    except LLMError as exc:
        return {
            "topics": [],
            "category": category,
            "total_found": 0,
            **error_response(MCPErrorCode.LLM_ERROR, str(exc)),
        }
    except ImportError as exc:
        return {
            "topics": [],
            "category": category,
            "total_found": 0,
            **error_response(MCPErrorCode.IMPORT_ERROR, str(exc)),
        }
    except ValidationError as exc:
        return {
            "topics": [],
            "category": category,
            "total_found": 0,
            **validation_error_response(
                f"LLM response validation failed: {exc}",
                errors=[
                    {"field": str(e.get("loc", "unknown")), "message": e.get("msg", "")}
                    for e in (exc.errors() if hasattr(exc, "errors") else [])
                ],
            ),
        }
    except Exception as exc:
        return {
            "topics": [],
            "category": category,
            "total_found": 0,
            **error_response(MCPErrorCode.UNKNOWN, str(exc)),
        }


def list_topic_pool(
    status: str = "",
    category: str = "",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """List topics in the pool, optionally filtered by status or category.

    Parameters
    ----------
    status:
        Filter by topic status (e.g. ``"pending"``, ``"selected"``).
    category:
        Filter by category.
    pool_db_path:
        Explicit path to the topic pool SQLite database.

    Returns
    -------
    dict
        ``{"topics": [...], "count": int}``.
    """
    try:
        from automedia.pool.db import PoolDB, default_pool_path

        if pool_db_path:
            _require_allowed(pool_db_path, tool_name="list_topic_pool")
            db = PoolDB(pool_db_path)
        else:
            db = PoolDB(default_pool_path())

        topics = db.list_topics(status=status or None)
        if category:
            topics = [t for t in topics if t.get("category") == category]
        db.close()
        return success_response({"topics": topics, "count": len(topics)})

    except ImportError as exc:
        return {"topics": [], **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except AutoMediaError as exc:
        return {"topics": [], **error_response(MCPErrorCode.PIPELINE_ERROR, str(exc))}
    except Exception as exc:
        return {"topics": [], **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def add_pool_topic(
    title: str,
    category: str = "",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """Add a topic to the topic pool.

    Parameters
    ----------
    title:
        Title of the topic to add.
    category:
        Optional category for the topic.
    pool_db_path:
        Explicit path to the topic pool SQLite database.

    Returns
    -------
    dict
        ``{"id": int, "title": str, "category": str, "status": "pending"}``
        or an error dict on failure.
    """
    try:
        from automedia.pool.db import PoolDB, default_pool_path

        if pool_db_path:
            _require_allowed(pool_db_path, tool_name="add_pool_topic")
            db = PoolDB(pool_db_path)
        else:
            db = PoolDB(default_pool_path())

        topic_id = db.add_topic(data={"title": title, "category": category})
        db.close()
        return success_response(
            {
                "id": topic_id,
                "title": title,
                "category": category,
                "status": "pending",
            }
        )
    except ImportError as exc:
        return error_response(MCPErrorCode.IMPORT_ERROR, str(exc))
    except AutoMediaError as exc:
        return error_response(MCPErrorCode.PIPELINE_ERROR, str(exc))
    except Exception as exc:
        return error_response(MCPErrorCode.UNKNOWN, str(exc))


def pool_add_topic(
    title: str,
    category: str = "",
    pool_db_path: str = "",
) -> dict[str, Any]:
    """⚠️ DEPRECATED: Use :func:`add_pool_topic` instead."""
    warnings.warn(
        "pool_add_topic is deprecated, use add_pool_topic instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return add_pool_topic(title=title, category=category, pool_db_path=pool_db_path)
