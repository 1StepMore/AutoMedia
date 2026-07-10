---
title: Gate Failure Modes
description: Failure modes, diagnostics, and remediation for each Gate — based on production experience with AutoMedia.
---

# Gate Failure Modes and Remediation

This document records each Gate's failure modes, diagnostic methods, and
remediation steps. The content draws on experience accumulated from running
AutoMedia in production.

## pre-gate: Topic Selection

Topic score falls below threshold or duplicates recently published content.

**Common failure causes:**

- Topic score below minimum threshold (typically < 0.3)
- Semantic similarity with recent N published articles > 0.85
- Topic domain outside channel scope (not AI/media related)
- Source URL unreachable or returns 404

**Remediation:**

- Adjust scoring weights or re-collect updated data
- Check the recent N range in the semantic dedup library, narrow if needed
- Verify channel domain keywords are configured correctly
- Retry URL fetch or mark as dead link to skip

**Quick diagnosis:**

```bash
# View topic scores in the topic pool
automedia pool list --status pending
```

## G0: Fact Check

Five-step verification of content consistency with source data: source tracing,
data verification, timeline, citations, entities.

**Common failure causes:**

- Source URL domain not present in generated content
- Key numbers do not match source data
- Event date after source publication date (time reversal)
- Citation not present verbatim in content
- Key entity names misspelled or missing

**Remediation:**

- Ensure content includes the source URL domain (not just a link)
- Verify all `key_numbers` from `source_data` appear in the content
- Check that all mentioned dates are before the source's `published_date`
- Citations must be extracted verbatim from `source_data.quotes[]`
- Entity names must be cross-checked against `source_data.entities[]`

**Common pitfall:** The LLM sometimes "rewrites" data to produce approximate
but imprecise numbers. For example, writing "about 3%" instead of "3.2%".
The Gate flags this as a failure. Fix: force the use of exact original values.

## G1: Humanizer

Remove AI-generated traces, making the text read in a natural human writing
style.

**Common failure causes:**

- Output still contains AI marker words like "furthermore", "in summary",
  "in the realm of"
- Sentence structure too uniform (same length, same beginnings)
- Emotional tone flat or mechanical
- Transition phrases between paragraphs are formulaic

**Remediation:**

- Replace AI transition phrases with natural spoken expressions
- Vary sentence length and word choice at sentence starts
- Inject appropriate emotional markers (exclamations, rhetorical questions)
- Replace formulaic paragraph openings with context-relevant hooks

**Quick checklist:**

```
是否还有 "此外" / "值得注意的是" / "总的来说" 开头段落?
所有句子长度都在 15-25 字之间? 需要一些短句和长句混合。
情感是否中性得像百科? 需要一些态度。
```

## G2: Copy Review

Copy structure and style review, ensuring readability and flow.

**Common failure causes:**

- Paragraphs too long or too short, lacking visual rhythm
- Inconsistent tone between sections
- Opening lacks an effective hook
- CTA weak or missing

**Remediation:**

- Balance paragraph length (3-5 sentences is ideal)
- Unify tone across the entire piece (formal vs conversational)
- Strengthen the opening hook with a bold assertion or question
- Ensure the CTA is specific, actionable, and visible

## G3: Brand CTA

Brand name integrity and CTA compliance.

**Common failure causes:**

- Brand name appears with homophone typos
- CTA link or QR code reference missing
- Brand mention frequency below minimum threshold
- CTA placement not prominent enough (not at beginning or end)

**Remediation:**

- Verify the brand name character by character
- Ensure CTA includes actionable text and link/QR code reference
- Increase brand mentions to at least the required frequency
- Move CTA to high-visibility positions (near beginning or end)

**Common pitfall:** "壹目贯维" is often written by the LLM as "一目贯维" or
"壹目惯维". You must emphasize this in the prompt and do character-level
validation.

## G4: WeChat Checklist

Pre-publish checks specific to the WeChat Official Accounts platform.

**Common failure causes:**

- Cover image missing or wrong aspect ratio
- Original author declaration not set
- WeChat-specific formatting issues (line spacing, font size)
- Preview mode rendering anomalies

**Remediation:**

- Upload a 900x500 px cover image that matches the article topic
- Set the original author field before publishing
- Reapply formatting using the WeChat editor
- Always preview on mobile before publishing

## G5: HTML Hard Gate

HTML output structure and accessibility standard validation.

**Common failure causes:**

- HTML fails W3C validation
- Images missing alt attributes
- Inline styles conflicting with site CSS
- Responsive layout breaks at the 768px breakpoint

**Remediation:**

- Check HTML with W3C validator and fix errors
- Add descriptive alt text to every `<img>` element
- Scope inline styles to avoid cascade conflicts
- Test layout at 375px, 768px, and 1920px breakpoints

## V0: Lint

Code quality check for HyperFrames HTML/JS output.

**Common failure causes:**

- JavaScript syntax errors
- Unused variables or imports in templates
- Templates contain hardcoded test data instead of dynamic bindings
- GSAP animations target non-existent DOM elements

**Remediation:**

- Fix lint errors then re-render
- Remove unused imports and variables
- Replace hardcoded test data with template variable references
- Check GSAP selectors match actual DOM element IDs

## V1: Vision QA

Visual quality assurance for generated video frames and images.

**Common failure causes:**

- Images have unwanted artifacts (noise, distortion, cropping)
- Brand name or key text illegible in rendered frames
- Inconsistent color grading across frames
- Aspect ratio does not match target platform (vertical video 9:16)

**Remediation:**

- Regenerate images with modified prompts (avoid known artifacts)
- Ensure brand text is large enough with sufficient contrast
- Follow the unified color palette defined during composition
- Check the `aspect_ratio` parameter matches the target format

**Common pitfall:** When the Vision API is rate limited, it degrades to pixel
luminance analysis. The QA report will note "degraded" in the output. Accuracy
drops but the flow is not blocked.

## V2: Pre-Send Whisper

Verify the quality of Whisper ASR output.

**Common failure causes:**

- Whisper transcription WER (Word Error Rate) too high
- Homophone errors for brand names and proper nouns
- Timestamps significantly misaligned with audio
- Whisper model too small for the audio quality

**Remediation:**

- Use a larger Whisper model (large-v3) for better accuracy
- Cross-check brand names against the known correct script text
- Re-run Whisper with `--word_timestamps True` for fine alignment
- Apply noise reduction preprocessing when audio quality is poor

## V3: Content Semantic

Check semantic consistency and topic alignment of generated content.

**Common failure causes:**

- Content deviates from the original topic outline
- Key claims lack supporting source material
- Section order does not follow the narrative flow
- Duplicate or contradictory statements across sections

**Remediation:**

- Align content point by point to the approved topic outline
- Cite source material for every key claim
- Reorder sections according to the story arc defined in planning
- Merge or remove contradictory statements across sections

## V4: TTS Brand Asset

Verify brand audio (TTS) quality and correctness.

**Common failure causes:**

- TTS audio mispronounces the brand name
- Speaking rate too fast or too slow
- Audio duration does not match the target slot
- Wrong voice ID or accent used

**Remediation:**

- Use SSML phoneme tags to force correct brand pronunciation
- Adjust speaking rate via `<prosody rate="...">` or TTS API speed parameters
- Trim or extend the script to fit the target duration window
- Select the appropriate voice_id from the voice library

## V5: MP3 vs SRT

Cross-validate audio duration against subtitle timing.

**Common failure causes:**

- MP3 total duration significantly shorter/longer than SRT timeline
- Individual subtitle segments overlap or have excessive gaps
- WPM exceeds readability threshold (> 300)
- Audio file corrupted or truncated

**Remediation:**

- Adjust speaking rate and regenerate TTS audio to match SRT timeline
- Merge overlapping segments and redistribute time budget
- Rewrite dense segments to reduce word count
- Verify MP3 integrity with `ffprobe`

## V6: Subtitle Rendering

Ensure subtitles are correctly rendered into the video.

**Common failure causes:**

- Subtitle text clipped or cropped at video edges
- Font size too small to read on mobile devices
- ASS style PlayRes does not match video resolution
- Subtitle timing out of sync with rendered frames

**Remediation:**

- Set ASS PlayResX/Y to match video resolution (e.g. 1080x1920)
- Font size at least 28 (for vertical 9:16 video)
- Set bottom margin (MarginV) to 120
- Re-render with corrected timing values

## V7: Six-Step Hard Gate

Final comprehensive quality gate before publishing (6 checks).

**Common failure causes:**

- One or more of the 6 checks fail
- Generated assets missing or wrong path
- Metadata (title, description, tags) incomplete
- Cross-platform format conversion introduces artifacts

**Remediation:**

- Run sub-checks individually to locate the failing step
- Confirm all asset files exist at expected paths
- Fill in missing metadata fields per platform requirements
- Check converted output resolution and format

## L1: Publish Log Schema

Verify publish log entries conform to the required schema.

**Common failure causes:**

- Log entry missing required fields (platform, url, timestamp)
- Field value type mismatch (e.g. timestamp is string instead of datetime)
- Publish log schema version does not match the database

**Remediation:**

- Fill all required fields before writing log entries
- Type-cast values to match schema definitions
- Migrate the publish log table to the latest schema version

## L2: Archive Validation

Verify the project archive is complete and not corrupted.

**Common failure causes:**

- Archive ZIP file missing or truncated
- Expected files missing from archive (MP4, SRT, cover image)
- File checksum does not match recorded value
- Archive contains expired or irrelevant files

**Remediation:**

- Recreate the archive ensuring all output assets are included
- Validate the archive against the expected file path manifest
- Recompute checksums and compare against recorded values
- Clean the archive directory before repackaging

## L3: Platform Integrity

Ensure the asset set for each target publishing platform is complete.

**Common failure causes:**

- Platform-specific format conversion fails (e.g. MP4 codec not supported)
- Required resolution variants missing
- Video platform thumbnail not generated
- Subtitle files missing for target platform

**Remediation:**

- Re-convert using the target platform's recommended codec/settings
- Generate all required resolution variants (1080p, 720p, 480p)
- Generate platform-compatible thumbnails (size, format, aspect ratio)
- Generate platform-specific subtitle files (SRT, VTT, SCC)
