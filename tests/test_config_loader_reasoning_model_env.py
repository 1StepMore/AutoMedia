"""``AUTOMEDIA_LLM_REASONING_MODEL`` env mapping (#560).

The reasoning-model switch must land on
``llm.text_generation.reasoning_model`` as a real ``bool`` so the LLM client
does not have to re-parse the string.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from automedia.core.config_loader import _env_to_config

_ENV_KEY = "AUTOMEDIA_LLM_REASONING_MODEL"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the env layer from a developer ``.env`` or ambient AUTOMEDIA_*."""
    monkeypatch.setattr("automedia.core.config_loader.dotenv_overlay", lambda: {})
    for key in [k for k in os.environ if k.startswith("AUTOMEDIA_")]:
        monkeypatch.delenv(key, raising=False)


def _reasoning_model() -> Any:
    """Return the mapped value, or ``False`` when the key is absent."""
    return (
        _env_to_config()
        .get("llm", {})
        .get("text_generation", {})
        .get("reasoning_model", False)
    )


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on"])
def test_truthy_values_enable_reasoning_model(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv(_ENV_KEY, raw)

    value = _reasoning_model()

    assert value is True, f"{_ENV_KEY}={raw!r} should map to True, got {value!r}"


@pytest.mark.parametrize("raw", ["0", "false", "off"])
def test_falsy_values_disable_reasoning_model(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv(_ENV_KEY, raw)

    value = _reasoning_model()

    assert value is False, f"{_ENV_KEY}={raw!r} should map to False, got {value!r}"


def test_unset_env_yields_false() -> None:
    assert _reasoning_model() is False
