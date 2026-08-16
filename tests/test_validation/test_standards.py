"""Unit tests for the validation standards registry (W1-T3).

The handbook format is pinned by ``standards.py``: a ``## Standards`` (or
``## Standard Keys``) heading followed by a Markdown table whose ``Key``
column holds the standard keys scenario steps cite.  W1 tests run against
FIXTURE handbooks because the real ``scenarios/STANDARDS.md`` is authored in
W2-T1 (plan W1-T3, Momus improvement 3).

Covers: known keys parsed from the fixture (Key column only — no invented
keys), unknown keys rejected, trimming/dedup/non-empty tolerance, both pinned
headings, from_default resolution (env override + repo-root default), absent
handbook -> loud StandardsError naming the path, malformed handbook -> loud
StandardsError naming the file.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from automedia.validation import standards as standards_module
from automedia.validation.standards import StandardsError, StandardsRegistry

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "synth" / "standards"
FIXTURE_HANDBOOK = FIXTURES / "standards_fixture.md"
KEYS_HEADING_FIXTURE = FIXTURES / "standards_keys_heading_fixture.md"

KNOWN_KEYS = {
    "founder-expectations.F01",
    "founder-expectations.F02",
    "evaluation-matrix.dim1",
    "evaluation-matrix.dim2",
    "gate.G6",
    "gate.V0",
    "builtin.artifact_exists",
    "builtin.non_empty",
    "builtin.gate_records_pass",
    "builtin.exit_code",
    "builtin.data_has",
    "builtin.unconfigured",
}

# Canonical pipeline surfaces (issue #78 A1): one standard key per gate (33)
# and per pipeline mode (9).  Gate names EXACTLY as the gates registry names
# them (pre-gate, CW, G0-G6, V0-V7, H0, L1-L4, D1-D7, P1-P4); mode names
# exactly as ``_MODE_MAP`` keys runner.py.  The real handbook must define
# exactly these and no more.
ALL_GATE_KEYS: set[str] = {
    f"gate.{name}"
    for name in (
        "pre-gate",
        "CW",
        "G0",
        "G1",
        "G2",
        "G3",
        "G4",
        "G5",
        "G6",
        "V0",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
        "V7",
        "H0",
        "L1",
        "L2",
        "L3",
        "L4",
        "D1",
        "D2",
        "D3",
        "D4",
        "D5",
        "D6",
        "D7",
        "P1",
        "P2",
        "P3",
        "P4",
    )
}
ALL_MODE_KEYS: set[str] = {
    f"mode.{name}"
    for name in (
        "auto",
        "text_only",
        "text_with_cover",
        "video_only",
        "qa_only",
        "image-carousel",
        "social-thread",
        "short-video",
        "repurpose",
    )
}


def test_fixture_handbooks_are_committed() -> None:
    """Guard: tests must run against the fixtures, never a real handbook."""
    assert FIXTURE_HANDBOOK.is_file()
    assert KEYS_HEADING_FIXTURE.is_file()


def test_real_handbook_defines_all_gate_and_mode_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #78 A1: the REAL ``scenarios/STANDARDS.md`` defines exactly the
    canonical 33 ``gate.*`` + 9 ``mode.*`` keys — the loader cross-checks
    every step's ``standard:`` against this handbook, so a scenario step
    citing ``gate.G1`` fails to load until the key exists here.  The set is
    pinned exactly (no extra, no missing) so the reconciliation cannot
    silently drift."""
    assert len(ALL_GATE_KEYS) == 33
    assert len(ALL_MODE_KEYS) == 9
    monkeypatch.delenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", raising=False)
    registry = StandardsRegistry.from_default()
    known = registry.known_keys()
    gate_keys = {key for key in known if key.startswith("gate.")}
    mode_keys = {key for key in known if key.startswith("mode.")}
    assert gate_keys == ALL_GATE_KEYS, (
        f"handbook gate.* keys differ from canonical 33: "
        f"missing={sorted(ALL_GATE_KEYS - gate_keys)}, "
        f"extra={sorted(gate_keys - ALL_GATE_KEYS)}"
    )
    assert mode_keys == ALL_MODE_KEYS, (
        f"handbook mode.* keys differ from canonical 9: "
        f"missing={sorted(ALL_MODE_KEYS - mode_keys)}, "
        f"extra={sorted(mode_keys - ALL_MODE_KEYS)}"
    )
    for key in ALL_GATE_KEYS | ALL_MODE_KEYS:
        assert registry.validate_standard(key) is True


def test_known_keys_parsed_from_fixture() -> None:
    registry = StandardsRegistry(FIXTURE_HANDBOOK)

    assert registry.known_keys() == KNOWN_KEYS
    for key in KNOWN_KEYS:
        assert registry.validate_standard(key) is True


def test_validate_standard_unknown_key_returns_false() -> None:
    registry = StandardsRegistry(FIXTURE_HANDBOOK)

    assert registry.validate_standard("founder-expectations.F99") is False
    assert registry.validate_standard("gate.V9") is False
    assert registry.validate_standard("") is False
    assert registry.validate_standard(" ") is False


def test_duplicate_rows_are_deduped() -> None:
    """The fixture carries founder-expectations.F01 twice on purpose."""
    registry = StandardsRegistry(FIXTURE_HANDBOOK)

    assert len(registry.known_keys()) == len(KNOWN_KEYS)
    assert registry.known_keys() == KNOWN_KEYS


def test_keys_are_trimmed_and_nonempty(tmp_path: Path) -> None:
    handbook = tmp_path / "STANDARDS.md"
    handbook.write_text(
        "\n".join(
            [
                "## Standards",
                "",
                "| Key | Check type | Standard | Source doc | Clause |",
                "| --- | --- | --- | --- | --- |",
                "|  founder-expectations.F01  | artifact_exists | F01 | docs/x.md | §8.3 |",
                "| | non_empty | blank key row is skipped | docs/guide.md | §2 |",
                "| builtin.non_empty | non_empty | expect contract | docs/guide.md | §2.3 |",
            ]
        ),
        encoding="utf-8",
    )

    registry = StandardsRegistry(handbook)

    assert registry.known_keys() == {"founder-expectations.F01", "builtin.non_empty"}


def test_standard_keys_heading_variant() -> None:
    """The alternative pinned heading ``## Standard Keys`` is accepted."""
    registry = StandardsRegistry(KEYS_HEADING_FIXTURE)

    assert "founder-expectations.F01" in registry.known_keys()
    assert "evaluation-matrix.dim1" in registry.known_keys()
    assert "gate.G6" in registry.known_keys()
    assert "builtin.artifact_exists" in registry.known_keys()
    assert registry.validate_standard("founder-expectations.F01") is True


def test_from_default_uses_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """from_default resolves ``<dir>/STANDARDS.md``; the env override points
    at a directory carrying a STANDARDS.md copied from the fixture."""
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    shutil.copy(FIXTURE_HANDBOOK, scenario_dir / "STANDARDS.md")
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(scenario_dir))

    registry = StandardsRegistry.from_default()

    assert registry.known_keys() == KNOWN_KEYS


def test_from_default_resolves_repo_root_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", raising=False)

    assert standards_module._resolve_scenarios_dir() == (
        Path(__file__).resolve().parents[2] / "scenarios"
    )


def test_from_default_without_handbook_raises_loudly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty_dir = tmp_path / "no-handbook"
    empty_dir.mkdir()
    monkeypatch.setenv("AUTOMEDIA_VALIDATION_SCENARIOS_DIR", str(empty_dir))

    with pytest.raises(StandardsError) as exc_info:
        StandardsRegistry.from_default()

    message = str(exc_info.value)
    assert "STANDARDS.md" in message
    assert str(empty_dir) in message


def test_explicit_missing_path_raises(tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "STANDARDS.md"

    with pytest.raises(StandardsError) as exc_info:
        StandardsRegistry(missing)

    assert str(missing) in str(exc_info.value)


def test_malformed_handbook_without_table_raises(tmp_path: Path) -> None:
    handbook = tmp_path / "STANDARDS.md"
    handbook.write_text("## Standards\n\nNo table here, just prose.\n", encoding="utf-8")

    with pytest.raises(StandardsError) as exc_info:
        StandardsRegistry(handbook)

    assert str(handbook) in str(exc_info.value)


def test_malformed_handbook_without_heading_raises(tmp_path: Path) -> None:
    handbook = tmp_path / "STANDARDS.md"
    handbook.write_text(
        "\n".join(
            [
                "| Key | Check type | Standard | Source doc | Clause |",
                "| --- | --- | --- | --- | --- |",
                "| builtin.artifact_exists | artifact_exists | expect | docs/guide.md | §2.3 |",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(StandardsError) as exc_info:
        StandardsRegistry(handbook)

    assert str(handbook) in str(exc_info.value)


def test_init_without_path_raises() -> None:
    with pytest.raises(StandardsError):
        StandardsRegistry()
