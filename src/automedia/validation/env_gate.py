"""Environment gate for agent-tester validation scenarios (W1-T5).

Evaluates a scenario's ``requires_env`` list against the process environment
(guide §2.5).  The gate never returns a pass/fail verdict: a missing
prerequisite marks the scenario ``unconfigured`` — a state, never a verdict of
acceptance (§2.5: "``unconfigured`` is a state, never a verdict of
acceptance"; §4.2: "unconfigured never passes").  The caller (W1-T7 engine)
maps a non-configured result to the ``unconfigured`` status and carries the
``missing`` list into the run record as the reason.

A variable is missing when it is absent from the environment OR set to the
empty string — an empty value is an unconfigured variable, not a silent pass
(honesty rule).  Declaration order of the missing names is preserved and
duplicates are removed.

Fake-LLM awareness (gap T-15, criterion i): when ``AUTOMEDIA_FAKE_LLM=1``
the deterministic mock LLM answers every call, so a scenario whose only unmet
prerequisites are LLM provider variables RUNS and is graded instead of
short-circuiting to ``unconfigured``.  A scenario that must exercise the real
provider opts out via ``requires_real_llm: true`` and stays gated.  Non-LLM
prerequisites (master key, platform credentials, ``AUTOMEDIA_VALIDATION_
EXPECT_*``) are never exempted — a missing one still gates.  Whether a mocked
run reaches ``passed`` is T-21's acceptance, not this gate's.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

_FAKE_TRUTHY: frozenset[str] = frozenset({"1", "true", "yes"})
"""Values of ``AUTOMEDIA_FAKE_LLM`` that activate the deterministic mock."""

LLM_ENV_NAMES: frozenset[str] = frozenset(
    {
        "AUTOMEDIA_LLM_API_KEY",
        "AUTOMEDIA_LLM_BASE_URL",
        "AUTOMEDIA_LLM_PROVIDER",
        "AUTOMEDIA_LLM_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "GOOGLE_API_KEY",
    }
)
"""LLM provider variables the fake mode exempts; every other var stays gated.

Master keys (``AUTOMEDIA_MASTER_KEY``), platform credentials, and the
``AUTOMEDIA_VALIDATION_EXPECT_*`` control vars are deliberately absent —
fake LLM mode substitutes the language model only, never credentials.
"""


@dataclass(frozen=True)
class EnvGateResult:
    """Outcome of evaluating one scenario's ``requires_env`` (guide §2.5).

    ``configured`` is ``False`` when any required variable is missing;
    ``missing`` names them in declaration order, deduped, and feeds the
    ``unconfigured`` reason in the run record.
    """

    configured: bool
    missing: list[str]


def fake_mode_active(environ: Mapping[str, str] | None = None) -> bool:
    """True when ``AUTOMEDIA_FAKE_LLM`` selects the deterministic mock LLM.

    Reads the environment variable directly (the primary fake-mode mechanism
    in ``automedia.core.llm_client``); the config-file fallback belongs to the
    LLM client and is intentionally not consulted here — the gate must stay a
    pure environment check.
    """
    env: Mapping[str, str] = os.environ if environ is None else environ
    return env.get("AUTOMEDIA_FAKE_LLM", "").strip().lower() in _FAKE_TRUTHY


def check_env(
    requires_env: list[str] | None,
    environ: Mapping[str, str] | None = None,
    *,
    requires_real_llm: bool = False,
    fake_mode: bool | None = None,
) -> EnvGateResult:
    """Return whether every variable in ``requires_env`` is configured.

    ``environ`` is injectable for tests and defaults to ``os.environ``.
    ``requires_env`` of ``None`` or ``[]`` is always configured.  An empty
    string value counts as missing (unconfigured, never a silent pass).

    Fake-LLM awareness (gap T-15): when fake mode is active (explicit
    ``fake_mode`` or ``AUTOMEDIA_FAKE_LLM`` in ``environ``) and the scenario
    does not declare ``requires_real_llm``, missing LLM provider variables are
    exempted — the scenario runs against the mock.  Every other missing
    variable still gates.
    """
    names = [] if requires_env is None else requires_env
    env: Mapping[str, str] = os.environ if environ is None else environ
    missing = [name for name in dict.fromkeys(names) if not env.get(name)]
    active = fake_mode_active(env) if fake_mode is None else fake_mode
    if active and not requires_real_llm:
        missing = [name for name in missing if name not in LLM_ENV_NAMES]
    return EnvGateResult(configured=not missing, missing=missing)
