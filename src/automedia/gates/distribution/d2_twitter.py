"""D2 Twitter/X Distribution Gate — rewrites base content into a Twitter/X thread.

This gate reads the pipeline content, rewrites it as a Twitter/X thread
(5-10 tweets, each ≤ 280 characters), performs a single quality check
(each tweet ≤ 280 chars, at least 3 tweets), stores the result in
``gate_context.extra["d2_output"]``, and writes it to
``04_distribution/twitter/`` in the project directory.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

from structlog import get_logger

from automedia.core.llm_client import LLMError, llm_complete
from automedia.gates._context import GateContext
from automedia.gates._result import build_gate_result
from automedia.gates.base import BaseGate

log = get_logger(__name__)

_MIN_TWEET_COUNT: int = 3
"""Minimum acceptable number of tweets in the thread."""

_MAX_TWEET_LENGTH: int = 280
"""Maximum character length for each individual tweet."""

_EXPECTED_MAP: dict[str, str] = {
    "content_present": "Content is provided in gate_context",
    "llm_success": "LLM call completes without error",
    "tweet_quality": (
        f"At least {_MIN_TWEET_COUNT} tweets, each ≤ {_MAX_TWEET_LENGTH} chars"
    ),
    "file_write_success": "Twitter thread file is written to disk",
}


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
    # Try numbered-tweet format first: "1/", "1.", "Tweet 1:", "#1", etc.
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

    # If split didn't yield enough tweets, fall back to blank-line splitting
    if len(tweets) < _MIN_TWEET_COUNT:
        tweets = [p.strip() for p in raw.split("\n\n") if p.strip()]

    # If still insufficient, treat as single-tweet-per-line
    if len(tweets) < _MIN_TWEET_COUNT:
        tweets = [p.strip() for p in raw.split("\n") if p.strip() and len(p.strip()) > 20]

    return tweets


def _render_twitter_prompt(content: str, brand: str, title: str) -> str:
    """Build the Twitter/X thread rewrite prompt.

    Parameters
    ----------
    content:
        The source content to rewrite into a thread.
    brand:
        Brand identifier for brand-aligned messaging.
    title:
        The article title (optional, may be empty).

    Returns
    -------
    str
        The rendered prompt string.
    """
    title_hint = f" (adapted from: \"{title}\")" if title else ""

    return (
        f"You are a Twitter/X content strategist who creates viral threads.\n"
        f"Rewrite the following content into a compelling Twitter/X thread{title_hint} "
        f"for brand \"{brand}\".\n\n"
        f"## Twitter/X Thread Requirements\n\n"
        f"- Write in the language of the source content\n"
        f"- Create 5-10 connected tweets that tell a complete story\n"
        f"- **Each tweet MUST be 280 characters or fewer** — this is critical\n"
        f"- First tweet (hook): a bold, curiosity-grabbing statement\n"
        f"- Each subsequent tweet earns the next tap — build narrative momentum\n"
        f"- Vary tweet length: mix punchy one-liners with slightly longer tweets\n"
        f"- Use line breaks within tweets for visual punch (sparingly)\n"
        f"- Number each tweet: 1/, 2/, 3/, etc.\n"
        f"- Include at least one surprising or controversial take for engagement\n"
        f"- End with a memorable takeaway + CTA (follow, retweet, comment)\n"
        f"- DO NOT use thread-unroll services or '🧵' emoji\n"
        f"- DO NOT include placeholder text or meta-commentary\n"
        f"- Return only the thread content, no explanations\n\n"
        f"## Source Content\n\n"
        f"{content}"
    )


# ---------------------------------------------------------------------------
# D2Gate
# ---------------------------------------------------------------------------


class D2Gate(BaseGate):
    """D2 Twitter/X Distribution Gate.

    Rewrites the pipeline's base content into a Twitter/X thread format
    using an LLM, validates tweet count and individual tweet length, and
    persists the result to disk.

    ``gate_context`` expected keys:
        - ``content``: str — the base article content to rewrite (required)
        - ``project_dir``: str — absolute path to the project root (required)
        - ``brand``: str — brand identifier (optional)
        - ``title``: str — original article title (optional)
        - ``config``: dict — merged AutoMedia configuration (optional)

    ``gate_context`` set keys:
        - ``extra["d2_output"]``: list[dict] — list of tweet dicts with
          ``index`` and ``text`` keys
        - ``output_files``: list[dict] — appended entry for the written file
    """

    _gate_name = "D2"
    _failure_mode = "retry"

    def execute(self, gate_context: GateContext | dict[str, Any]) -> dict[str, Any]:
        """Rewrite content into a Twitter/X thread format.

        Args:
            gate_context: Pipeline context containing content and project_dir.

        Returns:
            dict with keys: ``passed``, ``gate``, ``checks``, ``output_path``,
            ``error``, and ``expected_vs_actual``.
        """
        content: str = gate_context.get("content", "")
        project_dir: str = gate_context.get("project_dir", "")
        brand: str = gate_context.get("brand", "")
        title: str = gate_context.get("title", "")
        config: dict[str, Any] | None = gate_context.get("config")

        # ------------------------------------------------------------------
        # Check 1 — content present
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
                gate="D2",
                error="D2Gate: 'content' is required and must be non-empty",
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Build LLM prompt
        # ------------------------------------------------------------------
        prompt = _render_twitter_prompt(content, brand, title)

        # ------------------------------------------------------------------
        # Check 2 — LLM call
        # ------------------------------------------------------------------
        try:
            rewritten: str = llm_complete(prompt, config=config)
        except LLMError as exc:
            log.warning("D2 LLM call failed", error=str(exc))
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "llm_success",
                        "passed": False,
                        "detail": f"LLM call failed: {exc}",
                    },
                ],
                gate="D2",
                error=f"D2Gate: LLM rewrite failed — {exc}",
                expected_map=_EXPECTED_MAP,
            )

        rewritten = rewritten.strip()

        # ------------------------------------------------------------------
        # Check 3 — tweet quality gate
        # ------------------------------------------------------------------
        tweets = _split_into_tweets(rewritten)
        tweet_count = len(tweets)

        # Validate individual tweet lengths
        over_limit_tweets = [
            {"index": i + 1, "length": len(t)}
            for i, t in enumerate(tweets)
            if len(t) > _MAX_TWEET_LENGTH
        ]
        tweet_quality_failures: list[str] = []
        if tweet_count < _MIN_TWEET_COUNT:
            tweet_quality_failures.append(
                f"Only {tweet_count} tweet(s) found, minimum required is {_MIN_TWEET_COUNT}"
            )
        if over_limit_tweets:
            tweet_quality_failures.append(
                f"{len(over_limit_tweets)} tweet(s) exceed {_MAX_TWEET_LENGTH} chars: "
                + ", ".join(f"#{t['index']} ({t['length']} chars)" for t in over_limit_tweets)
            )

        if tweet_quality_failures:
            log.warning(
                "D2 tweet quality check failed",
                tweet_count=tweet_count,
                over_limit=len(over_limit_tweets),
                failures=tweet_quality_failures,
            )
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "llm_success",
                        "passed": True,
                        "detail": "LLM call completed successfully",
                    },
                    {
                        "name": "tweet_quality",
                        "passed": False,
                        "detail": "; ".join(tweet_quality_failures),
                    },
                ],
                gate="D2",
                error=(
                    f"D2Gate: Twitter thread quality check failed — "
                    f"{'; '.join(tweet_quality_failures)}"
                ),
                expected_map=_EXPECTED_MAP,
            )

        # ------------------------------------------------------------------
        # Build structured thread output
        # ------------------------------------------------------------------
        thread = [
            {"index": i + 1, "text": t}
            for i, t in enumerate(tweets)
        ]

        # Store in gate_context for downstream gates
        context_extra = gate_context.setdefault("extra", {})
        if isinstance(context_extra, dict):
            context_extra["d2_output"] = thread
        else:
            gate_context["extra"] = {"d2_output": thread}

        # ------------------------------------------------------------------
        # Write to 04_distribution/twitter/
        # ------------------------------------------------------------------
        twitter_dir = os.path.join(project_dir, "04_distribution", "twitter")
        os.makedirs(twitter_dir, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_twitter_thread.md"
        output_path = os.path.join(twitter_dir, filename)

        # Write thread as markdown with tweet separator lines
        thread_lines: list[str] = []
        for tweet in thread:
            thread_lines.append(f"## Tweet {tweet['index']}\n\n{tweet['text']}\n")
        thread_content = "\n---\n".join(thread_lines)

        try:
            with open(output_path, "w", encoding="utf-8") as fh:
                fh.write(thread_content)
        except OSError as exc:
            log.error("D2 file write failed", path=output_path, error=str(exc))
            return build_gate_result(
                [
                    {
                        "name": "content_present",
                        "passed": True,
                        "detail": "content present in gate_context",
                    },
                    {
                        "name": "llm_success",
                        "passed": True,
                        "detail": "LLM call completed successfully",
                    },
                    {
                        "name": "tweet_quality",
                        "passed": True,
                        "detail": (
                            f"{tweet_count} tweets, all ≤ {_MAX_TWEET_LENGTH} chars"
                        ),
                    },
                    {
                        "name": "file_write_success",
                        "passed": False,
                        "detail": f"File write failed: {exc}",
                    },
                ],
                gate="D2",
                error=f"D2Gate: failed to write Twitter thread — {exc}",
                expected_map=_EXPECTED_MAP,
            )

        # Record in output_files
        gate_context.setdefault("output_files", []).append(
            {
                "type": "twitter_thread",
                "path": output_path,
                "md5": "",
            }
        )

        log.info(
            "D2 Twitter thread rewrite complete",
            tweet_count=tweet_count,
            output_path=output_path,
        )

        # ------------------------------------------------------------------
        # Success
        # ------------------------------------------------------------------
        return build_gate_result(
            [
                {
                    "name": "content_present",
                    "passed": True,
                    "detail": "content present in gate_context",
                },
                {
                    "name": "llm_success",
                    "passed": True,
                    "detail": "LLM call completed successfully",
                },
                {
                    "name": "tweet_quality",
                    "passed": True,
                    "detail": (
                        f"{tweet_count} tweets, all ≤ {_MAX_TWEET_LENGTH} chars"
                    ),
                },
                {
                    "name": "file_write_success",
                    "passed": True,
                    "detail": f"Twitter thread written to {output_path}",
                },
            ],
            gate="D2",
            expected_map=_EXPECTED_MAP,
            output_path=output_path,
            modified_content=rewritten,
        )
