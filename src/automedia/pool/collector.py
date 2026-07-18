"""HotCollector — topic collection funnel.

Layer 2: Tavily AI search on extracted keywords.
Layer 3: AIHOT aggregator feed / LLM-based trending generator.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from structlog import get_logger

log = get_logger(__name__)

if TYPE_CHECKING:
    from automedia.omni.opp_adapter import ExtractionResult

_TAVILY_API_URL = "https://api.tavily.com/search"


class HotCollector:
    """Collect hot topics from real sources.

    Parameters
    ----------
    seed_topics : list[dict] | None
        Optional pre-seeded topics to include.  Each dict must have at least
        ``source``, ``title``, ``url``, ``heat_score``.
    tavily_api_key : str | None
        Tavily Search API key.  Falls back to ``AUTOMEDIA_TAVILY_API_KEY``
        environment variable when *None*.
    """

    def __init__(
        self,
        seed_topics: list[dict] | None = None,
        tavily_api_key: str | None = None,
    ) -> None:
        """Initialize the hot topic collector.

        Args:
            seed_topics: Optional pre-seeded topics to include in the
                collection funnel.
            tavily_api_key: Tavily Search API key. Falls back to env var.
        """
        self._seed_topics = seed_topics or []
        self._tavily_api_key = tavily_api_key or os.environ.get("AUTOMEDIA_TAVILY_API_KEY", "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_all(self) -> list[dict]:
        """Run the collection funnel and return deduplicated topics.

        Returns
        -------
        list[dict]
            Each item has keys: ``source``, ``title``, ``url``,
            ``heat_score`` (float 0-10), ``collected_at`` (ISO-8601).
        """
        # Layer 2 — Tavily AI search on extracted keywords
        keywords = self._extract_keywords(self._seed_topics)
        layer2 = self._search_tavily(keywords)

        # Layer 3 — AIHOT aggregator
        layer3 = self._fetch_aihot()

        # Merge all layers + seed topics
        all_topics = layer2 + layer3 + self._seed_topics

        # Simple title-based dedup (preserve order, keep first occurrence)
        seen_titles: set[str] = set()
        unique: list[dict] = []
        for t in all_topics:
            normalized = t["title"].strip().lower()
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                unique.append(t)

        return unique

    def ingest_file(self, file_path: str) -> ExtractionResult | None:
        """Extract content from a document file via OPPAdapter.

        Supported formats: ``.docx``, ``.pptx``, ``.pdf``, ``.xlsx``,
        ``.csv``, ``.json``, ``.xml``, ``.html``, ``.epub``, ``.eml``,
        ``.msg``.

        Parameters
        ----------
        file_path : str
            Path to the document file to ingest.

        Returns
        -------
        ExtractionResult | None
            The extraction result for supported formats (or on OPP failure),
            or ``None`` for unsupported formats.
        """
        _, ext = os.path.splitext(file_path)
        if ext.lower() not in {
            ".docx",
            ".pptx",
            ".pdf",
            ".xlsx",
            ".csv",
            ".json",
            ".xml",
            ".html",
            ".epub",
            ".eml",
            ".msg",
        }:
            return None

        from automedia.omni.opp_adapter import OPPAdapter

        try:
            adapter = OPPAdapter()
            return adapter.extract(file_path)
        except Exception as exc:
            from automedia.omni.opp_adapter import ExtractionResult

            return ExtractionResult(
                md_content="",
                manifest={"source_file": file_path, "error": str(exc)},
                warnings=[f"Extraction failed: {exc}"],
            )

    # ------------------------------------------------------------------
    # Layer 2 — Tavily AI search
    # ------------------------------------------------------------------

    def _search_tavily(self, keywords: list[str]) -> list[dict]:
        """Search trending topics via Tavily Search API.

        Requires ``AUTOMEDIA_TAVILY_API_KEY`` or *tavily_api_key* to be set.
        Returns an empty list when the API key is not configured or when
        the API call fails.

        Parameters
        ----------
        keywords : list[str]
            Search keywords extracted from seed topics.

        Returns
        -------
        list[dict]
            Each item has keys: ``source``, ``title``, ``url``,
            ``heat_score``, ``collected_at``.
        """
        if not self._tavily_api_key:
            return []
        query = " ".join(keywords[:5]).strip()
        if not query:
            return []

        try:
            import httpx
        except ImportError:
            return []

        now = _now_iso()
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    _TAVILY_API_URL,
                    json={
                        "api_key": self._tavily_api_key,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": 5,
                    },
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
        except Exception:
            return []

        results: list[dict] = []
        for item in data.get("results", []):
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if not title or not url:
                continue
            score = item.get("score", 0.5)
            heat_score = round(min(float(score) * 10, 10.0), 1)
            results.append(
                {
                    "source": "tavily",
                    "title": title,
                    "url": url,
                    "heat_score": heat_score,
                    "collected_at": now,
                }
            )
        return results

    # ------------------------------------------------------------------
    # Layer 3 — AIHOT / LLM-based trending generator
    # ------------------------------------------------------------------

    def _fetch_aihot(self) -> list[dict]:
        """Fetch trending AI / creator-economy topics via LLM.

        Uses the AutoMedia LLM client to generate a list of currently
        trending topics.  Returns an empty list when the LLM is not
        configured or on any failure.
        """
        try:
            from automedia.core.llm_client import llm_complete
        except ImportError:
            return []

        now = _now_iso()
        prompt = (
            "Generate a list of 5 currently trending hot topics in the AI "
            "and creator-economy space. "
            "Return ONLY a JSON array of objects with keys: "
            '"title" (topic title in Chinese or English), '
            '"url" (a relevant news or article URL), '
            'and "heat_score" (float 0-10 indicating popularity).'
        )

        try:
            response = llm_complete(
                prompt=prompt,
                system_prompt=(
                    "You are a trending-topic researcher. "
                    "Return ONLY valid JSON, no markdown, no explanation."
                ),
                temperature=0.7,
                max_tokens=1024,
            )
        except Exception:
            return []

        text = response.strip()
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl + 1 :]
            if text.endswith("```"):
                text = text[:-3].rstrip()

        try:
            items: list[Any] = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(items, list):
            return []

        results: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            results.append(
                {
                    "source": "aihot",
                    "title": title,
                    "url": item.get("url", ""),
                    "heat_score": float(item.get("heat_score", 5.0)),
                    "collected_at": now,
                }
            )
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(topics: list[dict]) -> list[str]:
        """Extract simple keywords from topic titles for Layer 2 search.

        Splits on common delimiters and filters stop-words.
        """
        stop_words = {"的", "了", "在", "是", "和", "与", "如何", "最新", "消息"}
        keywords: list[str] = []
        for t in topics:
            title: str = t.get("title", "")
            # Simple character-level keyword extraction for CJK
            for segment in _split_cjk(title):
                if segment not in stop_words and len(segment) >= 2:
                    keywords.append(segment)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)
        return unique


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _split_cjk(text: str) -> list[str]:
    """Split CJK text into 2-4 character segments and English words."""
    segments: list[str] = []
    buf = ""
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            buf += ch
            if len(buf) >= 4:
                segments.append(buf)
                buf = ""
        else:
            if buf:
                segments.append(buf)
                buf = ""
            if ch.isalpha():
                buf += ch
            else:
                if buf:
                    segments.append(buf)
                    buf = ""
    if buf:
        segments.append(buf)
    # Also add 2-char substrings for better coverage
    two_char: list[str] = []
    for seg in segments:
        if len(seg) >= 2:
            for i in range(len(seg) - 1):
                two_char.append(seg[i : i + 2])
    return segments + two_char
