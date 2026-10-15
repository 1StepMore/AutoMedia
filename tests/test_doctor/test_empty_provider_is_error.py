"""Empty ``provider`` must be a doctor ERROR, not a silent pass (issue #208).

An automated flow once rewrote a real ``~/.automedia/model_config.yaml``
with ``provider: ''``.  The runtime resolved the blank through the
environment/credential fallback, so ``automedia doctor`` still reported the
LLM API as reachable and the corruption stayed invisible.  ``doctor`` now
fails the ``llm_api`` check when any configured slot declares an empty
provider.
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.core.doctor import Doctor

_EMPTY_PROVIDER_HINT = "provider is empty"


def _config(**text_generation: Any) -> dict[str, Any]:
    """Return a merged-config-shaped dict with one text_generation block."""
    return {"llm": {"text_generation": {"model": "deepseek-chat", **text_generation}}}


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep fake mode and ambient keys out of the probe decisions."""
    monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)
    monkeypatch.delenv("AUTOMEDIA_LLM_API_KEY", raising=False)


class TestEmptyProviderIsError:
    """``_check_llm_chain`` refuses an explicitly blank provider."""

    def test_empty_provider_fails_the_chain_check(self) -> None:
        """``provider: ''`` is reported instead of passing silently."""
        ok, message = Doctor._check_llm_chain(_config(provider=""))
        assert ok is False
        assert _EMPTY_PROVIDER_HINT in (message or "")
        assert "text_generation" in (message or "")

    def test_whitespace_provider_fails_the_chain_check(self) -> None:
        """A whitespace-only provider is the same corruption."""
        ok, message = Doctor._check_llm_chain(_config(provider="   "))
        assert ok is False
        assert _EMPTY_PROVIDER_HINT in (message or "")

    def test_missing_provider_key_is_not_reported(self) -> None:
        """An omitted provider key is implied ("openai") at runtime — no error."""
        ok, message = Doctor._check_llm_chain(_config())
        assert ok is True
        assert message is None

    def test_null_provider_is_reported(self) -> None:
        """An explicit ``provider: null`` is the same corruption as ``''``."""
        ok, message = Doctor._check_llm_chain(_config(provider=None))
        assert ok is False
        assert _EMPTY_PROVIDER_HINT in (message or "")

    def test_real_provider_passes(self) -> None:
        """A configured provider still passes the chain check."""
        ok, message = Doctor._check_llm_chain(_config(provider="deepseek", api_key="sk-x"))
        assert ok is True
        assert message is None

    def test_empty_provider_in_a_sibling_slot_fails(self) -> None:
        """Every configured slot is checked, not only text_generation."""
        config = _config(provider="deepseek", api_key="sk-x")
        config["llm"]["vision"] = {"provider": "", "model": "vision-model"}
        ok, message = Doctor._check_llm_chain(config)
        assert ok is False
        assert "vision" in (message or "")

    def test_check_llm_api_reports_the_empty_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The doctor verdict (``llm_api``) fails, not just the chain helper."""
        monkeypatch.setattr(
            "automedia.core.config_loader.load_config",
            lambda *args, **kwargs: _config(provider=""),
        )
        installed, status = Doctor._check_llm_api()
        assert installed is False
        assert _EMPTY_PROVIDER_HINT in (status or "")
