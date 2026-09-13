"""CLI leaf-command coverage audit (gaps T-06, T-07).

A leaf is behaviourally covered when a scenario invokes it without
``--help``; otherwise it must be on the versioned ``registration_only.yml``
exemptions list (owner + reason + one-release expiry).  The committed
library must leave zero uncovered leaves.  Synthetic fixtures only.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from automedia.validation.cli_leaves import cli_leaves_audit
from automedia.validation.loader import LoadError
from automedia.validation.schema import Scenario

_TODAY = date(2026, 9, 13)


def _cli_scenario(name: str, command: str) -> Scenario:
    return Scenario.from_dict(
        {
            "name": name,
            "description": "synthetic CLI leaf fixture",
            "intent": "exercise the CLI leaf audit",
            "user_level": "L0",
            "category": "cli",
            "requires_env": [],
            "steps": [
                {
                    "name": "run the command",
                    "kind": "cli",
                    "check": "the command answers",
                    "standard": "founder-expectations.F02",
                    "command": command,
                    "expect": {"exit_code": 0},
                }
            ],
        }
    )


def _write_exemptions(path: Path, entries: list[dict[str, str]]) -> Path:
    lines = ["version: 1", 'reviewed: "2026-09-13"', "entries:"]
    for entry in entries:
        lines.append(f"  - name: {entry['name']}")
        lines.append(f"    owner: {entry['owner']}")
        lines.append(f"    reason: {entry['reason']}")
        if "expires" in entry:
            lines.append(f'    expires: "{entry["expires"]}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class TestCommittedLibrary:
    def test_no_uncovered_unexempt_leaf(self) -> None:
        audit = cli_leaves_audit(today=_TODAY)
        assert audit["uncovered"] == [], audit["uncovered"]
        assert audit["unknown_exemptions"] == [], audit["unknown_exemptions"]
        assert audit["counts"]["declared"] == audit["counts"]["covered"] + audit["counts"]["exempt"]

    def test_the_four_validate_commands_are_covered(self) -> None:
        audit = cli_leaves_audit(today=_TODAY)
        for leaf in ("validate run", "validate report", "validate diff", "validate coverage"):
            assert leaf in audit["covered"], f"{leaf} not behaviourally covered"


class TestLeafClassification:
    def test_help_probe_does_not_cover_a_leaf(self, tmp_path: Path) -> None:
        scenarios = [_cli_scenario("help-only", "automedia adapter --help")]
        exemptions = _write_exemptions(
            tmp_path / "exempt.yml",
            [{"name": "adapter create", "owner": "o", "reason": "r", "expires": "2099-01-01"}],
        )
        audit = cli_leaves_audit(scenarios=scenarios, exemptions_path=exemptions, today=_TODAY)
        assert "adapter list" in audit["uncovered"]
        assert "adapter create" in audit["exempt"]

    def test_behavioral_invocation_covers_a_leaf(self, tmp_path: Path) -> None:
        scenarios = [_cli_scenario("behavior", "automedia adapter list")]
        audit = cli_leaves_audit(scenarios=scenarios, exemptions_path=tmp_path / "none.yml")
        assert "adapter list" in audit["covered"]

    def test_group_subcommand_is_the_leaf(self, tmp_path: Path) -> None:
        scenarios = [_cli_scenario("state", "automedia pipeline state a4c8 --base-dir /tmp/x")]
        audit = cli_leaves_audit(scenarios=scenarios, exemptions_path=tmp_path / "none.yml")
        assert "pipeline state" in audit["covered"]
        assert "pipeline" not in audit["covered"]

    def test_expired_exemption_is_uncovered_again(self, tmp_path: Path) -> None:
        scenarios = [_cli_scenario("help-only", "automedia adapter --help")]
        exemptions = _write_exemptions(
            tmp_path / "exempt.yml",
            [{"name": "adapter list", "owner": "o", "reason": "r", "expires": "2020-01-01"}],
        )
        audit = cli_leaves_audit(scenarios=scenarios, exemptions_path=exemptions, today=_TODAY)
        assert "adapter list" in audit["uncovered"]
        assert "adapter list" not in audit["exempt"]


class TestExemptionValidation:
    def test_missing_reason_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yml"
        path.write_text(
            "version: 1\nentries:\n  - name: adapter list\n    owner: o\n",
            encoding="utf-8",
        )
        with pytest.raises(LoadError, match="reason is required"):
            cli_leaves_audit(scenarios=[], exemptions_path=path, today=_TODAY)

    def test_bad_expiry_is_rejected(self, tmp_path: Path) -> None:
        exemptions = _write_exemptions(
            tmp_path / "bad.yml",
            [{"name": "adapter list", "owner": "o", "reason": "r", "expires": "not-a-date"}],
        )
        with pytest.raises(LoadError, match="expires"):
            cli_leaves_audit(scenarios=[], exemptions_path=exemptions, today=_TODAY)

    def test_unknown_exemption_is_reported(self, tmp_path: Path) -> None:
        exemptions = _write_exemptions(
            tmp_path / "unknown.yml",
            [{"name": "no-such-leaf", "owner": "o", "reason": "r", "expires": "2099-01-01"}],
        )
        audit = cli_leaves_audit(scenarios=[], exemptions_path=exemptions, today=_TODAY)
        assert audit["unknown_exemptions"] == ["no-such-leaf"]
