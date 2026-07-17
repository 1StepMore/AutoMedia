from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

__all__ = [
    "PipelineMode",
    "ResearchPattern",
    "EngineModality",
    "TopicStatus",
    "GateName",
    "RetryLevel",
    "NonEmptyStr",
    "CronExpression",
    "ProjectStatusFilter",
]

PipelineMode = Literal[
    "auto",
    "text_only",
    "text_with_cover",
    "video_only",
    "qa_only",
    "image-carousel",
    "social-thread",
    "short-video",
]

ResearchPattern = Literal["a", "b"]

EngineModality = Literal["tts", "asr", "image", "video"]

TopicStatus = Literal["pending", "selected", "published", "archived"]

GateName = Literal[
    "pre-gate",
    "CW",
    "G0",
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
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
]

RetryLevel = Literal["quality", "tenacity", "manual"]

NonEmptyStr = Annotated[str, Field(min_length=1)]

CronExpression = Annotated[str, Field(pattern=r"^(\S+\s+){4}\S+$")]

ProjectStatusFilter = Literal["published", "archived", "failed", ""]
