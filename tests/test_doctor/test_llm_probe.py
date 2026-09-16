"""Bounded, non-false-positive LLM probe for ``Doctor._check_llm_api``.

Regression coverage for todo 7 of ``automedia-reinforcement``:

* The probe must bound its total wall-clock time so a blackholing provider
  cannot hang ``automedia doctor``: one request attempt per provider spec,
  each request bounded by the probe timeout.
* Fake-LLM mode must be detected from the *same merged config* the probe uses
  (both ``AUTOMEDIA_FAKE_LLM`` and ``llm.fake_mode``), and must never be
  reported as ``"API reachable"``.

Timing / spy tests request the ``allow_network`` fixture **on purpose**:
``tests/conftest.py`` installs a session-scoped autouse
``_hermetic_network_guard`` that patches ``socket.socket.connect`` to raise
``ConnectionRefusedError`` *instantly* for any non-loopback target.  Without
``allow_network`` the connect to the blackhole address is refused in
microseconds and the elapsed-time assertions would pass vacuously.
``allow_network`` lifts the guard for one test so the connect genuinely blocks
and the configured timeout — not an instant refusal — bounds the call.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import openai
import pytest

from automedia.core import llm_client
from automedia.core.doctor import Doctor
from automedia.core.llm_client import LLMError, llm_complete

# ``10.255.255.1`` is a blackhole (no host answers; SYN packets are dropped),
# verified on this host to block until the socket timeout fires.  A routable
# but closed port would be refused instantly and make the timing vacuous.
_BLACKHOLE_BASE_URL = "http://10.255.255.1:9/v1"
_PROBE_TIMEOUT_S = 15.0
_SINGLE_SPEC_SLACK_S = 5.0
_MULTI_SPEC_SLACK_S = 10.0


def _config(*, specs: int = 1, fake_mode: bool = False) -> dict[str, Any]:
    """Return a merged-config-shaped dict with *specs* provider specs."""
    primary: dict[str, Any] = {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "test-key-not-real",
        "base_url": _BLACKHOLE_BASE_URL,
        "temperature": 0.0,
        "max_tokens": 10,
    }
    text_generation = dict(primary)
    if specs > 1:
        text_generation["fallback"] = [
            {
                "provider": "openai",
                "model": f"gpt-4o-mini-fb{i}",
                "base_url": _BLACKHOLE_BASE_URL,
            }
            for i in range(specs - 1)
        ]
    llm: dict[str, Any] = {"text_generation": text_generation}
    if fake_mode:
        llm["fake_mode"] = True
    return {"llm": llm}


def _patch_load_config(monkeypatch: pytest.MonkeyPatch, config: dict[str, Any]) -> None:
    """Point the probe's merged-config load at *config* (HOME stays untouched)."""
    monkeypatch.setattr(
        "automedia.core.config_loader.load_config",
        lambda *args, **kwargs: config,
    )


class _SpyClient:
    """Minimal OpenAI-client stand-in recording attempts and option calls.

    ``with_options`` records its kwargs and returns ``self`` so the call chain
    (``with_options`` → ``chat.completions.create``) is observed exactly as the
    production code exercises it.
    """

    def __init__(self, attempts: list[dict[str, Any]], option_calls: list[dict[str, Any]]) -> None:
        self._attempts = attempts
        self._option_calls = option_calls

    def with_options(self, **kwargs: object) -> _SpyClient:
        self._option_calls.append(dict(kwargs))
        return self

    @property
    def chat(self) -> _SpyClient:
        return self

    @property
    def completions(self) -> _SpyClient:
        return self

    def create(self, **kwargs: object) -> None:
        self._attempts.append(dict(kwargs))
        raise openai.APITimeoutError(
            httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        )


class _RaisingClient:
    """Client stand-in that records ``with_options`` calls then fails locally."""

    def __init__(self, option_calls: list[dict[str, Any]]) -> None:
        self._option_calls = option_calls

    def with_options(self, **kwargs: object) -> _RaisingClient:
        self._option_calls.append(dict(kwargs))
        return self

    @property
    def chat(self) -> _RaisingClient:
        return self

    @property
    def completions(self) -> _RaisingClient:
        return self

    def create(self, **kwargs: object) -> None:
        raise LLMError("simulated local failure")


class TestProbeTimingBound:
    """A blackholing host must not hang the probe."""

    def test_single_spec_blackhole_is_bounded_and_unreachable(
        self, monkeypatch: pytest.MonkeyPatch, allow_network: None
    ) -> None:
        """Given one blackholing provider spec, when the probe runs,
        then it reports not-reachable and is bounded by the probe timeout.

        ``allow_network`` is required: the hermetic guard would refuse the
        blackhole connect instantly and the elapsed assertion would be vacuous.
        """
        _patch_load_config(monkeypatch, _config(specs=1))
        monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)

        start = time.monotonic()
        installed, status = Doctor._check_llm_api()
        elapsed = time.monotonic() - start

        assert installed is False
        assert status != "API reachable"
        # The connect genuinely blocked (not an instant refusal), so the
        # configured timeout is what bounded the call.
        assert elapsed >= _PROBE_TIMEOUT_S - 1.0
        assert elapsed < _PROBE_TIMEOUT_S + _SINGLE_SPEC_SLACK_S  # < 20 s

    def test_multi_spec_blackhole_total_time_is_bounded(
        self, monkeypatch: pytest.MonkeyPatch, allow_network: None
    ) -> None:
        """Given two blackholing provider specs, when the probe runs,
        then the total is bounded by N_specs × probe timeout.

        ``allow_network`` is required for the same reason as the single-spec
        test: without it the connects are refused instantly.
        """
        n_specs = 2
        _patch_load_config(monkeypatch, _config(specs=n_specs))
        monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)

        start = time.monotonic()
        installed, status = Doctor._check_llm_api()
        elapsed = time.monotonic() - start

        assert installed is False
        assert status != "API reachable"
        assert elapsed >= _PROBE_TIMEOUT_S - 1.0
        assert elapsed < n_specs * _PROBE_TIMEOUT_S + _MULTI_SPEC_SLACK_S


class TestProbeAttempts:
    """One request attempt per spec, carrying the probe timeout."""

    def _spy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        attempts: list[dict[str, Any]] = []
        option_calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            llm_client,
            "_build_client",
            lambda config, task_type="text_generation", provider_spec=None: _SpyClient(
                attempts, option_calls
            ),
        )
        return attempts, option_calls

    def test_probe_makes_one_attempt_per_spec_with_probe_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given ONE spec, when the probe runs, then exactly one request
        attempt was made and it carried the probe timeout."""
        attempts, option_calls = self._spy(monkeypatch)
        _patch_load_config(monkeypatch, _config(specs=1))
        monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)

        installed, status = Doctor._check_llm_api()

        assert installed is False
        assert status != "API reachable"
        assert len(attempts) == 1
        assert len(option_calls) == 1
        assert option_calls[0]["timeout"] == _PROBE_TIMEOUT_S
        # SDK-internal retries are disabled so the timeout bounds the whole call.
        assert option_calls[0]["max_retries"] == 0

    def test_probe_makes_one_attempt_per_spec_multi_spec(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given TWO specs, when the probe runs, then attempts == N_specs and
        every attempt carried the probe timeout."""
        n_specs = 2
        attempts, option_calls = self._spy(monkeypatch)
        _patch_load_config(monkeypatch, _config(specs=n_specs))
        monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)

        installed, status = Doctor._check_llm_api()

        assert installed is False
        assert status != "API reachable"
        assert len(attempts) == n_specs
        assert len(option_calls) == n_specs
        assert all(call["timeout"] == _PROBE_TIMEOUT_S for call in option_calls)

    def test_timeout_none_leaves_sdk_default_untouched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given ``timeout=None``, when ``llm_complete`` runs, then it must NOT
        call ``with_options`` — an explicit ``None`` would strip the SDK default
        timeout from every existing caller."""
        option_calls: list[dict[str, Any]] = []

        def _raising_client(
            config: dict[str, Any], task_type: str = "text_generation", provider_spec: object = None
        ) -> _RaisingClient:
            return _RaisingClient(option_calls)

        monkeypatch.setattr(llm_client, "_build_client", _raising_client)
        config = _config(specs=1)

        with pytest.raises(LLMError):
            llm_complete(prompt="hi", config=config, timeout=None)

        assert option_calls == []


class TestFakeModeNotReportedReachable:
    """Fake mode must never masquerade as a reachable API."""

    def test_env_fake_mode_is_not_reported_reachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Given ``AUTOMEDIA_FAKE_LLM=1``, when the probe runs, then the status
        is not ``"API reachable"``."""
        monkeypatch.setenv("AUTOMEDIA_FAKE_LLM", "1")
        _patch_load_config(monkeypatch, {"llm": {"fake_mode": False, "text_generation": {}}})

        installed, status = Doctor._check_llm_api()

        assert installed is False
        assert status != "API reachable"
        assert "fake" in (status or "").lower()

    def test_config_fake_mode_is_not_reported_reachable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Given ``llm.fake_mode: true`` in the merged config (and NO env var),
        when the probe runs, then the status is not ``"API reachable"``.

        Mechanism: ``_check_llm_api`` loads the merged config itself and passes
        it to ``_is_fake_mode(config)``; a bare ``_is_fake_mode()`` would miss
        this source.
        """
        monkeypatch.delenv("AUTOMEDIA_FAKE_LLM", raising=False)
        _patch_load_config(monkeypatch, {"llm": {"fake_mode": True}})

        installed, status = Doctor._check_llm_api()

        assert installed is False
        assert status != "API reachable"
        assert "fake" in (status or "").lower()
