# AutoMedia — Coverage Gaps

> **Automated content production dimensions NOT covered by the current pipeline.**
> Last updated: 2026-07-12

This document lists capabilities and dimensions that are **absent from AutoMedia's current implementation**. It serves as a gap analysis for contributors, a roadmap input, and a reference for AI agents entering the codebase.

> **📌 Note:** This document is **superseded** by `docs/project-audit.md`, which provides a more comprehensive and up-to-date audit of the entire codebase. New contributors should start with `docs/project-audit.md`. **Section 1.4 has been updated** to reflect PRD-4's implementation — all other sections remain accurate as of the last-updated date.

---

## Table of Contents

1. [High Priority (pipeline blockers)](#1-high-priority)
2. [Medium Priority (feature-complete gaps)](#2-medium-priority)
3. [Low Priority (nice-to-have)](#3-low-priority)
4. [Stub / Placeholder Gaps Within Existing Code](#4-stub--placeholder-gaps-within-existing-code)
5. [Architecture Gaps (ADRs accepted but not done)](#5-architecture-gaps)
6. [Summary Table](#6-summary-table)

---

## 1. High Priority

These are capabilities that the pipeline claims or implies it has, but does **not** actually deliver.

### 1.1 Video Synthesis & Rendering

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | The pipeline has **no actual video generation or assembly engine**. `ImagePipeline` produces only **static PNG images** (covers, body images, fallback frames) via ComfyUI. There is no: |
| | • AI video generation (Runway, Pika, Sora, or any text-to-video model) |
| | • FFmpeg-based scene stitching or transitions |
| | • Background music overlay |
| | • Opening/ending credits assembly |
| | • Motion graphics or animation rendering |
| **Impact** | The `auto` and `video_only` pipeline modes depend on an external HyperFrames rendering step that is **not part of this repository**. The project validates videos but cannot produce them. |
| **Related gates** | V0 (lint), V1 (vision QA), V6 (subtitle render), V7 (six-step hard) — all validate but don't generate |
| **Upstream dependency** | ComfyUI (optional, for images only); Bun + HyperFrames (external JS rendering, not in repo) |
| **Suggested approach** | Integrate an AI video model API (e.g., Runway Gen-3, Pika, Kling) or implement FFmpeg-based assembly with subtitle overlay, BGM, and transitions. |

### 1.2 International Social Media Publishing

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | Real API-based adapters for the following platforms (configured in `defaults.yaml` and `onboard.py` but **no adapter class exists**): |
| | • **YouTube** — referenced in `publish_log_schema.py`, `onboard.py`, `defaults.yaml`; no adapter |
| | • **TikTok** — referenced in `onboard.py`, `defaults.yaml`; no adapter |
| | • **Twitter / X** — referenced in `publish_log_schema.py`, `onboard.py`, `defaults.yaml`; no adapter |
| | Platforms not even referenced but industry-standard: **Instagram**, **Facebook**, **LinkedIn** |
| **Impact** | Publishing is limited to Chinese platforms (WeChat, Zhihu) plus a Feishu notification webhook. The project cannot publish to any global platform. |
| **Existing pattern** | Follow `BasePlatformAdapter` in `src/automedia/adapters/base.py` and register in `src/automedia/adapters/__init__.py` |
| **Platform references** | `src/automedia/gates/publish_log_schema.py` (L1 valid_platforms enum), `src/automedia/cli/commands/onboard.py` (onboarding config), `src/automedia/manifests/defaults.yaml` (default platform configs) |

### 1.3 Topic Collection (Real API Integration)

| | |
|---|---|
| **Status** | ⚠️ Simulated only |
| **What's missing** | `HotCollector` in `src/automedia/pool/collector.py` returns **synthetic/hardcoded data** for all sources: |
| | • Weibo (微博) — simulated hot-search topics |
| | • Zhihu (知乎) — simulated hot-search topics |
| | • Douyin (抖音) — simulated hot-search topics |
| | • Bilibili (哔哩哔哩) — simulated hot-search topics |
| | • Tavily AI Search — simulated results |
| | • AIHOT Aggregator — simulated feed |
| **Impact** | Cannot collect real trending topics in production. The topic pool is populated with fake data. |
| **Suggested approach** | Replace each `_collect_*` method with real API calls (or web scraping where APIs don't exist). The `scorer.py` and `dedup.py` are production-ready. |

### 1.4 Agent Account & Social Media Session Management

| | |
|---|---|
| **Status** | ✅ Implemented (PRD-4, v2.0-alpha) |
| **What was built** | The PRD-4 Account Management subsystem is fully implemented in `src/automedia/accounts/`: |
| | • **Encrypted credential store** (`store.py`) — AES-256-GCM encryption per-platform credentials, master key derived from `AUTOMEDIA_MASTER_KEY` via SHA-256 |
| | • **Account registry** (`registry.py`) — Multi-account CRUD per platform with label uniqueness enforcement, health status tracking |
| | • **Auth flow engine** (`auth/oauth2.py`, `auth/flows.py`) — OAuth2 authorization_code + PKCE, OAuth2 client_credentials, CookieAuthFlow, APIKeyAuthFlow |
| | • **Session manager** (`session.py`) — TTL-aware token cache with concurrency locks, rate-limit backoff, health monitoring |
| | • **Pydantic v2 models** (`models.py`) — Account, Credential, SessionToken with field-level encryption and masked repr |
| | • **4 MCP tools** (`mcp/accounts.py`) — `connect_account`, `list_accounts`, `get_account_health`, `disconnect_account` |
| | • **5 CLI commands** (`cli/commands/account.py`) — `account connect`, `account list`, `account health`, `account disconnect`, `account refresh` |
| | • **191 tests** — all passing, included in CI |
| **Remaining gaps** | While the core auth infrastructure is production-ready, these agent-facing features remain: |
| | • **Browser automation** — no Playwright-based login for platforms without APIs (Xiaohongshu). Stub remains in `xiaohongshu_publisher.py`. |
| | • **Account analytics dashboard** — no MCP resource or CLI command for aggregate health overview |
| | • **Post-publish analytics** — `get_analytics()` still returns `"not_implemented"` on all platform adapters |
| **Impact** | The core account infrastructure no longer blocks autonomous agent operation. Agents can register, authenticate, and manage multiple platform accounts programmatically. Remaining gaps are around browser-automation-only platforms (Xiaohongshu) and the analytics feedback loop. |
| **Location** | `src/automedia/accounts/` (new subsystem), `src/automedia/mcp/accounts.py` (MCP tools), `src/automedia/cli/commands/account.py` (CLI commands) |
| **Related docs** | `docs/project-audit.md §2.5` (account layer in architecture), `docs/project-audit.md §4` (OAuth2/AES rows in maturity matrix) |

---

## 2. Medium Priority

These are capabilities that would meaningfully extend the pipeline's value but don't block core functionality.

### 2.1 Content Repurposing

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No automatic content repurposing across formats: |
| | • Long-form article → short social posts (no summarization / excerpt extraction) |
| | • Video script → blog post (no transcript-to-article) |
| | • Podcast → article + social snippets (no audio-to-text-to-publish) |
| | • Platform-specific content adaptation (same topic, different tone/length per platform) |
| **Impact** | Each platform requires a separate pipeline run. The same content cannot be automatically adapted for WeChat (long-form) vs Twitter (short) vs Xiaohongshu (image-centric). |

### 2.2 Post-Publish Analytics

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No analytics or performance tracking after publishing: |
| | • Read/play counts per platform |
| | • Engagement metrics (likes, comments, shares) |
| | • Cross-platform performance comparison |
| | • Content score / ROI calculation |
| **Impact** | No feedback loop to improve content strategy. Publishing is a one-way fire-and-forget operation. |

### 2.3 Decision Layer — LLM Integration

| | |
|---|---|
| **Status** | ⚠️ Partial (deterministic only) |
| **What's missing** | All 11 decision agents (`DecisionOrchestrator`) are **deterministic templates with no LLM calls**. They produce structured artifacts using hardcoded logic rather than AI analysis. The production E2E test design doc explicitly notes: *"Current Decision Agents are deterministic (no LLM calls)"*. |
| **Affected agents** | `BrandPositioningAgent`, `MarketResearchAgent`, `AudienceSegmentationAgent`, `CompetitorAnalysisAgent`, `BrandHealthDiagnosisAgent`, `MarketRevalidationAgent`, `AudienceDeepeningAgent`, `CompetitorTrackingAgent`, `ContentAssetAuditAgent`, `ProductOptimizationAgent`, `ContentMarketingAgent` |
| **Impact** | The Decision Layer produces template-based outputs that lack the depth and nuance promised by the architecture docs. |
| **Location** | `src/automedia/decision/build/`, `src/automedia/decision/scale/`, `src/automedia/decision/strategy/` |

### 2.4 Voice Cloning & Custom TTS

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | Only Microsoft Edge TTS (fixed set of standard voices) is supported: |
| | • No voice cloning (ElevenLabs, Fish Audio, CosyVoice) |
| | • No custom voice training |
| | • No multi-emotion TTS |
| | • No voice parameter fine-tuning beyond speed |
| **Impact** | All TTS output uses Microsoft's standard voices, limiting brand differentiation for audio/video content. |
| **Location** | `src/automedia/pipelines/audio_pipeline.py` — single edge-tts implementation |

---

## 3. Low Priority

These are nice-to-have capabilities that extend the platform's reach but are not critical to the core pipeline.

### 3.1 Blog / Website Publishing

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No adapters for: WordPress, Medium, Substack, Notion, or custom website CMS APIs. |
| **Rationale** | The project focuses on Chinese social media + Feishu notification. Website publishing can be added via the existing adapter pattern. |

### 3.2 Email / Newsletter Marketing

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No email delivery (SendGrid, AWS SES, Mailchimp), no newsletter platform integration, no subscriber management. |

### 3.3 Podcast Production

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No podcast-specific features: |
| | • Chapter markers / chapters |
| | • RSS feed generation |
| | • Distribution to Apple Podcasts / Spotify |
| | • Show notes generation |
| **Rationale** | The TTS pipeline produces MP3 but no podcast metadata or distribution logic. |

### 3.4 Background Music & Sound Effects

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No AI background music generation, no sound effects library, no multi-track audio mixing. |

### 3.5 SEO & Search Engine Optimization

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No SEO keyword analysis, no meta description generation, no structured data (Schema.org) output, no sitemap generation. |

### 3.6 Platform-Specific Thumbnails

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | The pipeline generates cover images in 4 aspect ratios but: |
| | • No YouTube thumbnail (1280×720 with text overlay) |
| | • No Instagram-optimized square/portrait crops |
| | • No platform-specific branding or text overlays |
| | • No A/B thumbnail variants |

### 3.7 Content A/B Testing

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No systematic A/B testing: no title variants, no cover image variants, no publishing time optimization, no performance comparison. |

### 3.8 Team Collaboration

| | |
|---|---|
| **Status** | ❌ Basic only |
| **What's missing** | Beyond single-user HITL (approve/skip), there is no: |
| | • Multi-user content review workflows |
| | • Role-based content approval chains |
| | • Real-time collaborative editing |
| | • Commenting / annotation on drafts |
| | • Visual content calendar UI |

### 3.9 Image / Video Content Moderation

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No NSFW detection, no violent content filtering, no politically sensitive image detection, no automated moderation before publishing. |

### 3.10 Podcast / Audio Content Distribution

| | |
|---|---|
| **Status** | ❌ Not implemented |
| **What's missing** | No automatic distribution to Apple Podcasts, Google Podcasts, Spotify, Ximalaya (喜马拉雅), or any audio platform API. |

---

## 4. Stub / Placeholder Gaps Within Existing Code

These are documented gaps **inside already-implemented modules** that need completion.

| Module | What's missing | File | Line |
|--------|---------------|------|------|
| **OL quality judge** | `judge()` always returns `{"score": 1.0, "feedback": "Auto-approved (stub)"}` | `src/automedia/omni/ol_adapter.py` | 179 |
| **ORF backfill** | `backfill()` returns `translated_md` unchanged — skeleton-based backfill not implemented | `src/automedia/omni/orf_adapter.py` | 46 |
| **ORF XLIFF apply** | `apply_xliff()` is a no-op placeholder | `src/automedia/omni/orf_adapter.py` | 68 |
| **MCP register adapter** | `register_platform_adapter` tool is a stub "until PRD-1 NG6" | `src/automedia/mcp/tools.py` | 466 |
| **Xiaohongshu publisher** | Returns `"not_implemented"` — Xiaohongshu has no public API | `src/automedia/adapters/platforms/xiaohongshu_publisher.py` | entire file |
| **Platform stubs (deprecated)** | Old `XiaohongshuAdapter` and `ZhihuDraftAdapter` in `platform_drafts/` | `src/automedia/platform_drafts/` | both files |
| **Production E2E tests (S1–S3)** | `tests/production/` directory does not exist despite full test design doc | `docs/production-e2e-test-design.md` | S1–S3 |

---

## 5. Architecture Gaps

Architecture Decision Records (ADRs) that were **accepted but not yet implemented**.

| ADR | Title | Effort | Target Version |
|-----|-------|--------|---------------|
| ADR-001 | Singleton Registry Unification | Medium (1–2 days) | v1.1.0 |
| ADR-004 | Decompose `mcp/server.py` Monolith | Medium (1–2 days) | Not specified |

**Location**: `docs/adr/architecture-decisions.md`

---

## 6. Summary Table

| # | Dimension | Priority | Type | Effort Estimate |
|---|-----------|----------|------|-----------------|
| 1.1 | Video synthesis & rendering | 🔴 High | New capability | Large (weeks) |
| 1.2 | International social publishing (YouTube/Twitter/TikTok) | 🔴 High | New capability | Medium (3–5 days per platform) |
| 1.3 | Real topic collection API | 🔴 High | Replace stub | Medium (3–5 days per source) |
| 1.4 | Agent account & session management | ✅ Implemented (PRD-4) | New subsystem ✅ | Complete (191 tests, 7 modules) |
| 2.1 | Content repurposing | 🟡 Medium | New capability | Large (weeks) |
| 2.2 | Post-publish analytics | 🟡 Medium | New capability | Large (weeks) |
| 2.3 | Decision Layer LLM integration | 🟡 Medium | Upgrade existing | Medium (5–7 days) |
| 2.4 | Voice cloning / custom TTS | 🟡 Medium | New capability | Medium (3–5 days) |
| 3.1 | Blog/website publishing | 🟢 Low | New capability | Small (1–2 days per platform) |
| 3.2 | Email/newsletter marketing | 🟢 Low | New capability | Medium (3–5 days) |
| 3.3 | Podcast production | 🟢 Low | New capability | Medium (5–7 days) |
| 3.4 | Background music & SFX | 🟢 Low | New capability | Small (2–3 days) |
| 3.5 | SEO optimization | 🟢 Low | New capability | Small (2–3 days) |
| 3.6 | Platform thumbnails | 🟢 Low | New capability | Small (1–2 days) |
| 3.7 | A/B testing | 🟢 Low | New capability | Medium (5–7 days) |
| 3.8 | Team collaboration | 🟢 Low | New capability | Large (weeks) |
| 3.9 | Content moderation | 🟢 Low | New capability | Small (2–3 days) |
| 3.10 | Audio platform distribution | 🟢 Low | New capability | Medium (3–5 days) |
| 4.1 | OL quality judge (stub) | 🟢 Low | Fix stub | Small (1 day) |
| 4.2 | ORF backfill/xliff (stubs) | 🟢 Low | Fix stub | Small (1 day) |
| 4.3 | MCP register adapter (stub) | 🟢 Low | Fix stub | Small (1 day) |
| 5.1 | ADR-001 Registry unification | 🟢 Low | Refactor | Small (1–2 days) |
| 5.2 | ADR-004 Server decomposition | 🟢 Low | Refactor | Small (1–2 days) |

---

## Reference

- Current capability overview: `AGENTS.md` (project root)
- Architecture decisions: `docs/adr/architecture-decisions.md`
- Commercial vs open-source split: `docs/open-core.md`
- Adapter framework: `src/automedia/adapters/base.py`
- Pipeline modes and gates: `src/automedia/pipelines/runner.py`
