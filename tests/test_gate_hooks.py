"""Tests for GateHook protocol and GateObserver default implementation."""

from typing import Any

import pytest

from automedia.hooks.protocol import GateHook, GateObserver


class TestGateHookProtocol:
    """Structural subtyping: any object matching the protocol is a GateHook."""

    def test_before_gate_returns_none(self) -> None:
        """A conforming hook must return None from before_gate."""

        class ConcreteHook:
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                return None

            def after_gate(
                self,
                gate_name: str,
                context: dict[str, Any],
                result: dict[str, Any],
            ) -> None:
                return None

            def on_gate_failed(
                self,
                gate_name: str,
                context: dict[str, Any],
                error: Exception,
            ) -> None:
                return None

        hook = ConcreteHook()
        assert isinstance(hook, GateHook)
        assert hook.before_gate("test", {}) is None

    def test_after_gate_returns_none(self) -> None:
        """A conforming hook must return None from after_gate."""

        class ConcreteHook:
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                return None

            def after_gate(
                self,
                gate_name: str,
                context: dict[str, Any],
                result: dict[str, Any],
            ) -> None:
                return None

            def on_gate_failed(
                self,
                gate_name: str,
                context: dict[str, Any],
                error: Exception,
            ) -> None:
                return None

        hook = ConcreteHook()
        assert isinstance(hook, GateHook)
        assert hook.after_gate("test", {}, {"status": "ok"}) is None

    def test_on_gate_failed_returns_none(self) -> None:
        """A conforming hook must return None from on_gate_failed."""

        class ConcreteHook:
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                return None

            def after_gate(
                self,
                gate_name: str,
                context: dict[str, Any],
                result: dict[str, Any],
            ) -> None:
                return None

            def on_gate_failed(
                self,
                gate_name: str,
                context: dict[str, Any],
                error: Exception,
            ) -> None:
                return None

        hook = ConcreteHook()
        assert isinstance(hook, GateHook)
        assert hook.on_gate_failed("test", {}, RuntimeError("fail")) is None

    def test_isinstance_check_runtime(self) -> None:
        """@runtime_checkable enables isinstance check for conforming objects."""

        class GoodHook:
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                pass

            def after_gate(
                self,
                gate_name: str,
                context: dict[str, Any],
                result: dict[str, Any],
            ) -> None:
                pass

            def on_gate_failed(
                self,
                gate_name: str,
                context: dict[str, Any],
                error: Exception,
            ) -> None:
                pass

        assert isinstance(GoodHook(), GateHook)

    def test_isinstance_rejects_incomplete_object(self) -> None:
        """An object missing required methods is NOT a GateHook."""

        class BadHook:
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                pass

            # missing after_gate and on_gate_failed

        assert not isinstance(BadHook(), GateHook)


class TestGateObserver:
    """GateObserver provides default no-op implementations."""

    def test_isinstance_gate_hook(self) -> None:
        """GateObserver must satisfy the GateHook protocol."""
        assert isinstance(GateObserver(), GateHook)

    def test_before_gate_returns_none(self) -> None:
        """Default before_gate returns None."""
        assert GateObserver().before_gate("my_gate", {"key": "val"}) is None

    def test_after_gate_returns_none(self) -> None:
        """Default after_gate returns None."""
        assert GateObserver().after_gate("my_gate", {"key": "val"}, {"ok": True}) is None

    def test_on_gate_failed_returns_none(self) -> None:
        """Default on_gate_failed returns None."""
        assert GateObserver().on_gate_failed("my_gate", {"key": "val"}, ValueError("bad")) is None

    def test_subclass_can_override_single_method(self) -> None:
        """Users should be able to subclass GateObserver and override only what they need."""

        class MyHook(GateObserver):
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                self.called = True
                return super().before_gate(gate_name, context)

        hook = MyHook()
        assert isinstance(hook, GateHook)
        hook.before_gate("x", {})
        assert hook.called
        # Unoverridden methods still work
        assert hook.after_gate("x", {}, {}) is None
        assert hook.on_gate_failed("x", {}, Exception()) is None


class TestContextAndResultPassing:
    """Verify that context, result, and error values are correctly forwarded."""

    def test_context_passed_to_before_gate(self) -> None:
        """before_gate receives the exact context dict."""

        class CaptureHook:
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                self.ctx = context

            def after_gate(
                self,
                gate_name: str,
                context: dict[str, Any],
                result: dict[str, Any],
            ) -> None:
                pass

            def on_gate_failed(
                self,
                gate_name: str,
                context: dict[str, Any],
                error: Exception,
            ) -> None:
                pass

        hook = CaptureHook()
        ctx = {"user": "alice", "role": "admin"}
        hook.before_gate("auth", ctx)
        assert hook.ctx is ctx
        assert hook.ctx == {"user": "alice", "role": "admin"}

    def test_context_and_result_passed_to_after_gate(self) -> None:
        """after_gate receives the exact context and result dicts."""

        class CaptureHook:
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                pass

            def after_gate(
                self,
                gate_name: str,
                context: dict[str, Any],
                result: dict[str, Any],
            ) -> None:
                self.ctx = context
                self.res = result

            def on_gate_failed(
                self,
                gate_name: str,
                context: dict[str, Any],
                error: Exception,
            ) -> None:
                pass

        hook = CaptureHook()
        ctx = {"phase": "build"}
        res = {"status": "passed", "duration_ms": 42}
        hook.after_gate("build", ctx, res)
        assert hook.ctx is ctx
        assert hook.res is res

    def test_context_and_error_passed_to_on_gate_failed(self) -> None:
        """on_gate_failed receives the exact context and exception."""

        class CaptureHook:
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                pass

            def after_gate(
                self,
                gate_name: str,
                context: dict[str, Any],
                result: dict[str, Any],
            ) -> None:
                pass

            def on_gate_failed(
                self,
                gate_name: str,
                context: dict[str, Any],
                error: Exception,
            ) -> None:
                self.ctx = context
                self.err = error

        hook = CaptureHook()
        ctx = {"attempt": 3}
        err = ConnectionError("timeout")
        hook.on_gate_failed("connect", ctx, err)
        assert hook.ctx is ctx
        assert hook.err is err

    @pytest.mark.parametrize(
        "method, args",
        [
            ("before_gate", ("g", {})),
            ("after_gate", ("g", {}, {"r": 1})),
            ("on_gate_failed", ("g", {}, ValueError("x"))),
        ],
        ids=["before_gate", "after_gate", "on_gate_failed"],
    )
    def test_all_methods_return_none(self, method: str, args: tuple[Any, ...]) -> None:
        """All three GateHook methods must return None."""

        class FullHook:
            def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
                return None

            def after_gate(
                self,
                gate_name: str,
                context: dict[str, Any],
                result: dict[str, Any],
            ) -> None:
                return None

            def on_gate_failed(
                self,
                gate_name: str,
                context: dict[str, Any],
                error: Exception,
            ) -> None:
                return None

        hook = FullHook()
        assert getattr(hook, method)(*args) is None
