"""Fake-LLM-aware env gate (gap T-15, criterion i).

With ``AUTOMEDIA_FAKE_LLM=1`` the deterministic mock LLM answers every call,
so a scenario whose only unmet prerequisite is the LLM provider key must RUN
and be graded — never short-circuit to ``unconfigured``.  Scenarios that must
use the real provider opt out with ``requires_real_llm: true`` and stay gated.
Non-LLM prerequisites (master key, platform credentials, validation expect
vars) are unaffected: a missing one still gates.

All fixtures are synthetic (Red Line 4).
"""

from __future__ import annotations

import asyncio

import pytest

from automedia.core.llm_client import llm_complete
from automedia.validation.engine import make_adapters, run_validation_scenario_async
from automedia.validation.env_gate import check_env, fake_mode_active
from automedia.validation.schema import Expect, Scenario, Step

_LLM_KEY = "AUTOMEDIA_LLM_API_KEY"
_FAKE = "AUTOMEDIA_FAKE_LLM"


def _scenario(*, requires_real_llm: bool = False) -> Scenario:
    """A one-step CLI scenario gated on the LLM provider key."""
    return Scenario(
        name="fake-gated-fixture",
        description="Synthetic scenario gated on the LLM provider key.",
        intent="Prove the fake-LLM-aware env gate runs LLM-requiring scenarios.",
        requires_env=[_LLM_KEY],
        requires_real_llm=requires_real_llm,
        steps=[
            Step(
                name="echo ok",
                kind="cli",
                check="echo prints ok",
                standard="founder-expectations.F02",
                command="python3 -c \"print('ok')\"",
                expect=Expect(exit_code=0, stdout_has=["ok"]),
            )
        ],
    )


@pytest.fixture()
def credential_free(monkeypatch: pytest.MonkeyPatch) -> None:
    """No real LLM key in the environment (CI's credential-free state)."""
    monkeypatch.delenv(_LLM_KEY, raising=False)


class TestEnvGateFakeMode:
    def test_fake_mode_active_reads_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_FAKE, "1")
        assert fake_mode_active() is True
        monkeypatch.setenv(_FAKE, "false")
        assert fake_mode_active() is False
        monkeypatch.delenv(_FAKE, raising=False)
        assert fake_mode_active() is False

    def test_fake_mode_satisfies_the_llm_key(
        self, monkeypatch: pytest.MonkeyPatch, credential_free: None
    ) -> None:
        monkeypatch.setenv(_FAKE, "1")
        result = check_env([_LLM_KEY])
        assert result.configured is True
        assert result.missing == []

    def test_no_fake_mode_stays_gated(self, credential_free: None) -> None:
        result = check_env([_LLM_KEY])
        assert result.configured is False
        assert result.missing == [_LLM_KEY]

    def test_requires_real_llm_stays_gated(
        self, monkeypatch: pytest.MonkeyPatch, credential_free: None
    ) -> None:
        monkeypatch.setenv(_FAKE, "1")
        result = check_env([_LLM_KEY], requires_real_llm=True)
        assert result.configured is False
        assert result.missing == [_LLM_KEY]

    def test_non_llm_prerequisite_stays_gated_in_fake_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_FAKE, "1")
        result = check_env(["AUTOMEDIA_MASTER_KEY"])
        assert result.configured is False
        assert result.missing == ["AUTOMEDIA_MASTER_KEY"]

    def test_control_vars_stay_gated_in_fake_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_FAKE, "1")
        result = check_env(["AUTOMEDIA_VALIDATION_EXPECT_X"])
        assert result.configured is False


class TestEngineFakeMode:
    def test_fake_mode_journey_is_not_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch, credential_free: None
    ) -> None:
        monkeypatch.setenv(_FAKE, "1")
        record = asyncio.run(
            run_validation_scenario_async(_scenario(), make_adapters(None))
        )
        assert record["status"] != "unconfigured"
        assert record["status"] == "passed"

    def test_no_fake_no_key_is_unconfigured(self, credential_free: None) -> None:
        record = asyncio.run(
            run_validation_scenario_async(_scenario(), make_adapters(None))
        )
        assert record["status"] == "unconfigured"
        assert _LLM_KEY in str(record["reason"])

    def test_requires_real_llm_is_unconfigured_in_fake_mode(
        self, monkeypatch: pytest.MonkeyPatch, credential_free: None
    ) -> None:
        monkeypatch.setenv(_FAKE, "1")
        record = asyncio.run(
            run_validation_scenario_async(
                _scenario(requires_real_llm=True), make_adapters(None)
            )
        )
        assert record["status"] == "unconfigured"


class TestFakeTextResponse:
    def test_fake_text_exceeds_the_journey_draft_floor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_FAKE, "1")
        response = llm_complete("Write an article about image carousels", config={})
        assert len(response.encode("utf-8")) > 500
        assert len(response) >= 1500

    def test_fake_text_is_deterministic_and_echoes_the_prompt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_FAKE, "1")
        prompt = "A fixed prompt used to prove the echo"
        first = llm_complete(prompt, config={})
        second = llm_complete(prompt, config={})
        assert first == second
        assert prompt in first
        assert "This is a fake LLM response" not in first
