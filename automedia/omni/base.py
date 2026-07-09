"""Base omni adapter — abstract interface for all omni adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseOmniAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def validate_env(self) -> bool: ...
