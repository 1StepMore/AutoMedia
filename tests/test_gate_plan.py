"""Gate order has one authority, and the DAG agrees with it (issue #282).

Before this module the order was described three times: ``runner._MODE_MAP``
(the thing execution actually read), ``dag.AUTO_GATE_DAG`` (exported and
labelled "canonical" in the CLI), and ``GateRegistry`` registration order.
Nothing forced them to agree, and the "canonical" label pointed at a structure
execution never consulted.

``pipelines.gate_plan`` is now the declaration.  These tests pin:

* the plan is the thing the runner executes (identity, not just equality);
* the DAG's topological order reproduces the plan for every mode;
* the DAG never gains or loses a gate relative to the plan's reachable set.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from automedia.pipelines import gate_plan
from automedia.pipelines.dag import AUTO_GATE_DAG, GateNode, topological_order
from automedia.pipelines.runner import _MODE_MAP

_PLAN_SRC = Path(gate_plan.__file__)


# --------------------------------------------------------------------------- #
# The runner executes the plan, not a copy of it
# --------------------------------------------------------------------------- #


def test_runner_mode_map_is_the_plan_object() -> None:
    """Identity, not equality: a second literal would pass an == check."""
    assert _MODE_MAP is gate_plan.MODE_GATE_NAMES


def test_runner_reexports_are_the_plan_lists() -> None:
    """The historical private names must alias the plan, never shadow it."""
    from automedia.pipelines import runner

    pairs = {
        "_AUTO_GATE_NAMES": gate_plan._AUTO_GATE_NAMES,
        "_TEXT_ONLY_GATE_NAMES": gate_plan._TEXT_ONLY_GATE_NAMES,
        "_TEXT_WITH_COVER_GATE_NAMES": gate_plan._TEXT_WITH_COVER_GATE_NAMES,
        "_VIDEO_ONLY_GATE_NAMES": gate_plan._VIDEO_ONLY_GATE_NAMES,
        "_QA_ONLY_GATE_NAMES": gate_plan._QA_ONLY_GATE_NAMES,
        "_IMAGE_CAROUSEL_GATE_NAMES": gate_plan._IMAGE_CAROUSEL_GATE_NAMES,
        "_SOCIAL_THREAD_GATE_NAMES": gate_plan._SOCIAL_THREAD_GATE_NAMES,
        "_SHORT_VIDEO_GATE_NAMES": gate_plan._SHORT_VIDEO_GATE_NAMES,
        "_REPURPOSE_GATE_NAMES": gate_plan._REPURPOSE_GATE_NAMES,
    }
    for runner_name, plan_list in pairs.items():
        assert getattr(runner, runner_name) is plan_list, runner_name


def test_valid_modes_match_the_plan_keys() -> None:
    from automedia.pipelines.runner import VALID_MODES

    assert tuple(gate_plan.MODE_GATE_NAMES) == VALID_MODES


# --------------------------------------------------------------------------- #
# The DAG reproduces the plan
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", list(gate_plan.MODE_GATE_NAMES))
def test_dag_topological_order_equals_the_plan(mode: str) -> None:
    """The load-bearing equivalence: order from edges == declared order."""
    assert (
        topological_order(AUTO_GATE_DAG, gate_plan.MODE_GATE_NAMES[mode])
        == (gate_plan.MODE_GATE_NAMES[mode])
    )


@pytest.mark.parametrize("mode", list(gate_plan.MODE_GATE_NAMES))
def test_plan_lists_are_subsequences_of_dag_declaration_order(mode: str) -> None:
    """A preset may skip gates but may never reorder them relative to the DAG."""
    dag_order = list(AUTO_GATE_DAG)
    planned = [gate for gate in dag_order if gate in set(gate_plan.MODE_GATE_NAMES[mode])]

    assert planned == gate_plan.MODE_GATE_NAMES[mode]


def test_every_planned_gate_exists_in_the_dag() -> None:
    planned = set().union(*gate_plan.MODE_GATE_NAMES.values())

    assert planned - set(AUTO_GATE_DAG) == set()


def test_dag_gates_outside_every_preset_are_the_known_unpreset_ones() -> None:
    """G4/G5 and L1-L4 are registered but in no preset, by design."""
    planned = set().union(*gate_plan.MODE_GATE_NAMES.values())

    assert set(AUTO_GATE_DAG) - planned == {"G4", "G5", "L1", "L2", "L3", "L4"}


def test_no_gate_appears_twice_in_a_mode() -> None:
    for mode, names in gate_plan.MODE_GATE_NAMES.items():
        assert len(names) == len(set(names)), f"{mode} repeats a gate"


def test_gate_names_for_mode_returns_a_copy() -> None:
    """Callers compose (modifiers, tier filtering); the plan must not mutate."""
    names = gate_plan.gate_names_for_mode("auto")
    names.remove("G0")

    assert "G0" in gate_plan.MODE_GATE_NAMES["auto"]


def test_unknown_mode_raises_with_the_valid_list() -> None:
    with pytest.raises(ValueError, match="Unknown pipeline mode"):
        gate_plan.gate_names_for_mode("nope")


# --------------------------------------------------------------------------- #
# Import isolation and single declaration
# --------------------------------------------------------------------------- #


def test_gate_plan_imports_nothing_from_automedia() -> None:
    """The plan is a leaf, so ``dag`` can import it without a runner cycle."""
    tree = ast.parse(_PLAN_SRC.read_text(encoding="utf-8"))

    offenders = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("automedia")
    ]
    offenders += [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name.startswith("automedia")
    ]

    assert offenders == []


def test_dag_still_does_not_import_the_runner() -> None:
    dag_src = Path(
        AUTO_GATE_DAG.__class__.__module__
        and __import__("automedia.pipelines.dag", fromlist=["x"]).__file__
    )
    text = dag_src.read_text(encoding="utf-8")

    tree = ast.parse(text)
    offenders = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "automedia.pipelines.runner"
    ]

    assert offenders == []


def test_only_gate_plan_declares_a_mode_gate_list() -> None:
    """The plan must exist in exactly one file — this is the whole point.

    A ``runner.py`` re-export is an alias assignment whose value is an
    ATTRIBUTE (``gate_plan._AUTO_GATE_NAMES``), not a literal list, so it does
    not count as a second declaration.
    """
    src_root = _PLAN_SRC.parent
    declarations: list[str] = []
    for path in sorted(src_root.glob("*.py")):
        if path.name == "gate_plan.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            target = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
            elif isinstance(node, ast.AnnAssign):
                target = node.target
            if not isinstance(target, ast.Name):
                continue
            if not target.id.endswith("_GATE_NAMES"):
                continue
            if isinstance(getattr(node, "value", None), ast.List):
                declarations.append(f"{path.name}:{target.id}")

    assert declarations == [], "a gate-name list is declared outside gate_plan.py: " + ", ".join(
        declarations
    )


def test_gate_node_is_still_the_dag_node_type() -> None:
    """Guard against a refactor replacing nodes with plain dicts."""
    assert all(isinstance(node, GateNode) for node in AUTO_GATE_DAG.values())
