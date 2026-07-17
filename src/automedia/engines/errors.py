"""Engine exception classes for the engine abstraction layer.

Provides a custom exception hierarchy for engine lifecycle errors:

- EngineNotFoundError: engine not registered for a modality
- EngineExecutionError: runtime failure during engine execution
- EngineUnavailableError: check_available() dependency check failed
"""

from __future__ import annotations

__all__ = [
    "EngineNotFoundError",
    "EngineExecutionError",
    "EngineUnavailableError",
]


class EngineNotFoundError(KeyError):
    """Raised when an engine is not registered for a modality.

    Attributes:
        engine_name: Name of the engine that was requested.
        modality: Modality the engine was requested for (e.g. 'tts', 'asr').
        available: Optional comma-separated list of available engines.
    """

    def __init__(self, engine_name: str, modality: str, available: str = "") -> None:
        self.engine_name = engine_name
        self.modality = modality
        self.available = available
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        msg = (
            f"Engine '{self.engine_name}' not found for modality "
            f"'{self.modality}'."
        )
        if self.available:
            msg += f" Available: {self.available}"
        return msg

    def __str__(self) -> str:
        return self._format_message()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(engine_name={self.engine_name!r}, modality={self.modality!r}, "
            f"available={self.available!r})"
        )


class EngineExecutionError(RuntimeError):
    """Raised when engine execution fails at runtime.

    Attributes:
        engine_name: Name of the engine that failed.
        details: Human-readable description of the failure.
        cause: Optional original exception that caused this error.
    """

    def __init__(
        self, engine_name: str, details: str, cause: Exception | None = None
    ) -> None:
        self.engine_name = engine_name
        self.details = details
        self.cause = cause
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        return f"Engine '{self.engine_name}' execution failed: {self.details}"

    def __str__(self) -> str:
        return self._format_message()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(engine_name={self.engine_name!r}, details={self.details!r}, "
            f"cause={self.cause!r})"
        )


class EngineUnavailableError(EngineExecutionError):
    """Raised when check_available() determines an engine is not usable.

    Includes installation guidance in the message.

    Attributes:
        engine_name: Name of the engine that is unavailable.
        reason: Why the engine is unavailable (e.g. CLI not found).
        install_hint: Installation command or instructions.
    """

    def __init__(self, engine_name: str, reason: str, install_hint: str) -> None:
        self.reason = reason
        self.install_hint = install_hint
        # EngineExecutionError.__init__ sets self.engine_name and self.details;
        # self._format_message() resolves to our override via MRO.
        super().__init__(engine_name=engine_name, details=reason)

    def _format_message(self) -> str:
        return (
            f"Engine '{self.engine_name}' unavailable: {self.reason}. "
            f"Install: {self.install_hint}"
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(engine_name={self.engine_name!r}, reason={self.reason!r}, "
            f"install_hint={self.install_hint!r})"
        )
