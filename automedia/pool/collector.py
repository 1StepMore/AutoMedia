"""HotCollector — three-layer funnel hot topic collection.

Layer 1: Simulated platform hot-search APIs (Weibo, Zhihu, Douyin, Bilibili).
Layer 2: Tavily AI search on extracted keywords.
Layer 3: AIHOT aggregator feed.

All data is synthetic — zero real API calls.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


class HotCollector:
    """Collect hot topics from multiple simulated sources via a 3-layer funnel.

    Parameters
    ----------
    seed_topics : list[dict] | None
        Optional pre-seeded topics to include.  Each dict must have at least
        ``source``, ``title``, ``url``, ``heat_score``.  When *None* a default
        synthetic dataset is produced.
    """

    def __init__(self, seed_topics: list[dict] | None = None) -> None:
        self._seed_topics = seed_topics or []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_all(self) -> list[dict]:
        """Run the full three-layer funnel and return deduplicated topics.

        Returns
        -------
        list[dict]
            Each item has keys: ``source``, ``title``, ``url``,
            ``heat_score`` (float 0-10), ``collected_at`` (ISO-8601).
        """
        # Layer 1 — platform hot-search APIs
        layer1: list[dict] = []
        layer1.extend(self._collect_weibo())
        layer1.extend(self._collect_zhihu())
        layer1.extend(self._collect_douyin())
        layer1.extend(self._collect_bilibili())

        # Layer 2 — Tavily AI search on keywords extracted from layer-1 titles
        keywords = self._extract_keywords(layer1)
        layer2 = self._search_tavily(keywords)

        # Layer 3 — AIHOT aggregator
        layer3 = self._fetch_aihot()

        # Merge all layers + seed topics
        all_topics = layer1 + layer2 + layer3 + self._seed_topics

        # Simple title-based dedup (preserve order, keep first occurrence)
        seen_titles: set[str] = set()
        unique: list[dict] = []
        for t in all_topics:
            normalized = t["title"].strip().lower()
            if normalized not in seen_titles:
                seen_titles.add(normalized)
                unique.append(t)

        return unique

    def ingest_file(self, file_path: str) -> "ExtractionResult | None":
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
            ".docx", ".pptx", ".pdf", ".xlsx", ".csv",
            ".json", ".xml", ".html", ".epub", ".eml", ".msg",
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
    # Layer 1 — platform hot-search APIs (simulated)
    # ------------------------------------------------------------------

    def _collect_weibo(self) -> list[dict]:
        """Simulate Weibo hot-search API."""
        now = _now_iso()
        return [
            {"source": "weibo", "title": "AI视频生成技术突破",
             "url": "https://weibo.com/hot/ai-video", "heat_score": 9.2, "collected_at": now},
            {"source": "weibo", "title": "大模型降价潮来袭",
             "url": "https://weibo.com/hot/llm-price", "heat_score": 8.5, "collected_at": now},
            {"source": "weibo", "title": "自媒体创作者工具更新",
             "url": "https://weibo.com/hot/creator-tools", "heat_score": 7.8, "collected_at": now},
        ]

    def _collect_zhihu(self) -> list[dict]:
        """Simulate Zhihu hot-search API."""
        now = _now_iso()
        return [
            {"source": "zhihu", "title": "人工智能如何改变教育",
             "url": "https://zhihu.com/hot/ai-edu", "heat_score": 8.0, "collected_at": now},
            {"source": "zhihu", "title": "AIGC内容创作指南",
             "url": "https://zhihu.com/hot/aigc-guide", "heat_score": 8.8, "collected_at": now},
            {"source": "zhihu", "title": "芯片行业最新动态",
             "url": "https://zhihu.com/hot/chip-news", "heat_score": 6.5, "collected_at": now},
        ]

    def _collect_douyin(self) -> list[dict]:
        """Simulate Douyin hot-search API."""
        now = _now_iso()
        return [
            {"source": "douyin", "title": "AI绘画爆款教程",
             "url": "https://douyin.com/hot/ai-paint", "heat_score": 9.0, "collected_at": now},
            {"source": "douyin", "title": "科技博主推荐的AI工具",
             "url": "https://douyin.com/hot/ai-tools", "heat_score": 7.5, "collected_at": now},
            {"source": "douyin", "title": "互联网大厂裁员最新消息",
             "url": "https://douyin.com/hot/layoff", "heat_score": 6.0, "collected_at": now},
        ]

    def _collect_bilibili(self) -> list[dict]:
        """Simulate Bilibili hot-search API."""
        now = _now_iso()
        return [
            {"source": "bilibili", "title": "Sora最新视频效果展示",
             "url": "https://bilibili.com/hot/sora", "heat_score": 9.5, "collected_at": now},
            {"source": "bilibili", "title": "大模型应用开发实战",
             "url": "https://bilibili.com/hot/llm-dev", "heat_score": 8.2, "collected_at": now},
            {"source": "bilibili", "title": "体育赛事精彩集锦",
             "url": "https://bilibili.com/hot/sports", "heat_score": 5.0, "collected_at": now},
        ]

    # ------------------------------------------------------------------
    # Layer 2 — Tavily AI search (simulated)
    # ------------------------------------------------------------------

    def _search_tavily(self, keywords: list[str]) -> list[dict]:
        """Simulate Tavily AI search based on extracted keywords.

        Returns synthetic results that match the keyword theme.
        """
        now = _now_iso()
        # Simulate keyword-driven results
        results: list[dict] = []
        keyword_set = {k.lower() for k in keywords}

        if any(k in keyword_set for k in ("ai", "人工智能", "大模型")):
            results.append({
                "source": "tavily",
                "title": "OpenAI发布最新AI研究成果",
                "url": "https://tavily.com/search/openai-research",
                "heat_score": 8.7,
                "collected_at": now,
            })
        if any(k in keyword_set for k in ("视频", "sora", "ai视频")):
            results.append({
                "source": "tavily",
                "title": "AI视频工具对比评测2025",
                "url": "https://tavily.com/search/ai-video-tools",
                "heat_score": 8.3,
                "collected_at": now,
            })
        if any(k in keyword_set for k in ("自媒体", "创作", "工具")):
            results.append({
                "source": "tavily",
                "title": "自媒体运营效率提升方案",
                "url": "https://tavily.com/search/content-efficiency",
                "heat_score": 7.6,
                "collected_at": now,
            })
        return results

    # ------------------------------------------------------------------
    # Layer 3 — AIHOT aggregator (simulated)
    # ------------------------------------------------------------------

    def _fetch_aihot(self) -> list[dict]:
        """Simulate AIHOT aggregator feed."""
        now = _now_iso()
        return [
            {"source": "aihot", "title": "全球AI创业融资周报",
             "url": "https://aihot.com/funding-weekly", "heat_score": 7.0, "collected_at": now},
            {"source": "aihot", "title": "AGI技术路线最新争论",
             "url": "https://aihot.com/agi-debate", "heat_score": 8.9, "collected_at": now},
        ]

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
            for word in title:
                # Keep Chinese characters and English letters as tokens
                pass
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
    return datetime.now(timezone.utc).isoformat()


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
