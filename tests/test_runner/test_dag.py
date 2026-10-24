"""RED-phase characterization tests for the canonical ``AUTO_GATE_DAG``.

Part of the graph-engineering-rollout Wave 1 (P0 equivalence layer).

These tests encode the canonical DAG spec: a directed acyclic graph of gate
nodes (``GateNode``) with ``depends_on`` edges, exposed as ``AUTO_GATE_DAG``
plus two helpers — ``downstream`` (reverse topological closure) and
``topological_order`` (topologically ordered subset of a gate-name list).

The load-bearing invariant (TestTopologicalOrderEquivalence): for EVERY mode
in ``automedia.pipelines.runner._MODE_MAP``,
``topological_order(AUTO_GATE_DAG, _MODE_MAP[mode])`` must reproduce the
existing linear gate-name list byte-exact. That means the DAG is a drop-in
replacement for the hardcoded mode lists — the runner's ordering semantics
must not change at all.

RED today: ``automedia.pipelines.dag`` does not exist yet, so this module
fails to collect with an ImportError. GREEN after
``src/automedia/pipelines/dag.py`` is implemented to satisfy every assertion
below.
"""

from __future__ import annotations

import random
import subprocess
import sys

import pytest

from automedia.pipelines import dag
from automedia.pipelines.dag import (
    AUTO_GATE_DAG,
    GATE_ORDER,
    GateNode,
    downstream,
    topological_order,
)
from automedia.pipelines.runner import _MODE_MAP

# Canonical track assignment (per the graph-engineering-rollout spec).
_COPY_TRACK = {"CW", "G0", "G1", "G2", "G3", "G4", "G5", "G6"}
_VIDEO_TRACK = {"V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"}
_LIFECYCLE_TRACK = {"L1", "L2", "L3", "L4"}
_QA_TRACK = {"pre-gate", "H0", "P1", "P2", "P3", "P4"}


class TestTopologicalOrderEquivalence:
    """P0 load-bearing invariant: the DAG reproduces the linear lists.

    The old version of this test passed the mode's own list as input and
    asserted the same list came back — true by construction, because the
    implementation tie-broke on input order.  It proved nothing: a shuffled
    input could legally emit G6 before CW, and only the sorted input ever
    produced the sorted answer.

    These tests pin the property that actually matters: the output depends on
    the GRAPH, not on how the caller ordered its argument.
    """

    @pytest.mark.parametrize("mode", list(_MODE_MAP))
    def test_topological_order_matches_mode_map(self, mode: str) -> None:
        """``topological_order`` on the mode subset equals the mode's list."""
        expected = _MODE_MAP[mode]
        ordered = topological_order(AUTO_GATE_DAG, expected)
        assert isinstance(ordered, list)
        assert ordered == expected

    @pytest.mark.parametrize("mode", list(_MODE_MAP))
    def test_shuffled_input_still_yields_the_canonical_order(self, mode: str) -> None:
        """Any permutation of a mode's gates must sort back to the plan.

        Without this, the equivalence above is an identity check on the input.
        """
        expected = _MODE_MAP[mode]
        shuffler = random.Random(f"dag-{mode}")
        for _ in range(50):
            shuffled = list(expected)
            shuffler.shuffle(shuffled)
            assert topological_order(AUTO_GATE_DAG, shuffled) == expected

    @pytest.mark.parametrize("mode", list(_MODE_MAP))
    def test_output_is_a_valid_topological_order(self, mode: str) -> None:
        """Vertices precede nothing that depends on them.

        Checked on a SHUFFLED input so the assertion cannot pass just by
        echoing the plan back.
        """
        subset = set(_MODE_MAP[mode])
        shuffler = random.Random(f"valid-{mode}")
        shuffled = list(_MODE_MAP[mode])
        shuffler.shuffle(shuffled)
        ordered = topological_order(AUTO_GATE_DAG, shuffled)

        position = {gate: index for index, gate in enumerate(ordered)}
        for gate in ordered:
            for parent in AUTO_GATE_DAG[gate].depends_on:
                if parent in subset:
                    assert position[parent] < position[gate], f"{parent} must precede {gate}"

    def test_g6_never_precedes_cw(self) -> None:
        """REGRESSION LOCK for the bug the old tie-break hid.

        G6 depends on G5, which is in no preset, so under present-parents
        semantics G6 becomes "ready" immediately.  With an input-order
        tie-break that let it emit first and inspect content CW had not yet
        written.  Declaration-order tie-break keeps CW ahead of it.
        """
        for mode in ("text_with_cover", "image-carousel", "social-thread"):
            gates = _MODE_MAP[mode]
            shuffler = random.Random(f"g6-{mode}")
            shuffled = list(gates)
            shuffle_attempts = 20
            for _ in range(shuffle_attempts):
                shuffler.shuffle(shuffled)
                ordered = topological_order(AUTO_GATE_DAG, shuffled)
                assert ordered.index("CW") < ordered.index("G6"), mode


class TestDeclarationOrderIsSemantic:
    """``AUTO_GATE_DAG`` insertion order IS the tie-break, so it is pinned.

    ``topological_order`` resolves ready gates in declaration order.  Without a
    pin, reordering the dict would silently change which gate runs first — the
    exact class of change that produced the G6-before-CW bug.  These tests make
    the order data instead of an accident of source layout.
    """

    EXPECTED_ORDER: tuple[str, ...] = (
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
        "P1",
        "P2",
        "P3",
        "P4",
    )

    def test_gate_order_matches_the_pinned_sequence(self) -> None:
        """The literal sequence.  Editing the dict without editing this fails."""
        assert GATE_ORDER == self.EXPECTED_ORDER

    def test_gate_order_covers_the_dag_exactly(self) -> None:
        assert set(GATE_ORDER) == set(AUTO_GATE_DAG)
        assert len(GATE_ORDER) == len(AUTO_GATE_DAG)

    def test_track_blocks_appear_in_the_documented_order(self) -> None:
        """pre-gate → copy → video → H0 → lifecycle → repurpose."""
        index = {name: i for i, name in enumerate(GATE_ORDER)}
        blocks = [
            ("pre-gate",),
            ("CW", "G0", "G1", "G2", "G3", "G4", "G5", "G6"),
            ("V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7"),
            ("H0",),
            ("L1", "L2", "L3", "L4"),
            ("P1", "P2", "P3", "P4"),
        ]
        flattened = [gate for block in blocks for gate in block]
        assert flattened == list(GATE_ORDER)
        assert [index[g] for g in flattened] == sorted(index[g] for g in flattened)

    def test_import_time_guard_accepts_the_real_dag(self) -> None:
        """The guard runs at import; importing this module already proved it."""
        dag._validate_declaration_order()  # must not raise

    def test_import_time_guard_rejects_a_forward_edge(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A dependent declared BEFORE its parent must be rejected.

        Simulated by patching the order so CW (which depends on pre-gate) comes
        first — the exact shape a careless reorder would produce.
        """
        # Move pre-gate to the END: same key set (so the drift guard passes),
        # but CW now sits before the parent it depends on.
        rotated = (*(name for name in GATE_ORDER if name != "pre-gate"), "pre-gate")
        monkeypatch.setattr(dag, "GATE_ORDER", rotated)

        with pytest.raises(RuntimeError, match="declared LATER"):
            dag._validate_declaration_order()

    def test_import_time_guard_rejects_drift(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dag, "GATE_ORDER", GATE_ORDER[:-1])

        with pytest.raises(RuntimeError, match="drifted"):
            dag._validate_declaration_order()

    def test_unknown_parent_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        broken = dict(AUTO_GATE_DAG)
        broken["CW"] = GateNode(
            name="CW", track="copy", depends_on=("does-not-exist",), failure_mode="stop"
        )
        monkeypatch.setattr(dag, "AUTO_GATE_DAG", broken)

        with pytest.raises(RuntimeError, match="unknown gate"):
            dag._validate_declaration_order()


class TestEdgesMustBeSatisfiable:
    """A DAG edge must name a predecessor that can actually run first.

    Under present-parents semantics a parent outside the mode subset is
    silently ignored, so an edge whose parent is in NO preset is not a soft
    constraint — it is a claim that can never be honoured.  Two such edges
    existed (G6<-G5 and P1<-L4) and both were invisible because the DAG was
    only ever checked against inputs that happened to be pre-sorted.
    """

    def test_no_preset_gate_depends_on_a_gate_in_no_preset(self) -> None:
        """The specific defect: a preset gate claiming an unpreset predecessor."""
        preset_gates = set().union(*_MODE_MAP.values())
        offenders = [
            f"{gate} <- {parent}"
            for gate, node in AUTO_GATE_DAG.items()
            if gate in preset_gates
            for parent in node.depends_on
            if parent not in preset_gates
        ]

        assert offenders == [], (
            "these edges name a predecessor that no preset ever runs: " + ", ".join(offenders)
        )

    def test_unpreset_gates_may_still_chain_among_themselves(self) -> None:
        """G4/G5 and L1-L4 keep their order for the command paths that run them."""
        for gate, parent in (("G5", "G4"), ("L2", "L1"), ("L3", "L2"), ("L4", "L3")):
            assert AUTO_GATE_DAG[gate].depends_on == (parent,)

    def test_every_edges_parent_also_appears_earlier_in_declaration_order(self) -> None:
        """Declaration order is the tie-break, so an edge must respect it."""
        order = list(AUTO_GATE_DAG)
        position = {name: index for index, name in enumerate(order)}
        for gate, node in AUTO_GATE_DAG.items():
            for parent in node.depends_on:
                assert position[parent] < position[gate], f"{parent} must be declared before {gate}"


class TestDownstreamReverseTopologicalClosure:
    """``downstream`` returns the reverse-topological closure of a gate.

    i.e. every gate that transitively depends on the given gate, in reverse
    topological order (dependencies before dependents).
    """

    def test_downstream_h0_covers_lifecycle_and_repurpose(self) -> None:
        """H0 unlocks the lifecycle track, which unlocks the repurpose track."""
        result = downstream(AUTO_GATE_DAG, "H0")
        assert result == ["L1", "L2", "L3", "L4", "P1", "P2", "P3", "P4"]
        # No copy/video gates may be downstream of H0.
        for gate in _COPY_TRACK | _VIDEO_TRACK:
            assert gate not in result, f"{gate!r} must not be downstream of H0"

    def test_downstream_v3_covers_video_then_h0(self) -> None:
        """V3 sits mid-video-track; everything after it, plus H0, must follow."""
        result = downstream(AUTO_GATE_DAG, "V3")
        assert result == [
            "V4",
            "V5",
            "V6",
            "V7",
            "H0",
            "L1",
            "L2",
            "L3",
            "L4",
            "P1",
            "P2",
            "P3",
            "P4",
        ]
        # H0 comes after the V7 chain.
        assert result.index("H0") > result.index("V7")

    def test_downstream_cw_covers_both_tracks(self) -> None:
        """CW forks into the copy track (G0..G6) and video track (V0..V7)."""
        result = downstream(AUTO_GATE_DAG, "CW")
        assert result == [
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
            "P1",
            "P2",
            "P3",
            "P4",
        ]

    def test_downstream_l4_is_empty(self) -> None:
        """L4 is the last lifecycle gate and nothing in a preset follows it.

        P1 used to depend on L4, but L4 runs only from the standalone
        ``localize`` command while P1 runs inside ``repurpose`` — so the edge
        declared a gate that can never precede P1.  P1 now depends on H0, the
        last gate both flows actually share.
        """
        assert downstream(AUTO_GATE_DAG, "L4") == []

    def test_downstream_g0_no_video_gates(self) -> None:
        """G0's subtree is copy→H0→lifecycle→repurpose; never video.

        V0 depends on CW directly, not on G0, so the video track is NOT part
        of G0's downstream closure.
        """
        result = downstream(AUTO_GATE_DAG, "G0")
        assert result == [
            "G1",
            "G2",
            "G3",
            "G4",
            "G5",
            "G6",
            "H0",
            "L1",
            "L2",
            "L3",
            "L4",
            "P1",
            "P2",
            "P3",
            "P4",
        ]
        assert not (set(result) & _VIDEO_TRACK)

    def test_downstream_g3_affected_set_in_auto_mode(self) -> None:
        """G3 failure affects G6 + H0 in auto mode, NOT video.

        The DAG closure contains G4/G5 and the lifecycle gates, but ``auto``
        presets none of them, so they are filtered out of the affected set.
        """
        result = downstream(AUTO_GATE_DAG, "G3")
        affected = [g for g in result if g in _MODE_MAP["auto"]]
        assert affected == ["G6", "H0"]
        assert not (set(affected) & _VIDEO_TRACK)  # V0 depends on CW, not G3


class TestTrackAssignment:
    """Every gate node carries a ``track``; the canonical assignment holds."""

    def test_copy_track(self) -> None:
        """CW and G0-G6 are the copy track."""
        for name in _COPY_TRACK:
            assert AUTO_GATE_DAG[name].track == "copy", name

    def test_video_track(self) -> None:
        """V0-V7 are the video track."""
        for name in _VIDEO_TRACK:
            assert AUTO_GATE_DAG[name].track == "video", name

    def test_lifecycle_track(self) -> None:
        """L1-L4 are the lifecycle track."""
        for name in _LIFECYCLE_TRACK:
            assert AUTO_GATE_DAG[name].track == "lifecycle", name

    def test_qa_track(self) -> None:
        """pre-gate, H0 and the repurpose gates are the qa track."""
        for name in _QA_TRACK:
            assert AUTO_GATE_DAG[name].track == "qa", name

    def test_every_gate_has_valid_track(self) -> None:
        """Every gate in the DAG is assigned to one canonical track."""
        valid = _COPY_TRACK | _VIDEO_TRACK | _LIFECYCLE_TRACK | _QA_TRACK
        for name, node in AUTO_GATE_DAG.items():
            assert node.track in {"copy", "video", "lifecycle", "qa"}, name
            assert name in valid, f"{name!r} is not assigned to any canonical track"

    def test_nodes_are_gate_node_instances(self) -> None:
        """Every value in the DAG is a ``GateNode``."""
        for name, node in AUTO_GATE_DAG.items():
            assert isinstance(node, GateNode), f"{name!r} is not a GateNode"


class TestFailureModeMatchesRegisteredClass:
    """DAG failure modes must agree with the auto-registered gate classes.

    The DAG is a *declarative* mirror of the existing gate classes; any drift
    between the DAG's ``failure_mode`` and the registered class's
    ``_failure_mode`` would change pipeline halt/rewrite semantics.
    """

    def test_failure_mode_matches_registry(self) -> None:
        """``AUTO_GATE_DAG[name].failure_mode`` == registered ``_failure_mode``."""
        import automedia.gates  # noqa: F401  # triggers auto-registration
        from automedia.gates.base import _registry

        for name, node in AUTO_GATE_DAG.items():
            if name not in _registry:
                pytest.skip(f"Gate {name!r} not registered in GateRegistry")
            assert node.failure_mode == _registry.get(name)._failure_mode, name


class TestDependsOnEdges:
    """Spot-check the canonical ``depends_on`` edge table."""

    def test_pre_gate_has_no_dependencies(self) -> None:
        """pre-gate is the DAG root."""
        assert AUTO_GATE_DAG["pre-gate"].depends_on == ()

    def test_cw_depends_on_pre_gate(self) -> None:
        assert AUTO_GATE_DAG["CW"].depends_on == ("pre-gate",)

    def test_g6_depends_on_the_copy_track_not_on_unpreset_g5(self) -> None:
        """G6 depends on G3, not G5.

        G5 (html_hard) is in no preset, so "G6 depends on G5" declared an
        ordering that can never happen: under present-parents semantics the
        edge was silently dropped and G6 became ready immediately.  G3 is the
        last copy gate every copy-bearing mode actually runs, so the edge now
        encodes a real predecessor.
        """
        assert AUTO_GATE_DAG["G6"].depends_on == ("G3",)

    def test_v0_depends_on_cw_and_is_parallel(self) -> None:
        """V0 runs async-parallel off CW, independent of the copy track."""
        assert AUTO_GATE_DAG["V0"].depends_on == ("CW",)
        assert AUTO_GATE_DAG["V0"].async_parallel is True

    def test_h0_depends_on_both_track_termini(self) -> None:
        """H0 joins the copy and video tracks."""
        assert AUTO_GATE_DAG["H0"].depends_on == ("G6", "V7")

    def test_l1_depends_on_h0_and_termini(self) -> None:
        assert AUTO_GATE_DAG["L1"].depends_on == ("H0", "G6", "V7")

    def test_p4_depends_on_p3(self) -> None:
        """Repurpose gates form their own chain."""
        assert AUTO_GATE_DAG["P4"].depends_on == ("P3",)

    def test_l4_depends_on_l3(self) -> None:
        assert AUTO_GATE_DAG["L4"].depends_on == ("L3",)

    def test_every_non_root_gate_has_dependencies(self) -> None:
        """Only pre-gate may have an empty ``depends_on``."""
        for name, node in AUTO_GATE_DAG.items():
            if name == "pre-gate":
                continue
            assert node.depends_on, f"{name!r} must declare depends_on"

    def test_every_dependency_references_an_existing_gate(self) -> None:
        """No dangling edges: every dependency is a node in the DAG."""
        for name, node in AUTO_GATE_DAG.items():
            for dep in node.depends_on:
                assert dep in AUTO_GATE_DAG, f"{name!r} depends on unknown gate {dep!r}"


class TestImportIsolation:
    """Metis G7: ``dag.py`` must not transitively import the runner."""

    def test_importing_dag_does_not_pull_runner(self) -> None:
        """A fresh interpreter importing only ``dag`` must not load runner.

        This keeps the DAG a standalone declarative module: importing it must
        never drag in ``automedia.pipelines.runner`` (and its heavy import
        chain) as a side effect.
        """
        code = (
            "import automedia.pipelines.dag\n"
            "import sys\n"
            "assert 'automedia.pipelines.runner' not in sys.modules, "
            "'dag transitively imports runner'"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
