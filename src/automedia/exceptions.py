"""AutoMedia exception hierarchy — domain-specific errors for every subsystem.

All AutoMedia exceptions inherit from :class:`AutoMediaError`, allowing
callers to ``except AutoMediaError`` to catch any known pipeline error.
Each subsystem has its own subclass for precise catching.
"""


class AutoMediaError(Exception):
    """Base exception for all AutoMedia errors."""


class PipelineError(AutoMediaError):
    """Pipeline execution failures."""


class GateError(AutoMediaError):
    """Quality gate execution failures."""


class AdapterError(AutoMediaError):
    """Platform adapter publish failures."""


class ConfigError(AutoMediaError):
    """Configuration loading/validation failures."""


class AccountError(AutoMediaError):
    """Account/credential management failures."""
