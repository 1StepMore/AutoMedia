"""Quality gates — all concrete gate implementations are imported here for auto-registration in GateRegistry.

Gate naming convention: G0-G6 (copy), V0-V7 (video/quality), L1-L4 (lifecycle), D1-D9 (distribution),
P1-P9 (repurpose sub-pipelines), CW (content writer), pre-gate.
"""

from structlog import get_logger

log = get_logger(__name__)

# Sub-pipeline repurpose gates (P-series)
from automedia.gates.sub_pipelines import P1WechatGate
from automedia.gates.sub_pipelines import P3NewsletterGate
from automedia.gates.sub_pipelines import P4BilibiliRepurpose

# Distribution gates (D-series)
from automedia.gates.distribution import (
    D1Gate,
    D2Gate,
    D3ZhihuRewrite,
    D4Gate,
    D5BilibiliRewrite,
    D6YouTubeGate,
    D7Gate,
)

# Text-track gates (G0-G5)
from automedia.gates._context import GateContext
from automedia.gates.archive_validation import L2ArchiveValidation
from automedia.gates.brand_cta import G3BrandCTA
from automedia.gates.content_semantic import V3ContentSemantic

# Content writer gate (between pre-gate and G0)
from automedia.gates.content_writer import ContentWriterGate

# Sub-pipeline repurpose gates (P-series)
from automedia.gates.sub_pipelines.p2_twitter import P2TwitterGate
from automedia.gates.copy_review import G2CopyReview
from automedia.gates.fact_check import G0FactCheck

# HITL gates
from automedia.gates.h0_human_review import H0HumanReviewGate
from automedia.gates.g6_tone_check import G6ToneCheckGate
from automedia.gates.html_hard import G5HtmlHard
from automedia.gates.humanizer import G1Humanizer

# Video-track gates (V0-V7)
from automedia.gates.lint import V0Lint
from automedia.gates.mp3_vs_srt import V5Mp3VsSrt
from automedia.gates.platform_integrity import L3PlatformIntegrity
from automedia.gates.pre_send_whisper import V2PreSendWhisper

# Lifecycle gates (L1-L3)
from automedia.gates.publish_log_schema import L1PublishLogSchema
from automedia.gates.six_step_hard import V7SixStepHard
from automedia.gates.subtitle_render import V6SubtitleRender

# Pre-gates
from automedia.gates.topic_selection import TopicSelectionGate
from automedia.gates.translation_quality import L4TranslationQuality
from automedia.gates.tts_brand_asset import V4TTSBrandAsset
from automedia.gates.vision_qa import V1VisionQA
from automedia.gates.wechat_checklist import G4WechatChecklist

__all__ = [
    # Sub-pipeline repurpose gates
    "P1WechatGate",
    "P2TwitterGate",
    "P3NewsletterGate",
    # Distribution gates
    "D1Gate",
    "D2Gate",
    "D3ZhihuRewrite",
    "D4Gate",
    "D5BilibiliRewrite",
    "D6YouTubeGate",
    "D7Gate",
    # Repurpose gates
    "P4BilibiliRepurpose",
    # Text-track gates (G0-G6)
    "G0FactCheck",
    "G1Humanizer",
    "G2CopyReview",
    "G3BrandCTA",
    "G4WechatChecklist",
    "G5HtmlHard",
    "G6ToneCheckGate",
    # Video-track gates (V0-V7)
    "V0Lint",
    "V1VisionQA",
    "V2PreSendWhisper",
    "V3ContentSemantic",
    "V4TTSBrandAsset",
    "V5Mp3VsSrt",
    "V6SubtitleRender",
    "V7SixStepHard",
    # Lifecycle gates
    "L1PublishLogSchema",
    "L2ArchiveValidation",
    "L3PlatformIntegrity",
    "L4TranslationQuality",
    # Content writer & pre-gate
    "ContentWriterGate",
    "TopicSelectionGate",
    # HITL gate
    "H0HumanReviewGate",

    # Context
    "GateContext",
]
