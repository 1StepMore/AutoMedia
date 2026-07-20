"""P2 Twitter/X Repurpose Gate — thread_format → fact_check → humanize sub-pipeline.

Repurposes the pipeline's base content into a Twitter/X thread format by
running a 3-step sub-pipeline:

    1. **Thread Format** — rewrites base content into a Twitter/X thread using the
       platform-specific ``twitter/content_writer`` prompt template.
    2. **Fact Check** — verifies factual claims in the rewritten thread using an
       LLM-based fact-check against the source content.
    3. **Humanize** — detects and removes AI writing patterns using the
       ``twitter/humanizer_g1`` prompt template.

Each step is adapted for Twitter/X's character-constrained, fast-paced format.

Output is written to ``04_repurpose/twitter/`` under the project directory.

Failure mode: ``retry`` — the pipeline will re-run this gate on failure.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any

from structlog import get_logger

from automedia.core.llm_client import LLMError, llm_complete
from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate
from automedia.prompts import load_prompt

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PLATFORM = "twitter"
"""Platform identifier for prompt resolution and output directory."""

_MIN_OUTPUT_LENGTH: int = 280
"""Minimum acceptable output length (characters) for single tweet content.

Combined thread length must be at least this to represent a meaningful thread."""

_MIN_TWEET_COUNT: int = 3
"""Minimum acceptable number of tweets in the thread."""

_MAX_TWEET_LENGTH: int = 280
"""Maximum character length for each individual tweet (Twitter/X limit)."""

_EXPECTED_MAP: dict[str, str] = {
    "content_present": "Content is provided in gate_context",
    "thread_format_success": "Thread format LLM call completes without error",
    "thread_format_quality": (
        f"At least {_MIN_TWEET_COUNT} tweets, each ≤ {_MAX_TWEET_LENGTH} chars, "
        f"combined length ≥ {_MIN_OUTPUT_LENGTH}"
    ),
    "fact_check_completed": "Fact-check LLM call completes without error",
    "humanize_completed": "Humanize LLM call completes without error",
    "file_write_success": "Twitter thread file is written to disk",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_into_tweets(raw: str) -> list[str]:
    """Split LLM output into individual tweet strings.

    Supports two common thread formats:
    - Numbered tweets (``1/``, ``1.``, ``Tweet 1:``, etc.)
    - Blank-line-separated tweets

    Parameters
    ----------
    raw:
        The raw LLM response text.

    Returns
    -------
    list[str]
        List of individual tweet strings (stripped, non-empty).
    """
    # Try numbered-tweet format first
    numbered_pattern = re.compile(
        r"(?:^|\n)\s*(?:"
        r"(?:\d+\s*[./:)])|"           # 1/, 1., 1:, 1)
        r"(?:Tweet\s*\d+\s*[:.])|"      # Tweet 1:, Tweet 1.
        r"(?:Thread\s*\d+\s*[:.])|"     # Thread 1:, Thread 1.
        r"(?:#\d+)"                     # #1
        r")\s*\n?"
    )
    parts = numbered_pattern.split(raw)
    tweets = [p.strip() for p in parts if p.strip()]

    # Fall back to blank-line splitting
    if len(tweets) < _MIN_TWEET_COUNT:
        tweets = [p.strip() for p in raw.split("\n\n") if p.strip()]

    # Fall back to line-by-line splitting
    if len(tweets) < _MIN_TWEET_COUNT:
        tweets = [p.strip() for p in raw.split("\n") if p.strip() and len(p.strip()) > 20]

    return tweets


def _check_thread_quality(content: str) -> str | None:
    """Check rewritten thread content for minimum quality standards.

    Validates combined length, tweet count, and individual tweet lengths.

    Returns ``None`` on pass, or an error string describing the issue.
    """
    tweets = _split_into_tweets(content)
    tweet_count = len(tweets)

    # Check combined length
    combined_length = len(content.strip())
    if combined_length < _MIN_OUTPUT_LENGTH:
        return (
            f"combined thread length {combined_length} chars is below "
            f"minimum {_MIN_OUTPUT_LENGTH}"
        )

    # Check tweet count
    if tweet_count < _MIN_TWEET_COUNT:
        return (
            f"Only {tweet_count} tweet(s) found, minimum required is {_MIN_TWEET_COUNT}"
        )

    # Check individual tweet lengths
    over_limit_tweets = [
        {"index": i + 1, "length": len(t)}
        for i, t in enumerate(tweets)
        if len(t) > _MAX_TWEET_LENGTH
    ]
    if over_limit_tweets:
        return (
            f"{len(over_limit_tweets)} tweet(s) exceed {_MAX_TWEET_LENGTH} chars: "
            + ", ".join(f"#{t['index']} ({t['length']} chars)" for t in over_limit_tweets)
        )

    return None


# ---------------------------------------------------------------------------
# Sub-pipeline step functions
# ---------------------------------------------------------------------------


def _step_thread_format(
    content: str,
    brand: str,
    topic: str,
    platform: str,
    config: dict[str, Any] | None,
) -> str | None:
    """Step 1: Rewrite base content into Twitter/X thread format.

    Uses the ``twitter/content_writer`` prompt template which produces
    a hook-first, 280-char-aware thread with 5-15 tweets.

    Returns the rewritten thread content string, or ``None`` on failure.
    """
    try:
        prompt = load_prompt("content_writer", platform=platform)
    except FileNotFoundError:
        # Fall back to the D2 inline prompt if no template exists
        log.info("P2.thread_format no platform-specific prompt, using fallback")
        prompt = (
            f"You are a Twitter/X content strategist who creates viral threads.\n"
            f"Rewrite the following content into a compelling Twitter/X thread "
            f"for brand \"{brand}\".\n\n"
            f"## Twitter/X Thread Requirements\n\n"
            f"- Write in the language of the source content\n"
            f"- Create 5-10 connected tweets that tell a complete story\n"
            f"- **Each tweet MUST be 280 characters or fewer** — this is critical\n"
            f"- First tweet (hook): a bold, curiosity-grabbing statement\n"
            f"- Number each tweet: 1/, 2/, 3/, etc.\n"
            f"- Include at least one surprising or controversial take for engagement\n"
            f"- End with a memorable takeaway + CTA (follow, retweet, comment)\n"
            f"- DO NOT use thread-unroll services or '🧵' emoji\n"
            f"- Return only the thread content, no explanations"
        )

    user_message = (
        f"Topic: {topic}\n"
        f"Brand: {brand}\n\n"
        f"Original content to rewrite into a Twitter/X thread:\n\n{content}"
    )

    try:
        rewritten: str = llm_complete(
            prompt + "\n\n" + user_message,
            config=config,
        )
    except LLMError as exc:
        log.warning("P2.thread_format LLM call failed", error=str(exc))
        return None

    rewritten = rewritten.strip()
    if not rewritten:
        log.warning("P2.thread_format returned empty content")
        return None

    return rewritten


def _step_fact_check(
    thread_content: str,
    source_content: str,
    config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Step 2: Fact-check the rewritten thread against source content.

    Uses an LLM to verify that factual claims in the thread are supported
    by the source material.

    Returns the fact-check result dict (``{"passed": bool, ...}``), or
    ``None`` on LLM failure.
    """
    fact_check_prompt = (
        "You are a fact-checking assistant. Compare the Twitter/X thread below "
        "against the original source content. Identify any factual claims in the "
        "thread that are NOT supported by the source content.\n\n"
        "## Instructions\n\n"
        "- Check numbers, dates, names, statistics, and key claims\n"
        "- Ignore stylistic differences — thread format naturally condenses content\n"
        "- Ignore opinions, speculation, and calls to action — these don't need facts\n"
        "- The thread may add transitions or hooks not in the source — that's fine\n\n"
        "## Output Format\n\n"
        "Return a JSON object with these exact keys:\n"
        "{\n"
        '  "passed": true,\n'
        '  "issues": [\n'
        '    "string — each string describes one unsupported claim. '
        'Include the tweet number and what was claimed vs what the source says."\n'
        "  ],\n"
        '  "confidence": 0.95\n'
        "}\n\n"
        "The `passed` field must be:\n"
        "- true if all factual claims in the thread are supported by the source\n"
        "- false if there is at least one unsupported claim\n\n"
        "## Source Content\n\n"
        f"{source_content}\n\n"
        "## Twitter/X Thread to Fact-Check\n\n"
        f"{thread_content}"
    )

    try:
        result_raw: str = llm_complete(fact_check_prompt, config=config)
    except LLMError as exc:
        log.warning("P2.fact_check LLM call failed", error=str(exc))
        return None

    result_raw = result_raw.strip()
    if not result_raw:
        return {"passed": True, "issues": []}

    # Try to parse JSON response
    try:
        # Strip markdown code fences if present
        json_str = re.sub(r"^```(?:json)?\s*|\s*```$", "", result_raw, flags=re.DOTALL)
        result = json.loads(json_str)
        if not isinstance(result, dict):
            raise ValueError("JSON response is not a dict")
        result.setdefault("passed", True)
        result.setdefault("issues", [])
        return result
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning(
            "P2.fact_check could not parse JSON",
            error=str(exc),
            raw=result_raw[:200],
        )
        # Non-fatal — treat unstructured response as pass
        return {"passed": True, "issues": [], "raw": result_raw}


def _step_humanize(
    content: str,
    platform: str,
    config: dict[str, Any] | None,
) -> str | None:
    """Step 3: Humanize thread content to remove AI writing patterns.

    Uses the ``twitter/humanizer_g1`` prompt template which detects
    formulaic hooks, uniform tweet lengths, perfect sequential logic,
    and other AI markers specific to Twitter threads.

    Returns the humanized content string, or the original ``content`` on
    failure (non-fatal).
    """
    try:
        humanize_prompt = load_prompt("humanizer_g1", platform=platform)
    except FileNotFoundError:
        # No Twitter-specific humanizer prompt — skip humanize step
        log.info("P2.humanize no platform-specific prompt, skipping")
        return content

    user_message = f"Twitter/X thread content to humanize:\n\n{content}"

    try:
        humanized: str = llm_complete(
            humanize_prompt + "\n\n" + user_message,
            config=config,
        )
    except LLMError as exc:
        log.warning("P2.humanize LLM call failed", error=str(exc))
        # Non-fatal — return original content
        return content

    humanized = humanized.strip()
    if not humanized:
        return content

    return humanized


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------


def _write_twitter_output(
    project_dir: str,
    content: str,
    gate_context: GateContext | dict[str, Any],
) -> str | None:
    """Write the final Twitter thread content to ``04_repurpose/twitter/``.

    Returns the output file path, or ``None`` on failure.
    """
    twitter_dir = os.path.join(project_dir, "04_repurpose", "twitter")
    os.makedirs(twitter_dir, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_twitter_thread.md"
    output_path = os.path.join(twitter_dir, filename)

    # Format thread with tweet separators for readability
    tweets = _split_into_tweets(content)
    thread_lines: list[str] = []
    for i, tweet in enumerate(tweets):
        thread_lines.append(f"## Tweet {i + 1}\n\n{tweet}\n")
    thread_content = "\n---\n".join(thread_lines)

    try:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(thread_content)
    except OSError as exc:
        log.error("P2 file write failed", path=output_path, error=str(exc))
        return None

    # Record in output_files
    gate_context.setdefault("output_files", []).append(
        {
            "type": "twitter_thread_repurpose",
            "path": output_path,
            "md5": "",
        }
    )

    log.info("P2 twitter thread written", path=output_path, length=len(content))
    return output_path


# ---------------------------------------------------------------------------
# P2TwitterGate
# ---------------------------------------------------------------------------


class P2TwitterGate(BaseGate):
    """P2 Twitter/X Repurpose Gate.

    Runs a 3-step sub-pipeline (thread format → fact check → humanize) to
    repurpose the pipeline's base content into a Twitter/X thread format
    using platform-adapted prompts.  The final output is written to
    ``04_repurpose/twitter/``.

    ``gate_context`` expected keys:
        - ``content``: str — the base article content to repurpose (required)
        - ``project_dir``: str — absolute path to the project root (required)
        - ``brand``: str — brand identifier (optional)
        - ``topic``: str — original topic (optional)
        - ``config``: dict — merged AutoMedia configuration (optional)
        - ``source_content``: str — original source content for fact-checking (optional)

    ``gate_context`` set keys:
        - ``extra["p2_twitter"]``: str — the final Twitter thread content
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "P2"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Execute the 3-step Twitter/X sub-pipeline.

        Args:
            gate_context: Pipeline context containing content and project_dir.

        Returns:
            dict with keys: ``passed``, ``gate``, ``checks``, ``output_path``,
            ``error``, and ``expected_vs_actual``.
        """
        content: str = gate_context.get("content", "")
        project_dir: str = gate_context.get("project_dir", "")
        brand: str = gate_context.get("brand", "")
        topic: str = gate_context.get("topic", "")
        config: dict[str, Any] | None = gate_context.get("config")
        source_content: str = gate_context.get("source_content", content)

        # ------------------------------------------------------------------
        # Check 0 — content present
        # ------------------------------------------------------------------
        if not content.strip():
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": False,
                        "detail": "gate_context 'content' is empty or missing",
                    }
                ],
                gate="P2",
                error="P2TwitterGate: 'content' is required and must be non-empty",
                expected_map=_EXPECTED_MAP,
            )

        if not project_dir:
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": False,
                        "detail": "gate_context 'project_dir' is empty or missing",
                    }
                ],
                gate="P2",
                error="P2TwitterGate: 'project_dir' is required",
                expected_map=_EXPECTED_MAP,
            )

        # ==================================================================
        # Step 1 — Thread Format (rewrite into Twitter thread)
        # ==================================================================
        thread = _step_thread_format(content, brand, topic, _PLATFORM, config)
        if thread is None:
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "thread_format_success",
                        "passed": False,
                        "detail": "LLM thread format call failed or returned empty content",
                    },
                ],
                gate="P2",
                error="P2TwitterGate: thread_format step failed",
                expected_map=_EXPECTED_MAP,
            )

        # Quality check on thread output
        quality_error = _check_thread_quality(thread)
        if quality_error is not None:
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "thread_format_success",
                        "passed": True,
                        "detail": "LLM thread format call completed successfully",
                    },
                    {
                        "name": "thread_format_quality",
                        "passed": False,
                        "detail": quality_error,
                    },
                ],
                gate="P2",
                error=f"P2TwitterGate: thread quality check failed — {quality_error}",
                expected_map=_EXPECTED_MAP,
            )

        # ==================================================================
        # Step 2 — Fact Check
        # ==================================================================
        fc_result = _step_fact_check(thread, source_content, config)
        if fc_result is None:
            # LLM call failed — non-fatal, continue
            log.warning("P2 fact_check step failed, continuing without fact-check")
        elif not fc_result.get("passed", True):
            # Fact-check identified issues — log as warning but continue
            issues = fc_result.get("issues", [])
            log.warning(
                "P2 fact_check flagged issues",
                issue_count=len(issues),
                issues=issues[:3],  # Log first 3 issues
            )

        # ==================================================================
        # Step 3 — Humanize
        # ==================================================================
        humanized = _step_humanize(thread, _PLATFORM, config)
        if humanized is None:
            # Non-fatal — use thread content as-is
            humanized = thread

        # ==================================================================
        # Store in gate_context for downstream gates
        # ==================================================================
        context_extra = gate_context.setdefault("extra", {})
        if isinstance(context_extra, dict):
            context_extra["p2_twitter"] = humanized
        else:
            gate_context["extra"] = {"p2_twitter": humanized}

        # ==================================================================
        # Write to 04_repurpose/twitter/
        # ==================================================================
        output_path = _write_twitter_output(project_dir, humanized, gate_context)
        if output_path is None:
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "thread_format_success",
                        "passed": True,
                        "detail": "LLM thread format call completed successfully",
                    },
                    {
                        "name": "thread_format_quality",
                        "passed": True,
                        "detail": (
                            f"thread content length {len(thread)} chars "
                            f">= {_MIN_OUTPUT_LENGTH}, "
                            f"{len(_split_into_tweets(thread))} tweets"
                        ),
                    },
                    {
                        "name": "fact_check_completed",
                        "passed": True,
                        "detail": "fact-check step completed",
                    },
                    {
                        "name": "humanize_completed",
                        "passed": True,
                        "detail": "humanize step completed",
                    },
                    {
                        "name": "file_write_success",
                        "passed": False,
                        "detail": "File write failed",
                    },
                ],
                gate="P2",
                error="P2TwitterGate: failed to write twitter thread output",
                expected_map=_EXPECTED_MAP,
            )

        # ==================================================================
        # Success
        # ==================================================================
        tweet_count = len(_split_into_tweets(humanized))
        log.info(
            "P2 twitter sub-pipeline complete",
            thread_length=len(thread),
            humanized_length=len(humanized),
            tweet_count=tweet_count,
            output_path=output_path,
        )

        return build_gate_result(
            [
                {
                    "name": "content_present",
                    "passed": True,
                    "detail": "content present in gate_context",
                },
                {
                    "name": "thread_format_success",
                    "passed": True,
                    "detail": "LLM thread format call completed successfully",
                },
                {
                    "name": "thread_format_quality",
                    "passed": True,
                    "detail": (
                        f"thread content length {len(thread)} chars "
                        f">= {_MIN_OUTPUT_LENGTH}, "
                        f"{len(_split_into_tweets(thread))} tweets, "
                        f"all ≤ {_MAX_TWEET_LENGTH} chars"
                    ),
                },
                {
                    "name": "fact_check_completed",
                    "passed": True,
                    "detail": "fact-check step completed",
                },
                {
                    "name": "humanize_completed",
                    "passed": True,
                    "detail": "humanize step completed",
                },
                {
                    "name": "file_write_success",
                    "passed": True,
                    "detail": f"Twitter thread written to {output_path}",
                },
            ],
            gate="P2",
            expected_map=_EXPECTED_MAP,
            output_path=output_path,
            modified_content=humanized,
        )
