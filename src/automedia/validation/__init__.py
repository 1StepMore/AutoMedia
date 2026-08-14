"""Agent-tester validation engine — scenario schema layer (Wave 1, C1).

Public surface of the validation package: closed-field scenario dataclasses
and schema constants.  The loader (W1-T2), adapters (W1-T4) and expect
evaluator (W1-T6) all build on this contract.
"""

from automedia.validation.schema import (
    ARTIFACT_CHECK_FIELDS,
    DEFAULT_TIMEOUT_SECONDS,
    EXPECT_KEYS,
    SCENARIO_FIELDS,
    STEP_FIELDS,
    STEP_KINDS,
    ArtifactCheck,
    Expect,
    Scenario,
    SchemaError,
    Step,
)

__all__ = [
    "ARTIFACT_CHECK_FIELDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "EXPECT_KEYS",
    "SCENARIO_FIELDS",
    "STEP_FIELDS",
    "STEP_KINDS",
    "ArtifactCheck",
    "Expect",
    "Scenario",
    "SchemaError",
    "Step",
]
