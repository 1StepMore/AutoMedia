"""``research_topics`` persists its findings into the default pool (reinforcement task 2).

Contract: after the LLM returns a :class:`TopicResearchOutput`, ``research_topics``
inserts every returned topic into the default pool DB (``default_pool_path()``,
the cwd-relative ``.automedia/pool.db``) — deduplicated by the topic's ``title``
field via :class:`TopicDeduplicator` — and reports how many rows were actually
inserted as a new ``"persisted"`` payload key.  The pre-existing keys
(``success``, ``topics``, ``category``, ``total_found``) are unchanged.

Hermeticity: every test chdirs into ``tmp_path`` and monkeypatches the cached
MCP allowlist so the temp pool is the only pool in play.  The real repo
``.automedia/`` and the user ``~/.automedia/`` are never touched; the LLM is
always mocked (the suite's network guard blocks real provider calls).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from automedia.core.llm_client import LLMError
from automedia.decision.pydantic import TopicResearchOutput
from automedia.mcp.allowlist import _reset_allowlist_cache
from automedia.mcp.tools import research_topics
from automedia.pool.db import PoolDB, default_pool_path

# Three distinct titles, all far below TopicDeduplicator's 0.75 similarity
# threshold so each is inserted exactly once.
_TOPICS: list[dict[str, object]] = [
    {
        "title": "Running Llama 3 on a Raspberry Pi: Can local AI work at the edge?",
        "category": "AI Tools",
        "angle": "Benchmark quantized models on an $80 device.",
        "confidence_score": 0.88,
        "rationale": "Edge inference is spiking and no benchmark exists.",
        "suggested_format": "tutorial",
        "estimated_search_volume": "growing",
    },
    {
        "title": "Beyond ChatGPT: 7 open-source alternatives that run on your laptop",
        "category": "AI Tools",
        "angle": "Offline-capable open-source models with setup requirements.",
        "confidence_score": 0.82,
        "rationale": "Steady demand for open-source LLM comparisons.",
        "suggested_format": "comparison",
        "estimated_search_volume": "high",
    },
    {
        "title": "The hidden cost of AI APIs: How token pricing eats your margin",
        "category": "AI Tools",
        "angle": "The pricing math and API vs self-hosted TCO.",
        "confidence_score": 0.75,
        "rationale": "Acute, underserved developer pain point.",
        "suggested_format": "article",
        "estimated_search_volume": "medium",
    },
]


def _llm_output(topics: list[dict[str, object]]) -> TopicResearchOutput:
    return TopicResearchOutput(
        topics=topics,
        category="AI Tools",
        total_found=len(topics),
    )


@pytest.fixture(autouse=True)
def _hermetic_cwd_and_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run with cwd == tmp_path and an allowlist containing exactly tmp_path.

    Mirrors ``test_topic_pool_persistence.py``: the MCP allowlist is cached
    process-wide, so it is reset and repopulated around each test.  This keeps
    the default pool under ``tmp_path`` and out of the real repo ``.automedia/``.
    """
    monkeypatch.chdir(tmp_path)
    _reset_allowlist_cache()
    import automedia.mcp.server as _server_mod

    _server_mod._cached_allowlist = [str(tmp_path.resolve())]  # type: ignore[attr-defined]  # private cache poked to allowlist tmp_path (repo pattern)
    yield tmp_path
    _reset_allowlist_cache()


def _pool_titles() -> list[str]:
    with PoolDB(default_pool_path()) as db:
        return [str(t["title"]) for t in db.list_topics()]


class TestResearchTopicsPersists:
    """Successful research writes every returned topic into the default pool."""

    def test_three_researched_topics_become_three_pool_rows(self, tmp_path: Path) -> None:
        # Given: a mocked LLM returning three distinct topics
        output = _llm_output(_TOPICS)

        # When: research_topics runs (Tavily skipped via explicit trending_data)
        with patch("automedia.core.llm_client.llm_complete_structured_safe", return_value=output):
            result = research_topics(category="AI Tools", count=3, trending_data="seed")

        # Then: the payload keeps its existing keys and reports the insert count
        assert result["success"] is True
        assert result["topics"] == _TOPICS
        assert result["category"] == "AI Tools"
        assert result["total_found"] == 3
        assert result["persisted"] == 3

        # And: the default pool holds exactly the returned titles, in order
        assert _pool_titles() == [t["title"] for t in _TOPICS]

        # And: the pool resolves to a real on-disk database under tmp_path
        assert (tmp_path / ".automedia" / "pool.db").is_file()

    def test_second_call_with_the_same_topics_persists_zero(self) -> None:
        # Given: the same mocked research already persisted once
        output = _llm_output(_TOPICS)
        with patch("automedia.core.llm_client.llm_complete_structured_safe", return_value=output):
            first = research_topics(category="AI Tools", count=3, trending_data="seed")

            # When: the exact same research runs again
            second = research_topics(category="AI Tools", count=3, trending_data="seed")

        # Then: both calls succeed but the second inserts nothing new
        assert first["persisted"] == 3
        assert second["persisted"] == 0
        assert len(_pool_titles()) == 3

    def test_duplicate_titles_within_one_response_are_deduped(self) -> None:
        # Given: an LLM response containing the same title twice plus one new one
        duplicate = dict(_TOPICS[0])
        output = _llm_output([_TOPICS[0], duplicate, _TOPICS[1]])

        # When: research_topics persists the batch
        with patch("automedia.core.llm_client.llm_complete_structured_safe", return_value=output):
            result = research_topics(category="AI Tools", count=3, trending_data="seed")

        # Then: only the two distinct titles are inserted
        assert result["persisted"] == 2
        assert _pool_titles() == [str(_TOPICS[0]["title"]), str(_TOPICS[1]["title"])]

    def test_existing_pool_topic_is_not_duplicated(self) -> None:
        # Given: a topic already in the default pool
        with PoolDB(default_pool_path()) as db:
            db.add_topic({"title": str(_TOPICS[0]["title"]), "category": "AI Tools"})

        # When: research returns that same title alongside a fresh one
        output = _llm_output([_TOPICS[0], _TOPICS[2]])
        with patch("automedia.core.llm_client.llm_complete_structured_safe", return_value=output):
            result = research_topics(category="AI Tools", count=2, trending_data="seed")

        # Then: only the fresh title is inserted
        assert result["persisted"] == 1
        assert _pool_titles() == [str(_TOPICS[0]["title"]), str(_TOPICS[2]["title"])]


class TestResearchTopicsErrorPathsDoNotPersist:
    """A failed research call must not write anything into the pool."""

    def test_llm_error_returns_error_and_persists_nothing(self, tmp_path: Path) -> None:
        # Given: the LLM raises a provider error
        with patch(
            "automedia.core.llm_client.llm_complete_structured_safe",
            side_effect=LLMError("provider unavailable"),
        ):
            # When: research_topics runs
            result = research_topics(category="AI Tools", count=3, trending_data="seed")

        # Then: the error payload is unchanged and no pool row was written
        assert result["success"] is False
        assert result["error"]["code"] == "LLM_ERROR"
        assert result["topics"] == []
        assert result["total_found"] == 0
        assert not (tmp_path / ".automedia" / "pool.db").exists()
