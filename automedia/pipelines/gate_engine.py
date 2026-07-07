"""Gate engine — stub."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class Pipeline:
    """Pipeline execution context — stub."""

    def __init__(self) -> None:
        self.results: list[PipelineResult] = []

    def run(self) -> PipelineResult:
        raise NotImplementedError
