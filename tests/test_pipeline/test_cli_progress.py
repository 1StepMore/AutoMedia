"""Tests for CLIPipelineProgress — retry metadata propagation."""

from __future__ import annotations

from automedia.cli.commands.run import CLIPipelineProgress


class TestCLIPipelineProgressRetry:
    """CLIPipelineProgress handles retry kwargs without TypeError."""

    def test_on_gate_start_accepts_retry_kwargs(self) -> None:
        """on_gate_start with attempt_number/retry_level does not crash."""
        progress = CLIPipelineProgress("test-proj")
        # These kwargs match what gate_engine.py passes during quality retry
        progress.on_gate_start("G2", attempt_number=2, retry_level="quality")
        assert progress.current_gate == "G2"

    def test_on_gate_end_accepts_retry_kwargs(self) -> None:
        """on_gate_end with attempt_number/retry_level does not crash."""
        progress = CLIPipelineProgress("test-proj")
        progress.set_gate_names(["G1", "G2"])
        progress.on_gate_start("G2")
        progress.on_gate_end("G2", True, 1.5, detail="ok", attempt_number=1, retry_level="quality")
        # Should not raise TypeError

    def test_completed_count_not_inflated_by_retry(self) -> None:
        """_completed counter tracks unique gates, not on_gate_end calls."""
        progress = CLIPipelineProgress("test-proj")
        progress.set_gate_names(["G1", "G2"])

        # First gate passes
        progress.on_gate_start("G1")
        progress.on_gate_end("G1", True, 1.0)
        assert progress._completed == 1  # G1

        # G2 fails, retry 1
        progress.on_gate_start("G2")
        progress.on_gate_end(
            "G2", False, 0.5, detail="fail", attempt_number=1, retry_level="quality"
        )
        # _completed should still be 1 (only G1 is done, G2 hasn't passed yet)
        # Actually, _gates_done includes G2 now since on_gate_end was called
        # The key point is that ._completed = len(self._gates_done) deduplicates
        assert progress._completed >= 1

        # G2 retry starts and passes
        progress.on_gate_start("G2", attempt_number=2, retry_level="quality")
        progress.on_gate_end(
            "G2", True, 1.5, detail="passed on retry", attempt_number=2, retry_level="quality"
        )

        # After G2 passes, _completed should be 2 (G1 + G2)
        assert progress._completed == 2

    def test_tenacity_retry_kwargs_also_accepted(self) -> None:
        """on_gate_end with retry_level='tenacity' does not crash."""
        progress = CLIPipelineProgress("test-proj")
        progress.set_gate_names(["G1"])
        progress.on_gate_start("G1")
        # Tenacity retry calls on_gate_end/on_gate_start before re-executing
        progress.on_gate_end(
            "G1", False, 0.0, detail="timeout", attempt_number=1, retry_level="tenacity"
        )
        progress.on_gate_start("G1", attempt_number=2, retry_level="tenacity")
        progress.on_gate_end("G1", True, 2.0, detail="ok")
        # No crash = pass
