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
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvGateResult:
    """Outcome of evaluating one scenario's ``requires_env`` (guide §2.5).

    ``configured`` is ``False`` when any required variable is missing;
    ``missing`` names them in declaration order, deduped, and feeds the
    ``unconfigured`` reason in the run record.
    """

    configured: bool
    missing: list[str]


def check_env(
    requires_env: list[str] | None,
    environ: Mapping[str, str] | None = None,
) -> EnvGateResult:
    """Return whether every variable in ``requires_env`` is configured.

    ``environ`` is injectable for tests and defaults to ``os.environ``.
    ``requires_env`` of ``None`` or ``[]`` is always configured.  An empty
    string value counts as missing (unconfigured, never a silent pass).
    """
    names = [] if requires_env is None else requires_env
    env: Mapping[str, str] = os.environ if environ is None else environ
    missing = [name for name in dict.fromkeys(names) if not env.get(name)]
    return EnvGateResult(configured=not missing, missing=missing)
