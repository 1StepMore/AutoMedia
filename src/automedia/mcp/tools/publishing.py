"""Publishing and platform registration MCP tools."""
from __future__ import annotations

import importlib
from typing import Any

from structlog import get_logger

from automedia.exceptions import AutoMediaError, ModuleLoadError
from automedia.mcp.tools._shared import (
    MCPErrorCode,
    NonEmptyStr,
    _discover_projects,
    _require_allowed,
    _resolve_projects_dir,
    error_response,
    success_response,
)

log = get_logger(__name__)

__all__ = [
    "list_platforms",
    "publish_content",
    "register_platform_adapter",
]


def publish_content(
    project_id: NonEmptyStr,
    platform: str,
    account_id: str = "",
    base_dir: str = "",
    mode: str = "auto",
) -> dict[str, Any]:
    """Publish a project to a platform.

    Parameters
    ----------
    project_id:
        Project identifier.
    platform:
        Target platform name (e.g. ``"xiaohongshu"``, ``"zhihu"``).
    account_id:
        Optional account identifier for PRD-4 account-aware publishing.
    base_dir:
        Root directory containing project directories.
    mode:
        Publish mode. ``"auto"`` (default) respects the brand profile's
        automation level.  ``"publish"`` forces full publish regardless
        of automation level (overrides ``"review"`` to ``"auto"``).

    Returns
    -------
    dict
        ``{"published": bool, "platform": str, "url": str, …}``
        or an error dict on failure.  When the automation level is
        ``"review"`` and mode is ``"auto"``, the result includes
        ``status: "draft_created"`` and ``draft_url``.
    """
    try:
        _require_allowed(base_dir, tool_name="publish_content")

        from automedia.adapters.publish_engine import PublishEngine

        projects_dir = base_dir or _resolve_projects_dir()
        projects = _discover_projects(projects_dir)
        match = [p for p in projects if p.get("project_id") == project_id]
        if not match:
            return {
                "published": False,
                **error_response(
                    MCPErrorCode.NOT_FOUND,
                    f"Project {project_id!r} not found",
                    "Verify project_id",
                ),
            }

        proj = match[0]
        artifact_dir = proj["_dir"]

        # Resolve per-platform automation levels from brand profile
        from automedia.manifests.brand_profile_schema import load_brand_profiles  # noqa: PLC0415

        automation: dict[str, str] | None = None
        brand_name = proj.get("brand", "")
        if brand_name:
            profiles = load_brand_profiles()
            profile = profiles.get(brand_name)
            if profile is not None:
                automation = dict(profile.automation) if profile.automation else {}

        # mode="publish" overrides review → auto for the target platform
        if mode == "publish":
            if automation is None:
                automation = {}
            automation[platform] = "auto"

        engine = PublishEngine()
        account_ids = [account_id] if account_id else None
        result = engine.publish_all(
            artifact_dir=artifact_dir,
            project=proj,
            account_ids=account_ids,
            automation=automation,
        )

        # -- Log distribution attempts to asset library -------------------
        try:
            from automedia.asset_library.db import AssetDatabase

            db = AssetDatabase(brand_name or "default")
            for key, res in result.items():
                res_platform = res.get("platform", key)
                res_status = res.get("status", "")
                distro_status: str = "failure"
                if res_status in ("ok", "published", "success"):
                    distro_status = "success"
                elif res_status == "draft_created":
                    distro_status = "draft_created"
                elif res_status == "skipped":
                    distro_status = "skipped"

                db.log_distribution(
                    project_id=project_id,
                    platform=res_platform,
                    status=distro_status,
                    account_id=key if account_ids else "",
                    error_message=res.get("reason", res.get("error_message", "")),
                    url=res.get("url", ""),
                )
        except Exception as exc:
            log.warning("publish.distro_log_failed", error=str(exc))

        platform_result = result.get(platform, {})
        status = platform_result.get("status", "")
        success = platform_result.get("success", False) or status in ("ok", "published")
        base_response: dict[str, Any] = {
            "published": success,
            "platform": platform,
            "url": platform_result.get("url", ""),
        }
        if status == "draft_created":
            base_response["status"] = "draft_created"
            base_response["draft_url"] = platform_result.get("draft_url", "")
            base_response["draft_id"] = platform_result.get("draft_id", "")
        elif status == "error":
            base_response["published"] = False
            base_response["error"] = platform_result.get("reason", "unknown error")
        return success_response(base_response)
    except ImportError as exc:
        return {"published": False, **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except OSError as exc:
        return {"published": False, **error_response(MCPErrorCode.UNKNOWN, f"File I/O error: {exc}")}
    except AutoMediaError as exc:
        return {"published": False, **error_response(MCPErrorCode.PIPELINE_ERROR, str(exc))}
    except Exception as exc:
        return {"published": False, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def list_platforms() -> dict[str, Any]:
    """List all registered publishing platforms.

    Uses :class:`automedia.adapters.registry.AdapterRegistry` to enumerate
    all registered adapters by their platform name.

    Returns
    -------
    dict
        ``{"platforms": [...], "total": N}`` — sorted list of platform
        names and their count.  Never raises.  Returns empty list when
        no adapters are registered (not an error).
    """
    from automedia.adapters.registry import AdapterRegistry

    try:
        platforms = AdapterRegistry.list()
        return success_response({"platforms": platforms, "total": len(platforms)})
    except ImportError as exc:
        return {"platforms": [], "total": 0, **error_response(MCPErrorCode.IMPORT_ERROR, str(exc))}
    except AutoMediaError as exc:
        return {"platforms": [], "total": 0, **error_response(MCPErrorCode.ENGINE_ERROR, str(exc))}
    except Exception as exc:
        return {"platforms": [], "total": 0, **error_response(MCPErrorCode.UNKNOWN, str(exc))}


def register_platform_adapter(
    platform_name: str,
    adapter_class: str = "",
) -> dict[str, Any]:
    """Register a platform adapter (stub — PRD-1 NG6).

    ------------------------------------------------------------------
    ╔══════════════════════════════════════════════════════════════════╗
    ║  STUB NOTICE: Per PRD-1 NG6, no new content production          ║
    ║  platforms are added in this phase.  This function serves as    ║
    ║  a **validated placeholder** that records the intent to         ║
    ║  register an adapter, but does *not* wire up real platform      ║
    ║  connectivity.                                                  ║
    ║                                                                ║
    ║  Future implementation path:                                     ║
    ║  1. Create a concrete adapter class in a new module under        ║
    ║     ``automedia/adapters/`` (e.g. ``wechat.py``).               ║
    ║  2. The class should inherit from a base adapter protocol        ║
    ║     (defined elsewhere) and implement ``publish()``.             ║
    ║  3. Call this function with the dotted path to that class.       ║
    ║  4. The dynamic import below will register it with               ║
    ║     ``AdapterRegistry`` for downstream use.                     ║
    ╚══════════════════════════════════════════════════════════════════╝
    ------------------------------------------------------------------

    Parameters
    ----------
    platform_name:
        Platform identifier (e.g. ``"wechat"``, ``"weibo"``).
        Must be non-empty and match ``[a-zA-Z0-9_-]+``.
    adapter_class:
        Dotted Python path to the adapter class (e.g.
        ``"automedia.adapters.wechat.WeChatAdapter"``).
        When empty the function acts as a pure stub.

    Returns
    -------
    dict
        With ``adapter_class``: ``{"registered": True, "platform": str,
        "class": str}`` on success.
        Without ``adapter_class``: ``{"registered": False, "stub": True,
        "platform": str, "message": str, "instructions": str}``.
        On error: ``{"registered": False,
        "error": {"code": ..., "message": ..., "resolution": ...}}``.
    """
    import re

    if not platform_name or not isinstance(platform_name, str):
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.INVALID_PARAM,
                "platform_name must be a non-empty string.",
            ),
        }
    if not re.match(r"^[a-zA-Z0-9_-]+$", platform_name):
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.INVALID_PARAM,
                (
                    f"Invalid platform_name {platform_name!r}. "
                    f"Use only letters, digits, underscores, and hyphens."
                ),
            ),
        }

    try:
        from automedia.adapters.registry import AdapterRegistry

        if adapter_class:
            module_path, _, class_name = adapter_class.rpartition(".")
            if not module_path:
                return {
                    "registered": False,
                    **error_response(
                        MCPErrorCode.INVALID_PARAM,
                        (
                            f"Invalid adapter_class {adapter_class!r}: "
                            f"must be a dotted path (e.g. 'pkg.mod.ClassName')."
                        ),
                    ),
                }
            if not module_path.startswith("automedia.adapters."):
                return {
                    "registered": False,
                    **error_response(
                        MCPErrorCode.INVALID_PARAM,
                        (
                            f"Invalid adapter class: {adapter_class!r}. "
                            f"Must be in automedia.adapters.* namespace"
                        ),
                    ),
                }
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", class_name):
                return {
                    "registered": False,
                    **error_response(
                        MCPErrorCode.INVALID_PARAM,
                        (
                            f"Invalid class name in {adapter_class!r}. "
                            f"Class name must match [A-Za-z_][A-Za-z0-9_]*."
                        ),
                    ),
                }
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            AdapterRegistry.register(cls)
            return success_response(
                {
                    "registered": True,
                    "platform": platform_name,
                    "class": adapter_class,
                }
            )

        return success_response(
            {
                "registered": False,
                "platform": platform_name,
                "stub": True,
                "message": (
                    f"Stub: adapter for {platform_name!r} acknowledged. "
                    f"Provide a dotted ``adapter_class`` path to fully register."
                ),
                "instructions": (
                    f"To implement the {platform_name!r} adapter:\n"
                    f"  1. Create automedia/adapters/{platform_name}.py with a class\n"
                    f"     that implements the adapter protocol.\n"
                    f"  2. Call register_platform_adapter(\n"
                    f"       platform_name={platform_name!r},\n"
                    f"       adapter_class='automedia.adapters.{platform_name}.<ClassName>',\n"
                    f"     )\n"
                    f"  3. The adapter will be registered with AdapterRegistry."
                ),
            }
        )

    except (ImportError, ModuleNotFoundError) as exc:
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.IMPORT_ERROR,
                f"Could not import adapter class: {exc}",
            ),
        }
    except AttributeError as exc:
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.INVALID_PARAM,
                f"Adapter class not found in module: {exc}",
            ),
        }
    except ModuleLoadError as exc:
        return {
            "registered": False,
            **error_response(
                MCPErrorCode.IMPORT_ERROR,
                str(exc),
            ),
        }
    except Exception as exc:
        return {"registered": False, **error_response(MCPErrorCode.UNKNOWN, str(exc))}
