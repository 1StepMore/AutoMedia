"""HF endpoint resolution — issue #512.

``ensure_hf_endpoint`` must settle ``HF_ENDPOINT`` before
``huggingface_hub``/``faster_whisper`` is first imported in the process:
the hub endpoint is baked into ``huggingface_hub.constants`` at import
time, so a later env change would not affect a download. Priority: config
key ``hf_endpoint`` > an already-set ``HF_ENDPOINT`` > the hf-mirror
default (#512, owner decision; a local cache hit needs no network either
way).
"""

from __future__ import annotations

import pytest

from automedia.engines.implementations._hf_endpoint import (
    DEFAULT_HF_ENDPOINT,
    ensure_hf_endpoint,
)


class TestEnsureHfEndpoint:
    def test_unset_env_gets_mirror_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HF_ENDPOINT", raising=False)
        assert ensure_hf_endpoint(None) == DEFAULT_HF_ENDPOINT
        assert DEFAULT_HF_ENDPOINT == "https://hf-mirror.com"

    def test_existing_env_is_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HF_ENDPOINT", "https://hf.example.org")
        assert ensure_hf_endpoint(None) == "https://hf.example.org"

    def test_config_key_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HF_ENDPOINT", "https://hf.example.org")
        assert (
            ensure_hf_endpoint({"hf_endpoint": "https://cfg.example.org"})
            == "https://cfg.example.org"
        )

    def test_blank_config_key_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HF_ENDPOINT", "https://hf.example.org")
        assert ensure_hf_endpoint({"hf_endpoint": "  "}) == "https://hf.example.org"

    def test_idempotent_when_called_twice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HF_ENDPOINT", raising=False)
        first = ensure_hf_endpoint(None)
        second = ensure_hf_endpoint({"hf_endpoint": "https://cfg.example.org"})
        assert second == "https://cfg.example.org"
        assert first == DEFAULT_HF_ENDPOINT
