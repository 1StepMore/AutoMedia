"""L1 Publish-Log Schema Gate — JSON schema validation of publish_log.

Validates that the publish_log object conforms to a predefined JSON schema
before it enters the pipeline. Required fields: topic, content, media_paths,
platform. Optional fields: version, created_at.
"""

from __future__ import annotations

from typing import Any

from structlog import get_logger

from automedia.gates._context import GateContext
from automedia.gates._result import CheckResult, build_gate_result
from automedia.gates.base import BaseGate
from automedia.gates.helpers import apply_mock_overrides

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema for publish_log
# ---------------------------------------------------------------------------

_PUBLISH_LOG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["topic", "content", "media_paths", "platform"],
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "content": {"type": "string", "minLength": 1},
        "media_paths": {"type": "array", "items": {"type": "string"}},
        "platform": {
            "type": "string",
            "enum": [
                "wechat",
                "weibo",
                "douyin",
                "bilibili",
                "xiaohongshu",
                "youtube",
                "twitter",
            ],
        },
        "version": {"type": "string"},
        "created_at": {"type": "string"},
    },
}

# ---------------------------------------------------------------------------
# Check names
# ---------------------------------------------------------------------------

_CHECK_NAMES: list[str] = [
    "topic_present",
    "content_present",
    "media_paths_valid",
    "platform_valid",
    "version_valid",
    "timestamp_valid",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------



def _check_topic_present(publish_log: dict[str, Any]) -> CheckResult:
    """Check that *topic* is a non-empty string."""
    name = "topic_present"
    topic = publish_log.get("topic")
    if isinstance(topic, str) and len(topic.strip()) > 0:
        return {"name": name, "passed": True, "detail": "topic is present and non-empty"}
    return {"name": name, "passed": False, "detail": "topic is missing or empty"}


def _check_content_present(publish_log: dict[str, Any]) -> CheckResult:
    """Check that *content* is a non-empty string."""
    name = "content_present"
    content = publish_log.get("content")
    if isinstance(content, str) and len(content.strip()) > 0:
        return {"name": name, "passed": True, "detail": "content is present and non-empty"}
    return {"name": name, "passed": False, "detail": "content is missing or empty"}


def _check_media_paths_valid(publish_log: dict[str, Any]) -> CheckResult:
    """Check that *media_paths* is an array of non-empty strings."""
    name = "media_paths_valid"
    media_paths = publish_log.get("media_paths")
    if not isinstance(media_paths, list):
        return {"name": name, "passed": False, "detail": "media_paths is not a list"}
    if len(media_paths) == 0:
        return {"name": name, "passed": True, "detail": "media_paths is empty (allowed)"}
    for i, p in enumerate(media_paths):
        if not isinstance(p, str) or len(p.strip()) == 0:
            return {
                "name": name,
                "passed": False,
                "detail": f"media_paths[{i}] is not a non-empty string",
            }
    return {
        "name": name,
        "passed": True,
        "detail": f"media_paths contains {len(media_paths)} valid path(s)",
    }


def _check_platform_valid(publish_log: dict[str, Any]) -> CheckResult:
    """Check that *platform* is one of the allowed values."""
    name = "platform_valid"
    valid_platforms: set[str] = set(_PUBLISH_LOG_SCHEMA["properties"]["platform"]["enum"])
    platform = publish_log.get("platform")
    if isinstance(platform, str) and platform in valid_platforms:
        return {"name": name, "passed": True, "detail": f"platform '{platform}' is valid"}
    return {
        "name": name,
        "passed": False,
        "detail": f"platform '{platform}' is not in {sorted(valid_platforms)}",
    }


def _check_version_valid(publish_log: dict[str, Any]) -> CheckResult:
    """Check that *version* is a string if provided (optional field)."""
    name = "version_valid"
    if "version" not in publish_log:
        return {"name": name, "passed": True, "detail": "version not provided (optional)"}
    version = publish_log["version"]
    if isinstance(version, str) and len(version.strip()) > 0:
        return {"name": name, "passed": True, "detail": f"version '{version}' is valid"}
    return {"name": name, "passed": False, "detail": "version is present but empty"}


def _check_timestamp_valid(publish_log: dict[str, Any]) -> CheckResult:
    """Check that *created_at* is a valid ISO-format string if provided."""
    name = "timestamp_valid"
    if "created_at" not in publish_log:
        return {"name": name, "passed": True, "detail": "created_at not provided (optional)"}
    ts = publish_log["created_at"]
    if not isinstance(ts, str) or len(ts.strip()) == 0:
        return {"name": name, "passed": False, "detail": "created_at is present but empty"}
    # Basic ISO-format sanity check
    if "T" not in ts and not ts.replace("-", "").isdigit():
        return {
            "name": name,
            "passed": False,
            "detail": f"created_at '{ts}' does not look like ISO format",
        }
    return {"name": name, "passed": True, "detail": f"created_at '{ts}' is valid"}


# ---------------------------------------------------------------------------
# L1PublishLogSchema gate
# ---------------------------------------------------------------------------


class L1PublishLogSchema(BaseGate):
    """L1 Publish-Log Schema Gate — JSON schema validation of publish_log.

    ``gate_context`` expected keys:
        - ``publish_log``: dict — the publish_log payload to validate
        - ``_mock_results`` (optional): dict mapping check names to
          ``{"passed": bool, "detail": str}`` — drives deterministic results
          for testing.
    """

    _gate_name = "L1"
    _failure_mode = "stop"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Run 6 schema checks and return structured result."""
        publish_log: dict[str, Any] = gate_context.get("publish_log", {})
        mock_results: dict[str, dict[str, Any]] | None = gate_context.get("_mock_results")

        check_fns: list[tuple[str, Any]] = [
            ("topic_present", lambda: _check_topic_present(publish_log)),
            ("content_present", lambda: _check_content_present(publish_log)),
            ("media_paths_valid", lambda: _check_media_paths_valid(publish_log)),
            ("platform_valid", lambda: _check_platform_valid(publish_log)),
            ("version_valid", lambda: _check_version_valid(publish_log)),
            ("timestamp_valid", lambda: _check_timestamp_valid(publish_log)),
        ]

        checks = apply_mock_overrides(check_fns, mock_results)

        return build_gate_result(checks, gate="L1")
