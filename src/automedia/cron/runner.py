"""Cron pipeline runner — execute scheduled pipeline runs from cron jobs.

Provides :func:`run_scheduled_pipeline` which reads schedule entries from
``cron/jobs.yaml``, selects a topic from the pool, runs the full pipeline
with the configured **mode**, and optionally publishes to a specific
**platform** (or all brand-configured platforms when platform is empty).
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.pipelines.runner import run_full_pipeline

log = get_logger(__name__)

_DEFAULT_POOL_DB = ".automedia/pool.db"


def _select_topic_from_pool(
    category: str = "",
    pool_db_path: str = "",
) -> str | None:
    """Select the highest-scored pending topic from the pool.

    Parameters
    ----------
    category:
        Optional category filter.
    pool_db_path:
        Explicit path to the pool database.  Falls back to
        ``.automedia/pool.db`` when empty.

    Returns
    -------
    str or None
        The selected topic title, or ``None`` if no pending topics match.
    """
    from automedia.pool.db import PoolDB

    db_path = pool_db_path or _DEFAULT_POOL_DB
    db = PoolDB(db_path)
    try:
        topics = db.list_topics(status="pending")
        if category:
            topics = [t for t in topics if t.get("category") == category]

        if not topics:
            return None

        # Sort by score descending, pick the highest
        topics.sort(key=lambda t: t.get("score", 0.0), reverse=True)
        chosen = topics[0]
        db.mark_selected(chosen["id"])
        return chosen["title"]
    finally:
        db.close()


def _publish_to_platform(
    artifact_dir: str,
    project_id: str,
    topic: str,
    brand: str,
    platform: str,
) -> dict[str, Any]:
    """Publish a project's artefacts to *platform*.

    Parameters
    ----------
    artifact_dir:
        Path to the project's artifact directory.
    project_id:
        The project identifier.
    topic:
        The content topic.
    brand:
        Brand identifier.
    platform:
        Target platform name (e.g. ``"wechat"``, ``"zhihu"``).

    Returns
    -------
    dict
        Publish result dict from the adapter.
    """
    from automedia.adapters.publish_engine import PublishEngine

    project: dict[str, Any] = {
        "project_id": project_id,
        "topic": topic,
        "brand": brand,
    }

    engine = PublishEngine()
    results = engine.publish_all(
        artifact_dir=artifact_dir,
        project=project,
    )
    return results.get(platform, {"status": "not_attempted", "platform": platform})


def _publish_to_all_platforms(
    artifact_dir: str,
    project_id: str,
    topic: str,
    brand: str,
) -> dict[str, dict[str, Any]]:
    """Publish a project's artefacts to all registered / enabled platforms.

    This is the default behaviour when no specific platform is requested.

    Parameters
    ----------
    artifact_dir:
        Path to the project's artifact directory.
    project_id:
        The project identifier.
    topic:
        The content topic.
    brand:
        Brand identifier.

    Returns
    -------
    dict[str, dict]
        Mapping of platform name -> publish result dict.
    """
    from automedia.adapters.publish_engine import PublishEngine

    project: dict[str, Any] = {
        "project_id": project_id,
        "topic": topic,
        "brand": brand,
    }

    engine = PublishEngine()
    return engine.publish_all(
        artifact_dir=artifact_dir,
        project=project,
    )


def run_scheduled_pipeline(
    schedule_entry: dict[str, Any],
    *,
    pool_db_path: str = "",
) -> dict[str, Any]:
    """Execute a scheduled pipeline run based on a schedule entry.

    The pipeline is run with the **mode** configured in the schedule entry.
    After a successful or partial run the result is optionally published:

    * If **platform** is non-empty, the artifact is published to that
      platform only.
    * If **platform** is empty (default), the artifact is published to all
      brand-configured / registered platforms.

    Parameters
    ----------
    schedule_entry:
        A schedule entry dict.  Expected keys:

        * ``name`` — unique schedule name
        * ``brand`` — brand identifier (required)
        * ``category`` — optional topic category filter
        * ``mode`` — pipeline mode (default ``"auto"``)
        * ``platform`` — optional target platform (empty = publish all)
        * ``count`` — reserved for future batch support (ignored here)
    pool_db_path:
        Explicit path to the topic pool database.  Uses the default
        ``.automedia/pool.db`` when empty.

    Returns
    -------
    dict
        Result dict with keys:

        * ``status`` — ``"success"``, ``"partial"``, or ``"failed"``
        * ``topic`` — the selected topic title
        * ``project_id`` — project identifier (when pipeline ran)
        * ``mode`` — the pipeline mode used
        * ``platform`` — the target platform (may be empty)
        * ``publish_results`` — optional, present when publish was attempted
        * ``error`` — error message on failure
    """
    name: str = schedule_entry.get("name", "unnamed")
    brand: str = schedule_entry.get("brand", "")
    category: str = schedule_entry.get("category", "")
    mode: str = schedule_entry.get("mode", "") or "auto"
    platform: str = schedule_entry.get("platform", "")

    if not brand:
        return {"status": "failed", "error": f"Schedule {name!r} has no brand configured"}

    log.info(
        "cron.runner.start",
        name=name,
        brand=brand,
        category=category,
        mode=mode,
        platform=platform,
    )

    # ------------------------------------------------------------------
    # 1. Select a topic from the pool
    # ------------------------------------------------------------------
    try:
        topic = _select_topic_from_pool(category=category, pool_db_path=pool_db_path)
    except Exception as exc:
        msg = f"Topic selection failed: {exc}"
        log.error("cron.runner.topic_select_failed", name=name, error=msg)
        return {"status": "failed", "error": msg}

    if topic is None:
        msg = "No pending topic available for schedule" + (f" (category={category})" if category else "")
        log.warning("cron.runner.no_topic", name=name, category=category)
        return {"status": "failed", "error": msg}

    log.info("cron.runner.topic_selected", name=name, topic=topic)

    # ------------------------------------------------------------------
    # 2. Run the full pipeline
    # ------------------------------------------------------------------
    try:
        result = run_full_pipeline(
            topic=topic,
            brand=brand,
            mode=mode,
        )
    except Exception as exc:
        msg = f"Pipeline execution failed: {exc}"
        log.error("cron.runner.pipeline_failed", name=name, error=msg)
        return {"status": "failed", "error": msg, "topic": topic}

    response: dict[str, Any] = {
        "status": result.status,
        "topic": topic,
        "project_id": result.project_id,
        "mode": mode,
        "platform": platform,
        "brand": brand,
    }

    # ------------------------------------------------------------------
    # 3. Publish (if pipeline produced output)
    # ------------------------------------------------------------------
    if result.status in ("success", "partial") and result.project_dir:
        try:
            if platform:
                # Single-platform publish
                pub_result = _publish_to_platform(
                    artifact_dir=result.project_dir,
                    project_id=result.project_id,
                    topic=topic,
                    brand=brand,
                    platform=platform,
                )
                response["publish_results"] = {platform: pub_result}
                log.info(
                    "cron.runner.published_platform",
                    name=name,
                    platform=platform,
                    status=pub_result.get("status"),
                )
            else:
                # All-platforms publish
                pub_results = _publish_to_all_platforms(
                    artifact_dir=result.project_dir,
                    project_id=result.project_id,
                    topic=topic,
                    brand=brand,
                )
                response["publish_results"] = pub_results
                log.info(
                    "cron.runner.published_all",
                    name=name,
                    platform_count=len(pub_results),
                )
        except Exception as exc:
            log.warning(
                "cron.runner.publish_failed",
                name=name,
                platform=platform or "all",
                error=str(exc),
            )
            response["publish_error"] = str(exc)

    log.info(
        "cron.runner.complete",
        name=name,
        status=response["status"],
        project_id=result.project_id,
    )
    return response
