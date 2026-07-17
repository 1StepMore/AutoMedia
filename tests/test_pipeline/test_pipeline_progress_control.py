"""Tests for PipelineProgress control methods — cancel, pause, resume, retry, skip.

Scenarios
---------
1. cancel() sets _cancelled = True and unblocks paused event
2. pause() clears the paused event
3. resume() sets the paused event
4. is_cancelled() returns True after cancel
5. is_paused() returns True after pause, False after resume
6. wait_if_paused() blocks while paused, returns False if cancelled
7. mark_retry_gate / consume_retry_gate round-trip
8. mark_skip_gate / consume_skip_gate round-trip
9. consume_retry_gate clears the flag (idempotent consume)
10. consume_skip_gate clears the flag (idempotent consume)
11. Thread safety: concurrent calls from multiple threads
12. Fresh PipelineProgress starts not paused, not cancelled
"""

from __future__ import annotations

import threading

from automedia.pipelines.gate_engine import PipelineProgress

# =====================================================================
# Cancel
# =====================================================================


class TestCancel:
    """PipelineProgress.cancel() behaviour."""

    def test_cancel_sets_flag(self) -> None:
        """cancel() sets _cancelled = True."""
        progress = PipelineProgress()
        assert progress._cancelled is False
        progress.cancel()
        assert progress._cancelled is True

    def test_cancel_unblocks_paused_event(self) -> None:
        """cancel() sets the paused event so wait_if_paused() unblocks."""
        progress = PipelineProgress()
        progress.pause()
        assert not progress._paused_event.is_set()

        progress.cancel()
        assert progress._paused_event.is_set()

    def test_is_cancelled_true_after_cancel(self) -> None:
        """is_cancelled() returns True after cancel()."""
        progress = PipelineProgress()
        assert progress.is_cancelled() is False
        progress.cancel()
        assert progress.is_cancelled() is True

    def test_is_cancelled_false_by_default(self) -> None:
        """Fresh PipelineProgress is not cancelled."""
        progress = PipelineProgress()
        assert progress.is_cancelled() is False

    def test_cancel_idempotent(self) -> None:
        """Calling cancel() multiple times is safe."""
        progress = PipelineProgress()
        progress.cancel()
        progress.cancel()
        progress.cancel()
        assert progress.is_cancelled() is True


# =====================================================================
# Pause / Resume
# =====================================================================


class TestPauseResume:
    """PipelineProgress.pause() and resume() behaviour."""

    def test_pause_clears_event(self) -> None:
        """pause() clears the internal paused event."""
        progress = PipelineProgress()
        assert progress._paused_event.is_set()  # not paused by default
        progress.pause()
        assert not progress._paused_event.is_set()

    def test_resume_sets_event(self) -> None:
        """resume() sets the internal paused event."""
        progress = PipelineProgress()
        progress.pause()
        assert not progress._paused_event.is_set()

        progress.resume()
        assert progress._paused_event.is_set()

    def test_is_paused_true_after_pause(self) -> None:
        """is_paused() returns True after pause()."""
        progress = PipelineProgress()
        progress.pause()
        assert progress.is_paused() is True

    def test_is_paused_false_after_resume(self) -> None:
        """is_paused() returns False after resume()."""
        progress = PipelineProgress()
        progress.pause()
        assert progress.is_paused() is True

        progress.resume()
        assert progress.is_paused() is False

    def test_is_paused_false_by_default(self) -> None:
        """Fresh PipelineProgress is not paused."""
        progress = PipelineProgress()
        assert progress.is_paused() is False

    def test_pause_resume_cycle(self) -> None:
        """Multiple pause/resume cycles work correctly."""
        progress = PipelineProgress()
        for _ in range(3):
            assert progress.is_paused() is False
            progress.pause()
            assert progress.is_paused() is True
            progress.resume()
            assert progress.is_paused() is False

    def test_wait_if_paused_blocks_while_paused(self) -> None:
        """wait_if_paused() blocks when paused, returns True when resumed."""
        progress = PipelineProgress()
        progress.pause()

        results: list[bool] = []

        def waiter() -> None:
            results.append(progress.wait_if_paused())

        t = threading.Thread(target=waiter)
        t.start()

        # Give the thread a moment to block on the event
        import time

        time.sleep(0.05)
        assert len(results) == 0  # still blocked

        progress.resume()
        t.join(timeout=2.0)
        assert len(results) == 1
        assert results[0] is True  # not cancelled, so returns True


# =====================================================================
# Cancel while paused
# =====================================================================


class TestCancelWhilePaused:
    """Cancel interaction with pause."""

    def test_wait_if_paused_returns_false_when_cancelled(self) -> None:
        """wait_if_paused() returns False if pipeline is cancelled during wait."""
        progress = PipelineProgress()
        progress.pause()

        results: list[bool] = []

        def waiter() -> None:
            results.append(progress.wait_if_paused())

        t = threading.Thread(target=waiter)
        t.start()

        import time

        time.sleep(0.05)
        assert len(results) == 0  # still blocked

        progress.cancel()  # cancel also sets the paused event
        t.join(timeout=2.0)
        assert len(results) == 1
        assert results[0] is False  # cancelled, returns False

    def test_is_cancelled_true_after_cancel_while_paused(self) -> None:
        """is_cancelled() returns True when cancelled while paused."""
        progress = PipelineProgress()
        progress.pause()
        progress.cancel()
        assert progress.is_cancelled() is True
        assert progress.is_paused() is False  # cancel set the event


# =====================================================================
# Retry gate
# =====================================================================


class TestRetryGate:
    """mark_retry_gate / consume_retry_gate."""

    def test_mark_retry_gate_sets_flag(self) -> None:
        """mark_retry_gate stores the gate name."""
        progress = PipelineProgress()
        assert progress._retry_gate is None
        progress.mark_retry_gate("G0")
        assert progress._retry_gate == "G0"

    def test_consume_retry_gate_returns_flag(self) -> None:
        """consume_retry_gate returns the previously stored gate name."""
        progress = PipelineProgress()
        progress.mark_retry_gate("G1")
        assert progress.consume_retry_gate() == "G1"

    def test_consume_retry_gate_clears_flag(self) -> None:
        """After consume_retry_gate, the flag is None again."""
        progress = PipelineProgress()
        progress.mark_retry_gate("G2")
        progress.consume_retry_gate()
        assert progress._retry_gate is None

    def test_consume_retry_gate_idempotent(self) -> None:
        """Second consume returns None."""
        progress = PipelineProgress()
        progress.mark_retry_gate("G3")
        assert progress.consume_retry_gate() == "G3"
        assert progress.consume_retry_gate() is None

    def test_consume_retry_gate_default_none(self) -> None:
        """consume_retry_gate returns None when no gate was marked."""
        progress = PipelineProgress()
        assert progress.consume_retry_gate() is None

    def test_mark_retry_gate_overwrites_previous(self) -> None:
        """Marking a new retry gate overwrites the previous one."""
        progress = PipelineProgress()
        progress.mark_retry_gate("G0")
        progress.mark_retry_gate("G1")
        assert progress.consume_retry_gate() == "G1"


# =====================================================================
# Skip gate
# =====================================================================


class TestSkipGate:
    """mark_skip_gate / consume_skip_gate."""

    def test_mark_skip_gate_sets_flag(self) -> None:
        """mark_skip_gate stores the gate name."""
        progress = PipelineProgress()
        assert progress._skip_gate is None
        progress.mark_skip_gate("V0")
        assert progress._skip_gate == "V0"

    def test_consume_skip_gate_returns_flag(self) -> None:
        """consume_skip_gate returns the previously stored gate name."""
        progress = PipelineProgress()
        progress.mark_skip_gate("V1")
        assert progress.consume_skip_gate() == "V1"

    def test_consume_skip_gate_clears_flag(self) -> None:
        """After consume_skip_gate, the flag is None again."""
        progress = PipelineProgress()
        progress.mark_skip_gate("V2")
        progress.consume_skip_gate()
        assert progress._skip_gate is None

    def test_consume_skip_gate_idempotent(self) -> None:
        """Second consume returns None."""
        progress = PipelineProgress()
        progress.mark_skip_gate("V3")
        assert progress.consume_skip_gate() == "V3"
        assert progress.consume_skip_gate() is None

    def test_consume_skip_gate_default_none(self) -> None:
        """consume_skip_gate returns None when no gate was marked."""
        progress = PipelineProgress()
        assert progress.consume_skip_gate() is None


# =====================================================================
# Combined retry and skip — independent flags
# =====================================================================


class TestCombinedRetrySkip:
    """Retry and skip flags are independent."""

    def test_retry_and_skip_can_coexist(self) -> None:
        """Setting retry and skip independently works."""
        progress = PipelineProgress()
        progress.mark_retry_gate("G0")
        progress.mark_skip_gate("V0")
        assert progress.consume_retry_gate() == "G0"
        assert progress.consume_skip_gate() == "V0"

    def test_retry_does_not_affect_skip(self) -> None:
        """Setting retry does not change skip."""
        progress = PipelineProgress()
        progress.mark_retry_gate("G0")
        assert progress._skip_gate is None
        progress.mark_skip_gate("V0")
        assert progress._retry_gate == "G0"
        assert progress._skip_gate == "V0"


# =====================================================================
# Thread safety
# =====================================================================


class TestThreadSafety:
    """Concurrent access does not corrupt PipelineProgress state."""

    def test_concurrent_cancel_pause_resume(self) -> None:
        """Multiple threads calling cancel/pause/resume concurrently."""
        progress = PipelineProgress()
        errors: list[Exception] = []
        lock = threading.Lock()

        def hammer() -> None:
            for _ in range(100):
                try:
                    progress.cancel()
                    progress.pause()
                    progress.resume()
                    progress.is_cancelled()
                    progress.is_paused()
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(exc)

        threads = [threading.Thread(target=hammer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Thread safety violations: {errors}"

    def test_concurrent_retry_skip(self) -> None:
        """Multiple threads calling mark/consume concurrently."""
        progress = PipelineProgress()
        errors: list[Exception] = []
        lock = threading.Lock()

        def writer() -> None:
            for i in range(100):
                try:
                    progress.mark_retry_gate(f"G{i % 10}")
                    progress.mark_skip_gate(f"V{i % 10}")
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(exc)

        def reader() -> None:
            for _ in range(100):
                try:
                    progress.consume_retry_gate()
                    progress.consume_skip_gate()
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(5)] + [
            threading.Thread(target=reader) for _ in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"Thread safety violations: {errors}"

    def test_concurrent_wait_if_paused(self) -> None:
        """Multiple threads blocked on wait_if_paused all unblock correctly."""
        progress = PipelineProgress()
        results: list[bool] = []
        lock = threading.Lock()

        progress.pause()

        def waiter() -> None:
            r = progress.wait_if_paused()
            with lock:
                results.append(r)

        threads = [threading.Thread(target=waiter) for _ in range(10)]
        for t in threads:
            t.start()

        import time

        time.sleep(0.05)
        assert len(results) == 0  # all still blocked

        progress.resume()
        for t in threads:
            t.join(timeout=2.0)

        assert len(results) == 10
        assert all(results)  # all returned True (not cancelled)
