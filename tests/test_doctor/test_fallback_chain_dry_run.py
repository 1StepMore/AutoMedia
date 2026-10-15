"""Dry-run validation of the LLM fallback chain in ``Doctor`` (issue #206).

A fallback spec that cannot even be constructed used to fail silently: the
chain only surfaced the ``LLMError`` when it actually failed over.  ``doctor``
now builds every spec up front and names the broken one.
"""

from __future__ import annotations

from typing import Any

import pytest

from automedia.core.doctor import Doctor

# A provider guaranteed to resolve to no key: no env var, no model_config
# providers entry, no credential store — mirrors the existing doctor warning
# tests' ``provider-with-no-key-abc`` convention.
_BROKEN_PROVIDER = "provider-with-no-key-zzz"
_BROKEN_PROVIDER_ENV = "AUTOMEDIA_PROVIDER_WITH_NO_KEY_ZZZ"


def _config(
    *,
    primary_key: str = "",
    fallback_provider: str = _BROKEN_PROVIDER,
    fallback_key: str = "",
) -> dict[str, Any]:
    """Return a merged-config-shaped dict with one fallback spec."""
    return {
        "llm": {
            "text_generation": {
                "provider": "primary-provider",
                "model": "primary-model",
                "api_key": primary_key,
                "base_url": "https://primary.test/v1",
                "fallback": [
                    {
                        "provider": fallback_provider,
                        "model": "fallback-model",
                        "base_url": "https://example.invalid/v1",
                        "api_key": fallback_key,
                    }
                ],
            }
        }
    }


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove fake-mode and the broken provider's key from the environment."""
    monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)
    monkeypatch.delenv(_BROKEN_PROVIDER_ENV, raising=False)


class TestCheckLlmChain:
    """``Doctor._check_llm_chain`` builds every fallback spec dry-run."""

    def test_broken_fallback_spec_is_reported(self) -> None:
        """A fallback whose key resolves nowhere fails and names the spec."""
        ok, message = Doctor._check_llm_chain(_config())
        assert ok is False
        assert _BROKEN_PROVIDER in (message or "")
        assert "fallback[1]" in (message or "")
        assert "fallback-model" in (message or "")
        assert "https://example.invalid/v1" in (message or "")

    def test_empty_fallback_key_inherits_primary_and_builds(self) -> None:
        """Regression #206: ``api_key: ''`` is inherited, not wiped.

        With a non-empty primary key the fallback spec now carries it, so the
        spec constructs successfully instead of failing silently.
        """
        ok, message = Doctor._check_llm_chain(_config(primary_key="sk-primary"))
        assert ok is True
        assert message is None

    def test_fallback_with_resolvable_env_key_builds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A fallback key resolved from the environment is accepted."""
        monkeypatch.setenv("AUTOMEDIA_GOODPROVIDER", "sk-good")
        ok, message = Doctor._check_llm_chain(_config(fallback_provider="goodprovider"))
        assert ok is True
        assert message is None

    def test_primary_failure_is_deferred_to_live_probe(self) -> None:
        """The primary is not failed by the dry-run (the live probe owns it)."""
        config = _config(primary_key="")
        # Explicitly no fallback: only a primary that cannot be built.
        config["llm"]["text_generation"].pop("fallback")
        ok, message = Doctor._check_llm_chain(config)
        assert ok is True
        assert message is None


class TestCheckLlmApiReportsBrokenFallback:
    """``_check_llm_api`` must fail, naming the broken fallback."""

    def test_check_llm_api_fails_on_broken_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "automedia.core.config_loader.load_config",
            lambda *args, **kwargs: _config(),
        )
        installed, status = Doctor._check_llm_api()
        assert installed is False
        assert _BROKEN_PROVIDER in (status or "")
        assert "fallback[1]" in (status or "")
