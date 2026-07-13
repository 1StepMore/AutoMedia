"""Quality gates — all concrete gate implementations are imported here for auto-registration in GateRegistry.

Gate naming convention: G0-G5 (copy), V0-V7 (video/quality), L1-L4 (lifecycle), CW (content writer), pre-gate.
"""

# Text-track gates (G0-G5)
from automedia.gates._context import GateContext  # noqa: F401
from automedia.gates.archive_validation import L2ArchiveValidation  # noqa: F401
from automedia.gates.brand_cta import G3BrandCTA  # noqa: F401
from automedia.gates.content_semantic import V3ContentSemantic  # noqa: F401

# Content writer gate (between pre-gate and G0)
from automedia.gates.content_writer import ContentWriterGate  # noqa: F401
from automedia.gates.copy_review import G2CopyReview  # noqa: F401
from automedia.gates.fact_check import G0FactCheck  # noqa: F401
from automedia.gates.html_hard import G5HtmlHard  # noqa: F401
from automedia.gates.humanizer import G1Humanizer  # noqa: F401

# Video-track gates (V0-V7)
from automedia.gates.lint import V0Lint  # noqa: F401
from automedia.gates.mp3_vs_srt import V5Mp3VsSrt  # noqa: F401
from automedia.gates.platform_integrity import L3PlatformIntegrity  # noqa: F401
from automedia.gates.pre_send_whisper import V2PreSendWhisper  # noqa: F401

# Lifecycle gates (L1-L3)
from automedia.gates.publish_log_schema import L1PublishLogSchema  # noqa: F401
from automedia.gates.six_step_hard import V7SixStepHard  # noqa: F401
from automedia.gates.subtitle_render import V6SubtitleRender  # noqa: F401

# Pre-gates
from automedia.gates.topic_selection import TopicSelectionGate  # noqa: F401
from automedia.gates.translation_quality import L4TranslationQuality  # noqa: F401
from automedia.gates.tts_brand_asset import V4TTSBrandAsset  # noqa: F401
from automedia.gates.vision_qa import V1VisionQA  # noqa: F401
from automedia.gates.wechat_checklist import G4WechatChecklist  # noqa: F401
