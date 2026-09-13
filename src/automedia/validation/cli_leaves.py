"""CLI leaf-command coverage audit (gaps T-06, T-07).

A *leaf* is the deepest invocable CLI unit: a standalone command
(``automedia doctor``) or a subcommand of a command group (``automedia
pipeline state``).  A leaf is *registration-only* when the committed library
only ever runs it with ``--help`` (or never), so its behavior is unproven.
This module enumerates the declared leaves from the live CLI tree, computes
which leaves the committed scenarios exercise BEHAVIORALLY (a real invocation
without ``--help``), and reports every declared leaf that is neither covered
nor on the versioned ``registration_only.yml`` exemptions list (owner +
reason + one-release expiry).

The audit is static: it reads the CLI registration and the committed scenario
library, never executes a scenario.  A malformed exemptions file is a loud
:class:`LoadError` — coverage is never silently waived.
"""

from __future__ import annotations

import importlib
import shlex
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from automedia.validation.loader import LoadError, default_scenarios_dir, load_scenarios
from automedia.validation.schema import Scenario, Step

REGISTRATION_ONLY_FILENAME = "registration_only.yml"
"""Versioned registration-only exemptions list (gaps T-06/T-07)."""


@dataclass(frozen=True)
class CliTree:
    """The declared CLI shape: command groups and standalone commands."""

    sub_apps: dict[str, list[str]]
    fns: tuple[str, ...]

    def leaves(self) -> list[str]:
        """Every declared leaf: ``group sub`` pairs plus standalone commands."""
        names: list[str] = []
        for top, subs in self.sub_apps.items():
            if subs:
                names.extend(f"{top} {sub}" for sub in subs)
            else:
                names.append(top)
        names.extend(self.fns)
        return sorted(set(names))


def declared_cli_tree() -> CliTree:
    """Read the CLI registration and resolve every group's subcommands."""
    from automedia.cli.app import LazyTyperGroup

    sub_apps: dict[str, list[str]] = {}
    for name, (module_path, attr_name, _help) in LazyTyperGroup._lazy_sub_apps.items():
        module = importlib.import_module(module_path)
        click_app = getattr(module, attr_name)
        from typer.main import get_command

        command = get_command(click_app)
        sub_apps[name] = sorted(command.commands) if hasattr(command, "commands") else []
    fns = tuple(sorted(LazyTyperGroup._lazy_fns))
    return CliTree(sub_apps=sub_apps, fns=fns)


def _command_leaf(command: str, tree: CliTree) -> str | None:
    """The leaf a scenario CLI command invokes, or None when it is a help
    probe / non-automedia setup command / a group without a subcommand."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens or tokens[0] != "automedia" or "--help" in tokens:
        return None
    args = [token for token in tokens[1:] if not token.startswith("-")]
    if not args:
        return None
    top = args[0]
    if tree.sub_apps.get(top):
        if len(args) >= 2 and args[1] in tree.sub_apps[top]:
            return f"{top} {args[1]}"
        return None
    if top in tree.sub_apps or top in tree.fns:
        return top
    return None


def behavioral_cli_leaves(scenarios: list[Scenario], tree: CliTree) -> set[str]:
    """Leaves reached by a real (non-``--help``) CLI invocation in the library."""
    covered: set[str] = set()

    def walk(step: Step) -> None:
        if step.kind == "cli" and step.command:
            leaf = _command_leaf(step.command, tree)
            if leaf is not None:
                covered.add(leaf)
        for recovery in step.recovery_steps:
            walk(recovery)

    for scenario in scenarios:
        for step in [*scenario.steps, *scenario.cleanup_steps]:
            walk(step)
    return covered


def _load_exemptions(path: Path, today: date) -> tuple[set[str], dict[str, Any]]:
    """Load the versioned registration-only exemptions list.

    Every entry needs ``name``, ``owner`` and ``reason``; an optional ISO
    ``expires`` drops the entry once past.  A malformed file raises
    :class:`LoadError`.
    """
    meta: dict[str, Any] = {
        "path": str(path),
        "version": None,
        "reviewed": None,
        "release": None,
        "active": [],
        "expired": [],
    }
    if not path.is_file():
        return set(), meta
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise LoadError(f"{path}: registration-only exemptions unreadable: {exc}") from exc
    if not isinstance(doc, dict):
        raise LoadError(f"{path}: registration-only exemptions must be a mapping")
    if "version" not in doc:
        raise LoadError(f"{path}: registration-only exemptions require a 'version' field")
    meta["version"] = doc.get("version")
    meta["reviewed"] = doc.get("reviewed")
    meta["release"] = doc.get("release")
    entries = doc.get("entries", [])
    if not isinstance(entries, list):
        raise LoadError(f"{path}: 'entries' must be a list")
    active: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise LoadError(f"{path}: entries[{index}] must be a mapping")
        name = entry.get("name")
        owner = entry.get("owner")
        reason = entry.get("reason")
        for field, value in (("name", name), ("owner", owner), ("reason", reason)):
            if not isinstance(value, str) or not value.strip():
                raise LoadError(f"{path}: entries[{index}].{field} is required")
        expires = entry.get("expires")
        unexpired = True
        if expires is not None:
            try:
                unexpired = date.fromisoformat(str(expires)) >= today
            except ValueError as err:
                raise LoadError(
                    f"{path}: entries[{index}].expires must be ISO YYYY-MM-DD: {err}"
                ) from err
        row = {
            "name": name,
            "owner": owner,
            "reason": reason,
            "expires": expires,
        }
        meta["active" if unexpired else "expired"].append(row)
        if unexpired:
            active.add(name)
    return active, meta


def cli_leaves_audit(
    scenarios: list[Scenario] | None = None,
    *,
    scenarios_dir: str | Path | None = None,
    exemptions_path: str | Path | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Report covered / exempt / uncovered CLI leaves (gaps T-06, T-07)."""
    tree = declared_cli_tree()
    leaves = tree.leaves()
    loaded = load_scenarios(scenarios_dir) if scenarios is None else scenarios
    covered = behavioral_cli_leaves(loaded, tree)
    path = (
        Path(exemptions_path)
        if exemptions_path is not None
        else default_scenarios_dir() / REGISTRATION_ONLY_FILENAME
    )
    exempt, exemptions_meta = _load_exemptions(path, today or date.today())
    declared_set = set(leaves)
    return {
        "declared": leaves,
        "covered": sorted(covered & declared_set),
        "exempt": sorted(exempt & declared_set),
        "uncovered": sorted(declared_set - covered - exempt),
        "unknown_exemptions": sorted(exempt - declared_set),
        "exemptions": exemptions_meta,
        "counts": {
            "declared": len(leaves),
            "covered": len(covered & declared_set),
            "exempt": len(exempt & declared_set),
            "uncovered": len(declared_set - covered - exempt),
        },
    }


def main() -> None:
    """Print the audit as deterministic JSON (``python -m
    automedia.validation.cli_leaves``)."""
    import json

    print(json.dumps(cli_leaves_audit(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
