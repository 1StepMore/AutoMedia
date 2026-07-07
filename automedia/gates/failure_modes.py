"""Failure-mode knowledge base for every pipeline gate.

Each entry documents the gate's purpose, common failure causes, and
recommended fixes — serving as a quick-reference for debugging.
"""

from __future__ import annotations

FAILURE_MODES: dict[str, dict[str, object]] = {
    "G0": {
        "description": "Fact-Check Gate — 5-step verification of content against source data (source trace, numbers, timeline, quotes, entities)",
        "common_causes": [
            "Source URL domain not found in content body",
            "Expected key numbers missing or mismatched",
            "Event dates after the source publication date",
            "Quotes from source not present verbatim in content",
            "Key entity names misspelled or missing",
        ],
        "fixes": [
            "Ensure the source URL domain appears in the generated content",
            "Verify that all key_numbers from source_data are present in content",
            "Check that all mentioned dates precede the source published_date",
            "Include verbatim quotes from source_data.quotes[]",
            "Cross-reference entity names against source_data.entities[]",
        ],
        "docstring_ref": "gates/fact_check.py",
    },
    "G1": {
        "description": "Humanizer Gate — removes AI-generated phrasing patterns to produce natural-sounding text",
        "common_causes": [
            "Output still contains 'furthermore', 'in summary', 'in the realm of' and similar AI markers",
            "Sentence structure remains overly uniform (same length, same opening patterns)",
            "Emotional tone still flat or robotic",
            "Transition phrases between paragraphs are formulaic",
        ],
        "fixes": [
            "Replace AI transition phrases with natural conversational alternatives",
            "Vary sentence length and opening word choices",
            "Inject appropriate emotional markers (exclamations, rhetorical questions)",
            "Rewrite formulaic paragraph openings with context-specific hooks",
        ],
        "docstring_ref": "gates/humanizer.py",
    },
    "G2": {
        "description": "Copy-Review Gate — structural and stylistic review of generated copy for readability and flow",
        "common_causes": [
            "Paragraphs are too long or too short consistently",
            "Inconsistent tone between sections",
            "Missing or ineffective hook in the opening",
            "Call-to-action is weak or absent",
        ],
        "fixes": [
            "Balance paragraph lengths for visual rhythm",
            "Unify tone across all sections (formal vs conversational)",
            "Strengthen the opening hook with a bold claim or question",
            "Ensure CTA is specific, actionable, and visible",
        ],
        "docstring_ref": "gates/copy_review.py",
    },
    "G3": {
        "description": "Brand CTA Gate — enforces brand-name integrity and call-to-action compliance",
        "common_causes": [
            "Brand name 壹目贯维 is written with incorrect characters (homophone errors)",
            "CTA link or QR code reference is missing from the content",
            "Brand mention frequency is below the minimum threshold",
            "CTA placement is not prominent enough (above fold or closing)",
        ],
        "fixes": [
            "Verify brand name character-by-character: 壹目贯维",
            "Ensure CTA includes actionable text and link/QR reference",
            "Increase brand mention count to at least the required frequency",
            "Move CTA to a high-visibility position (near start or end)",
        ],
        "docstring_ref": "gates/brand_cta.py",
    },
    "G4": {
        "description": "WeChat Checklist Gate — pre-publish checks specific to the WeChat Official Accounts platform",
        "common_causes": [
            "Article cover image missing or wrong aspect ratio",
            "Original author declaration not set",
            "WeChat-specific formatting issues (line spacing, font size)",
            "Preview mode shows rendering glitches",
        ],
        "fixes": [
            "Upload a 900×500 px cover image that matches the article topic",
            "Set the original author field before publishing",
            "Re-apply formatting using WeChat's built-in editor",
            "Always preview on mobile before final publish",
        ],
        "docstring_ref": "gates/wechat_checklist.py",
    },
    "G5": {
        "description": "HTML Hard Gate — validates that rendered HTML output meets structural and accessibility standards",
        "common_causes": [
            "HTML does not pass W3C validation",
            "Missing alt attributes on images",
            "Inline styles conflict with site-wide CSS",
            "Responsive layout breaks below 768 px viewport",
        ],
        "fixes": [
            "Run HTML through W3C validator and fix errors",
            "Add descriptive alt text to every <img> element",
            "Scope inline styles to avoid cascade conflicts",
            "Test layout at 375 px, 768 px, and 1920 px breakpoints",
        ],
        "docstring_ref": "gates/html_hard.py",
    },
    "V0": {
        "description": "Lint Gate — code quality checks for rendered HyperFrames HTML/JS output",
        "common_causes": [
            "JavaScript syntax error detected by ESLint or equivalent",
            "Unused variables or imports in the template",
            "Template contains hardcoded test data instead of dynamic bindings",
            "GSAP animation targets non-existent DOM elements",
        ],
        "fixes": [
            "Fix lint errors before re-rendering",
            "Remove unused imports and variables",
            "Replace hardcoded test data with template variable references",
            "Verify GSAP selectors match actual element IDs in the DOM tree",
        ],
        "docstring_ref": "gates/lint.py",
    },
    "V1": {
        "description": "Vision QA Gate — visual quality assurance for generated video frames and images",
        "common_causes": [
            "Image contains undesirable artifacts (noise, distortion, cropping)",
            "Brand name or key text is illegible in rendered frames",
            "Color palette is inconsistent across frames",
            "Aspect ratio does not match target platform (9:16 for vertical video)",
        ],
        "fixes": [
            "Re-generate images with revised prompt that avoids known artifacts",
            "Ensure brand text is large enough and high-contrast",
            "Adhere to a consistent color palette defined at composition time",
            "Verify aspect_ratio parameter matches the target format",
        ],
        "docstring_ref": "gates/vision_qa.py",
    },
    "V2": {
        "description": "Pre-Send Whisper Gate — validates Whisper ASR output before SRT generation",
        "common_causes": [
            "Whisper transcribed text has high WER (word error rate)",
            "Homophone errors in brand names and proper nouns",
            "Timestamps drift significantly from actual audio",
            "Whisper model used is too small for the audio quality",
        ],
        "fixes": [
            "Use larger Whisper model (large-v3) for better accuracy",
            "Cross-check brand names against known-correct script text",
            "Re-run Whisper with --word_timestamps True for finer alignment",
            "If audio quality is poor, pre-process with noise reduction",
        ],
        "docstring_ref": "gates/pre_send_whisper.py",
    },
    "V3": {
        "description": "Content Semantic Gate — checks semantic consistency and topic alignment of generated content",
        "common_causes": [
            "Content strays from the original topic outline",
            "Key claims are not supported by the source material",
            "Section ordering does not match the intended narrative flow",
            "Redundant or contradictory statements appear in different sections",
        ],
        "fixes": [
            "Re-align content to match the approved topic outline point by point",
            "Cite or reference source material for every key claim",
            "Re-order sections to follow the narrative arc defined during planning",
            "Remove or merge contradictory statements across sections",
        ],
        "docstring_ref": "gates/content_semantic.py",
    },
    "V4": {
        "description": "TTS Brand Asset Gate — verifies brand audio (TTS) quality and correctness",
        "common_causes": [
            "TTS audio mispronounces the brand name 壹目贯维",
            "Speaking rate (speed) is too fast or too slow",
            "Audio duration does not match the target slot timing",
            "Wrong voice ID or accent used for the target platform",
        ],
        "fixes": [
            "Use SSML phoneme tags to force correct brand pronunciation",
            "Adjust rate via SSML <prosody rate=\"…\"> or TTS API speed parameter",
            "Trim or extend script to hit the target duration window",
            "Select the appropriate voice_id from the voice library",
        ],
        "docstring_ref": "gates/tts_brand_asset.py",
    },
    "V5": {
        "description": "MP3 vs SRT Gate — cross-validates audio length against subtitle timing",
        "common_causes": [
            "Total MP3 duration is significantly shorter/longer than SRT timeline",
            "Individual subtitle segments overlap or have excessive gaps",
            "Words-per-minute exceeds the readable threshold (> 300 WPM)",
            "Audio file is corrupted or truncated",
        ],
        "fixes": [
            "Re-generate TTS audio with adjusted speed to match SRT timeline",
            "Merge overlapping segments and redistribute time budget",
            "Rewrite dense segments to reduce word count",
            "Verify MP3 integrity: ffprobe should report expected duration",
        ],
        "docstring_ref": "gates/mp3_vs_srt.py",
    },
    "V6": {
        "description": "Subtitle Render Gate — ensures subtitles are rendered correctly into the video",
        "common_causes": [
            "Subtitle text is truncated or clipped at the video edge",
            "Font size is too small to read on mobile",
            "ASS style PlayRes does not match video resolution",
            "Subtitle timing is out of sync with rendered frames",
        ],
        "fixes": [
            "Set ASS PlayResX/Y to match video resolution (e.g., 1080×1920)",
            "Increase FontSize to at least 28 for vertical 9:16 video",
            "Set margin bottom (MarginV) to 120 for safe zone",
            "Re-run render with corrected timing values",
        ],
        "docstring_ref": "gates/subtitle_render.py",
    },
    "V7": {
        "description": "Six-Step Hard Gate — final comprehensive quality gate before publish (6 checks)",
        "common_causes": [
            "One or more sub-checks in the 6-step sequence failed",
            "Generated assets are missing or at wrong paths",
            "Metadata (title, description, tags) is incomplete",
            "Cross-platform format conversion introduced artifacts",
        ],
        "fixes": [
            "Run individual sub-checks separately to identify the failing step",
            "Verify all asset files exist at expected paths",
            "Fill in missing metadata fields per platform requirements",
            "Check converted output at target resolution and format",
        ],
        "docstring_ref": "gates/six_step_hard.py",
    },
    "L1": {
        "description": "Publish Log Schema Gate — validates that the publish log entry conforms to the required schema",
        "common_causes": [
            "Required fields missing from the log entry (platform, url, timestamp)",
            "Field values are of incorrect type (e.g., timestamp is string not datetime)",
            "Publish log schema version mismatch between gate and DB",
        ],
        "fixes": [
            "Fill in all required fields before writing the log entry",
            "Type-coerce values to match the published schema definitions",
            "Migrate the publish log table to the latest schema version",
        ],
        "docstring_ref": "gates/publish_log_schema.py",
    },
    "L2": {
        "description": "Archive Validation Gate — verifies that the project archive is complete and uncorrupted",
        "common_causes": [
            "Archive ZIP file is missing or truncated",
            "Expected files are missing from the archive (MP4, SRT, cover image)",
            "File checksums do not match recorded values",
            "Archive contains stale or unrelated files",
        ],
        "fixes": [
            "Re-create the archive ensuring all output assets are included",
            "Verify archive against the manifest of expected file paths",
            "Re-compute checksums and compare with recorded values",
            "Clean the archive directory before re-packaging",
        ],
        "docstring_ref": "gates/archive_validation.py",
    },
    "L3": {
        "description": "Platform Integrity Gate — ensures the asset set is complete for every target publishing platform",
        "common_causes": [
            "Platform-specific format conversion failed (e.g., MP4 codec not supported)",
            "Required resolution variant is missing",
            "Thumbnail image not generated for video platform",
            "Caption/subtitle file is missing for the target platform",
        ],
        "fixes": [
            "Re-run format conversion using target platform's recommended codec/settings",
            "Generate all required resolution variants (1080p, 720p, 480p)",
            "Generate platform-compliant thumbnail (size, format, aspect ratio)",
            "Generate platform-specific caption file (SRT, VTT, SCC)",
        ],
        "docstring_ref": "gates/platform_integrity.py",
    },
    "pre-gate": {
        "description": "Topic Selection Gate — filters and scores candidate topics before pipeline entry",
        "common_causes": [
            "Topic score is below the minimum threshold",
            "Topic content is too similar to recently published items",
            "Topic domain is outside the channel's scope (not AI/media related)",
            "Source URL is unreachable or returns 404",
        ],
        "fixes": [
            "Re-score topic with adjusted weights or re-collect fresher data",
            "Deduplicate against the last N published topics by semantic similarity",
            "Reject topics that do not match the channel's domain keywords",
            "Retry source URL fetch or mark as dead and skip",
        ],
        "docstring_ref": "gates/topic_selection.py",
    },
}
