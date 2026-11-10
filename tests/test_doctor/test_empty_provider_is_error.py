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


def _write_model_config(directory: Any, *, provider: str) -> None:
    """Write an isolated model_config.yaml with one text_generation slot."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "model_config.yaml").write_text(
        "llm:\n"
        "  text_generation:\n"
        f"    provider: '{provider}'\n"
        "    model: deepseek-chat\n"
        "    api_key: ''\n",
        encoding="utf-8",
    )


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
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The doctor verdict (``llm_api``) fails, not just the chain helper."""
        _write_model_config(tmp_path, provider="")
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(
            "automedia.core.config_loader.load_config",
            lambda *args, **kwargs: _config(provider=""),
        )
        installed, status = Doctor._check_llm_api()
        assert installed is False
        assert _EMPTY_PROVIDER_HINT in (status or "")
        assert "model_config.yaml" in (status or "")

    def test_file_layer_empty_provider_reported_when_env_masks_it(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#467: env-layer provider rescue must not mask the file corruption.

        The #446 failure mode: the resolved config carries a healthy provider
        from ``AUTOMEDIA_LLM_*``, the live probe fails on the missing key, and
        the reported error says nothing about the blank provider in the file.
        The file-layer probe names it.
        """
        _write_model_config(tmp_path, provider="")
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("AUTOMEDIA_LLM_PROVIDER", "GLM")
        monkeypatch.setattr(
            "automedia.core.config_loader.load_config",
            lambda *args, **kwargs: _config(provider="GLM"),
        )
        installed, status = Doctor._check_llm_api()
        assert installed is False
        assert _EMPTY_PROVIDER_HINT in (status or "")
        assert str(tmp_path) in (status or "")

    def test_healthy_file_layer_is_not_reported(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real provider in the file layer must not raise a false alarm."""
        _write_model_config(tmp_path, provider="glm")
        monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(
            "automedia.core.config_loader.load_config",
            lambda *args, **kwargs: _config(provider="glm", api_key="sk-x"),
        )
        monkeypatch.setattr("automedia.core.llm_client._is_fake_mode", lambda *a, **k: True)
        installed, status = Doctor._check_llm_api()
        assert installed is False
        assert "fake LLM mode active" in (status or "")
        assert _EMPTY_PROVIDER_HINT not in (status or "")
