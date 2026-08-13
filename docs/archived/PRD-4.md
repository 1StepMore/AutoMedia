---
title: PRD-4 — Agent Account & Publishing Management Layer
description: Account registry, OAuth/session management, and publishing automation layer — enables AI agents to connect, manage, and publish to social media accounts autonomously.
---

# PRD-4: Agent Account & Publishing Management Layer

> **Layer:** Account & Publishing Management  
> **Sits alongside:** PRD-1 (Production Layer — 通用化), PRD-2 (Omni Adapter Layer — Omni三件套集成), PRD-3 (Decision Layer — 商用一站式solution-wise)  
> **Status:** ✅ **已实现** — 见 `src/automedia/accounts/`、`automedia account` CLI 及 MCP 账户工具  
> **Target:** v2.0 (已发布)

---

## 1. Overview

PRD-4 sits **alongside** the existing three layers and provides the missing account infrastructure that enables AI agents to autonomously connect to, manage, and publish content to social media platforms.

### 1.1 Why PRD-4

AutoMedia's current architecture assumes **static, pre-configured credentials** for each platform. There is no way for an AI agent to:

- Log into a social media account
- Check whether a session is still valid
- Switch between multiple accounts on the same platform
- View account health / status
- Automatically refresh expired tokens or cookies
- Retrieve post-publish analytics

Without PRD-4, the pipeline is a **one-way firehose** — content is produced but cannot be managed or monitored post-publication. Agents must rely on human operators to manually configure credentials and handle failures.

### 1.2 Layer Stack

```
PRD-4 ── Agent Account & Publishing Management Layer
  │
  │  (provides authenticated account sessions & analytics to:)
  ├──► PRD-1 ── Production Layer (通用化 — gates, media, publishing adapters)
  │              PRD-4 accounts enable account-aware publishing via platform adapters
  │
  ├──► PRD-3 ── Decision Layer (商用一站式solution-wise — strategy, asset library, HITL)
  │              PRD-4 analytics inform strategy decisions (channel performance, best time to publish)
  │
  ┊   PRD-2 ── Omni Adapter Layer (Omni三件套集成 — doc extraction, translation)
  │            PRD-2 operates on files, not accounts — no direct dependency on PRD-4
  │
  ▼   (existing code stays unchanged where not consuming PRD-4)
```

PRD-4 does **not** replace the existing adapter pattern. Platform adapters (WeChatPublisher, ZhihuPublisher, etc.) continue to handle the platform-specific publish logic. PRD-4 adds the **account management and session infrastructure** that sits above them.

PRD-2 is intentionally **not** a consumer of PRD-4 — Omni adapters (OPP, OL, ORF) operate on files and documents, not on social media accounts, so PRD-4 account infrastructure is irrelevant to them.

---

## 2. Current State & Problem Analysis

### 2.1 Existing Auth Approach (Problematic)

| Platform | Auth Method | Session Mgmt | Multi-Account | Health Check |
|----------|------------|--------------|---------------|--------------|
| WeChat | `client_credential` OAuth (server-to-server) | ❌ Token fetched fresh per publish, no caching | ❌ Single account only | ❌ None |
| Zhihu | Static cookie from env var | ❌ None — cookie expires silently | ❌ Single account only | ❌ None |
| Xiaohongshu | Static cookie (stub — not implemented) | ❌ N/A | ❌ N/A | ❌ N/A |
| Feishu | _(out of scope — IM notifications handled by agent framework)_ | ❌ N/A | ❌ N/A | ❌ N/A |
| YouTube | No adapter | ❌ N/A | ❌ N/A | ❌ N/A |
| TikTok | No adapter | ❌ N/A | ❌ N/A | ❌ N/A |
| Twitter/X | No adapter | ❌ N/A | ❌ N/A | ❌ N/A |

### 2.2 Pain Points

1. **Agent cannot act autonomously** — every credential change requires human intervention
2. **Silent credential expiry** — WeChat token expires in 2 hours, Zhihu cookies expire unpredictably, causing publish failures with opaque errors
3. **No account switching** — a single deployment serves only one account per platform
4. **No analytics feedback** — post-publish data (reads, likes, comments) is invisible
5. **No onboarding flow** — connecting a new account requires manual env var / YAML editing

---

## 3. Architecture

### 3.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRD-4 LAYER                                   │
│                                                                     │
│  ┌────────────────────┐    ┌─────────────────────────────────────┐ │
│  │  Auth Flow Engine   │    │  Account Registry                    │ │
│  │  (OAuth2 / Cookie / │    │  (encrypted credential store,        │ │
│  │   API Key / QR)     │    │   per-platform account profiles)     │ │
│  └────────┬───────────┘    └──────────────┬──────────────────────┘ │
│           │                               │                         │
│           ▼                               ▼                         │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Session Manager                                   │  │
│  │  (token cache, refresh, rotation, expiry detection,           │  │
│  │   health monitoring, stale session alerting)                  │  │
│  └──────────────┬───────────────────────────────────────────────┘  │
│                 │                                                  │
│                 ▼                                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Unified Publishing API                            │  │
│  │  (account-aware publish(), schedule(), status(), analytics()) │  │
│  └──────────────┬───────────────────────────────────────────────┘  │
│                 │                                                  │
│                 ▼ (delegates to platform adapters)                 │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  PRD-1 Adapters (WeChatPublisher, ZhihuPublisher, etc.)      │  │
│  │  + Future adapters (YouTubePublisher, TikTokPublisher, etc.)  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
  PRD-4 MCP Tools & CLI
  (connect_account, list_accounts, check_account_health,
   disconnect_account, get_account_analytics, refresh_session)
```

### 3.2 Relationship to Existing Modules

| Existing Module | PRD-4 Relationship |
|----------------|-------------------|
| `core/credential_loader.py` | **Replaced** — PRD-4 provides an encrypted per-account credential store instead of flat key-value env vars |
| `adapters/base.py` | **Extended** — `BasePlatformAdapter` gains `authenticate()`, `check_health()`, `get_analytics()` abstract methods |
| `adapters/registry.py` | **Extended** — becomes account-aware (same adapter class → multiple account instances) |
| `adapters/publish_engine.py` | **Extended** — accepts account ID parameter instead of using global credentials |
| `mcp/server.py` | **Extended** — adds 5+ new MCP tools for account management |
| `cli/commands/adapter.py` | **Extended** — adds account CRUD commands |
| `tenant/` | **Independent** — PRD-4 accounts are orthogonal to tenant workspace management |
| `decision/` | **Consumer** — Decision Layer can query account analytics for strategy decisions |

### 3.3 Encryption Model

Account credentials must be stored encrypted at rest:

```
┌─────────────────────────────────────────┐
│  ~/.automedia/accounts/                  │
│  ├── wechat/                             │
│  │   ├── account_1.json.enc              │  ← AES-256-GCM encrypted
│  │   └── account_2.json.enc              │
│  ├── zhihu/                              │
│  │   └── account_1.json.enc              │
│  ├── youtube/                            │
│  │   └── account_1.json.enc              │
│  └── accounts.index.json                 │  ← UUID → {platform, label, fingerprint}
└─────────────────────────────────────────┘
```

Encryption key derived from:
1. `AUTOMEDIA_MASTER_KEY` env var (highest priority)
2. System keyring (`keyring` package)
3. Hardware-bound key (TPM/secure enclave, future)

---

## 4. Requirements

### 4.1 Account Registry (Foundation)

| ID | Requirement | Priority | Edition |
|----|-------------|----------|---------|
| AR-1 | Create/register a new platform account with credentials (OAuth token, cookie, API key) | P0 | Community |
| AR-2 | List all registered accounts with platform, label, and health status | P0 | Community |
| AR-3 | Get account details (platform, label, fingerprint, auth type, health status, last used) | P0 | Community |
| AR-4 | Delete/disconnect an account | P0 | Community |
| AR-5 | Update account credentials (refresh token, rotate cookie) | P0 | Community |
| AR-6 | Encrypted credential storage at rest (AES-256-GCM) | P0 | Community |
| AR-7 | Label/friendly-name each account (e.g., "Brand WeChat", "Personal Zhihu") | P1 | Community |
| AR-8 | Tag accounts by purpose (publishing, analytics, monitoring) | P2 | Commercial |
| AR-9 | Import/export accounts for backup and migration | P2 | Commercial |
| AR-10 | Account activity log (last publish, last health check, credential age) | P1 | Community |

### 4.2 Auth Flow Engine

| ID | Requirement | Priority | Edition |
|----|-------------|----------|---------|
| AF-1 | OAuth2 authorization_code flow (redirect URI + token exchange) | P0 | Community |
| AF-2 | OAuth2 client_credentials flow (server-to-server, existing WeChat pattern) | P0 | Community |
| AF-3 | Cookie-based auth for platforms without OAuth (Zhihu, Xiaohongshu) | P0 | Community |
| AF-4 | API key / bearer token auth for simple platforms (Feishu, future) | P0 | Community |
| AF-5 | QR-code login flow for WeChat Official Account (scan → confirm → token) | P1 | Commercial |
| AF-6 | Browser automation login (Playwright) for cookie-based platforms — headless login with fallback to manual cookie paste | P1 | Community |
| AF-7 | Webhook-based auth callback server (receives OAuth redirect, stores token) | P2 | Commercial |
| AF-8 | Multi-factor auth support for platforms that require it | P2 | Commercial |

### 4.3 Session Manager

| ID | Requirement | Priority | Edition |
|----|-------------|----------|---------|
| SM-1 | Token/session cache (avoid re-authenticating on every publish) | P0 | Community |
| SM-2 | Automatic token refresh before expiry (e.g., refresh WeChat token at 75% of TTL) | P0 | Community |
| SM-3 | Session health monitoring — periodic check that credentials are still valid | P1 | Community |
| SM-4 | Stale session alerting (log warning, MCP notification, optional webhook) | P1 | Community |
| SM-5 | Cookie rotation — detect when a cookie is about to expire and prompt re-login | P2 | Community |
| SM-6 | Rate-limit-aware retry — back off when platform returns rate-limit errors | P1 | Community |
| SM-7 | Session history — track session lifetime, refresh count, failure events | P2 | Commercial |

### 4.4 Account-Aware Publishing

| ID | Requirement | Priority | Edition |
|----|-------------|----------|---------|
| AP-1 | `publish(account_id, artifact_dir, project)` — publish using a specific account's session | P0 | Community |
| AP-2 | `schedule(account_id, artifact_dir, project, publish_at)` — scheduled publishing | P1 | Commercial |
| AP-3 | `get_publish_status(account_id, platform_ref)` — check if a submitted publish succeeded | P1 | Community |
| AP-4 | `cancel_publish(account_id, platform_ref)` — cancel a scheduled/queued publish | P2 | Commercial |
| AP-5 | Batch publish (same content → multiple accounts) | P1 | Community |
| AP-6 | Platform-specific content preview before publishing (draft review) | P2 | Commercial |

### 4.5 Account Analytics (Post-Publish)

| ID | Requirement | Priority | Edition |
|----|-------------|----------|---------|
| AA-1 | Get basic stats: follower count, post count, engagement rate | P1 | Community |
| AA-2 | Get per-post analytics: reads, likes, comments, shares, save count | P1 | Commercial |
| AA-3 | Get time-series analytics: follower growth, engagement trends | P2 | Commercial |
| AA-4 | Cross-platform analytics comparison (same content, different platforms) | P2 | Commercial |
| AA-5 | Analytics cache (avoid hitting rate limits; configurable TTL) | P1 | Community |

### 4.6 Agent-Facing Interface (MCP Tools)

| ID | Tool | Description | Priority |
|----|------|-------------|----------|
| MI-1 | `connect_account(platform, auth_type, credentials)` | Register a new account (OAuth flow or paste token/cookie) | P0 |
| MI-2 | `list_accounts(platform=None, status=None)` | List connected accounts with health status | P0 |
| MI-3 | `get_account_health(account_id)` | Check if an account's session is still valid | P0 |
| MI-4 | `disconnect_account(account_id)` | Remove an account and revoke tokens | P0 |
| MI-5 | `refresh_account_session(account_id)` | Force refresh an expiring session | P1 |
| MI-6 | `get_account_analytics(account_id, period)` | Get basic account stats | P1 |
| MI-7 | `get_post_analytics(account_id, post_id)` | Get per-post performance data | P2 |
| MI-8 | `start_oauth_flow(platform)` | Initiate OAuth2 login and return redirect URI | P1 |

### 4.7 CLI Interface

| ID | Command | Description | Priority |
|----|---------|-------------|----------|
| CI-1 | `automedia account connect <platform> [--auth-type]` | Interactive account registration | P0 |
| CI-2 | `automedia account list [--platform] [--status]` | List connected accounts | P0 |
| CI-3 | `automedia account health <account_id>` | Check account session health | P0 |
| CI-4 | `automedia account disconnect <account_id>` | Remove account | P0 |
| CI-5 | `automedia account refresh <account_id>` | Force session refresh | P1 |
| CI-6 | `automedia account analytics <account_id>` | Show account stats | P1 |
| CI-7 | `automedia publish <account_id> --project <dir>` | Quick publish via CLI | P1 |

### 4.8 Browser Automation (Platforms Without APIs)

| ID | Requirement | Priority | Edition |
|----|-------------|----------|---------|
| BA-1 | Playwright-based login flow for Xiaohongshu (cookie capture) | P1 | Community |
| BA-2 | Cookie health verification — open page, check if logged in | P1 | Community |
| BA-3 | Manual cookie paste fallback when automation fails (UI prompt) | P1 | Community |
| BA-4 | Headless Chrome/Chromium support with stealth evasion | P2 | Commercial |

---

## 5. Open-Core Split

| Feature Area | Community | Commercial |
|-------------|-----------|------------|
| Account Registry (AR-1 to AR-5, AR-7, AR-10) | ✅ | — |
| Encrypted credential storage (AR-6) | ✅ | — |
| Account tags & import/export (AR-8, AR-9) | ❌ | ✅ |
| Auth Flow Engine (AF-1 to AF-4, AF-6) | ✅ | — |
| QR-code login (AF-5) | ❌ | ✅ |
| Auth callback server (AF-7) | ❌ | ✅ |
| MFA support (AF-8) | ❌ | ✅ |
| Session Manager (SM-1 to SM-4) | ✅ | — |
| Cookie rotation (SM-5) | ✅ | — |
| Rate-limit-aware retry (SM-6) | ✅ | — |
| Session history (SM-7) | ❌ | ✅ |
| Account-aware publishing (AP-1, AP-3, AP-5) | ✅ | — |
| Scheduled publishing (AP-2) | ❌ | ✅ |
| Cancel publish, preview (AP-4, AP-6) | ❌ | ✅ |
| Basic analytics (AA-1, AA-5) | ✅ | — |
| Per-post & cross-platform analytics (AA-2 to AA-4) | ❌ | ✅ |
| MCP Tools (MI-1 to MI-5) | ✅ | — |
| Advanced MCP Tools (MI-6 to MI-8) | ❌ | ✅ |
| CLI commands (CI-1 to CI-4) | ✅ | — |
| Advanced CLI (CI-5 to CI-7) | ❌ | ✅ |
| Browser automation (BA-1 to BA-3) | ✅ | — |
| Stealth evasion (BA-4) | ❌ | ✅ |

---

## 6. Existing Code That Would Change

### 6.1 Files to Modify

| File | Change |
|------|--------|
| `src/automedia/core/credential_loader.py` | **Deprecate** — replaced by encrypted per-account store. Keep as fallback for backward compatibility. |
| `src/automedia/adapters/base.py` | **Extend** — add `authenticate()`, `check_health()`, `get_analytics()`, `refresh_session()` abstract methods |
| `src/automedia/adapters/registry.py` | **Extend** — support account-scoped adapter instances |
| `src/automedia/adapters/publish_engine.py` | **Extend** — `publish_all()` accepts optional `account_ids` parameter |
| `src/automedia/mcp/server.py` | **Extend** — register 5+ new MCP tools from §4.6 |
| `src/automedia/cli/app.py` | **Extend** — register `automedia account` command group |
| `src/automedia/adapters/platforms/wechat_publisher.py` | **Update** — extract auth to PRD-4, implement `authenticate()` + `refresh_session()` |
| `src/automedia/adapters/platforms/zhihu_publisher.py` | **Update** — implement `authenticate()` + `check_health()` |
| `src/automedia/adapters/platforms/xiaohongshu_publisher.py` | **Update** — implement browser-automation-based login when platform has no API |

### 6.2 Files to Create

| File | Purpose |
|------|---------|
| `src/automedia/accounts/__init__.py` | Package init, exports |
| `src/automedia/accounts/registry.py` | `AccountRegistry` — CRUD for platform accounts |
| `src/automedia/accounts/store.py` | Encrypted credential persistence (AES-256-GCM) |
| `src/automedia/accounts/auth/__init__.py` | Auth flow package init |
| `src/automedia/accounts/auth/oauth2.py` | OAuth2 authorization_code + client_credentials flow |
| `src/automedia/accounts/auth/cookie.py` | Cookie-based auth with health verification |
| `src/automedia/accounts/auth/browser.py` | Playwright-based browser login automation |
| `src/automedia/accounts/session.py` | `SessionManager` — token cache, refresh, expiry, health |
| `src/automedia/accounts/analytics.py` | `AccountAnalytics` — fetch post-publish stats |
| `src/automedia/cli/commands/account.py` | `automedia account` CLI command group |
| `src/automedia/mcp/accounts.py` | Account MCP tool handlers |
| `tests/test_accounts/` | Test suite for PRD-4 |

---

## 7. Migration Path

### Phase 1 (v2.0-alpha) — Foundation
- Encrypted credential store
- Account registry CRUD
- Auth flow engine for OAuth2 + cookie + API key
- Session manager with token refresh
- Extend `BasePlatformAdapter` with auth methods
- MCP tools: `connect_account`, `list_accounts`, `get_account_health`, `disconnect_account`, `refresh_account_session`
- CLI: `automedia account connect/list/health/disconnect/refresh`
- Update WeChatPublisher + ZhihuPublisher for PRD-4 auth

### Phase 2 (v2.0-beta) — Publishing & Analytics
- Account-aware publishing (`publish(account_id, ...)`)
- Batch publish (same content → multiple accounts)
- Basic analytics (follower count, engagement rate)
- MCP tools: `get_account_analytics`, `start_oauth_flow`
- CLI: `automedia account analytics`, `automedia publish`
- Browser automation for Xiaohongshu

### Phase 3 (v2.0) — Advanced Features
- Scheduled publishing
- Per-post analytics (reads, likes, comments)
- QR-code WeChat login
- Auth callback server
- Cross-platform analytics comparison
- New platform adapters (YouTube, Twitter, TikTok) with PRD-4 auth

---

## 8. Platform Adapter Auth Requirements

Each platform requires adapter-level support for PRD-4. The following table maps auth types to platforms:

| Platform | Auth Type | OAuth Flow | Cookie | API Key | Browser Auto | Notes |
|----------|-----------|------------|--------|---------|-------------|-------|
| WeChat | `client_credential` | ✅ Server-to-server | ❌ | ❌ | ❌ | Token TTL 2h; refresh before expiry |
| Zhihu | Cookie | ❌ | ✅ | ❌ | ✅ | No official OAuth; browser login + cookie capture |
| Xiaohongshu | Cookie | ❌ | ✅ | ❌ | ✅ | No public API; Playwright automation required |
| ~~Feishu~~ | ~~Webhook URL~~ | ⏭️ out of scope | — | — | — | IM notifications handled by agent framework |
| YouTube | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | Standard Google OAuth; requires redirect URI |
| Twitter/X | OAuth2 | ✅ OAuth 2.0 PKCE | ❌ | ❌ | ❌ | Twitter API v2 OAuth 2.0 |
| TikTok | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | TikTok for Developers OAuth |
| Instagram | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | Instagram Basic Display API / Graph API |
| LinkedIn | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | LinkedIn Marketing API OAuth |

---

## 9. Security Considerations

| Concern | Mitigation |
|---------|------------|
| Credential leakage | AES-256-GCM encryption at rest; credentials never logged; `_sanitize_url()` pattern from existing WeChat adapter |
| Token interception | OAuth2 PKCE for all authorization_code flows; HTTPS-only redirect URIs |
| Cookie theft | Encrypted cookie storage; browser automation uses temporary contexts |
| Replay attacks | Token binding to account ID; nonce validation where supported |
| Rate limit abuse | Per-account rate-limit tracking; configurable cooldown; exponential backoff |
| Credential rotation | Session manager auto-refreshes tokens; old credentials purged on rotation |
| Audit trail | All account operations logged (create, update, delete, publish, refresh) |

---

## 10. References

- `docs/archive/coverage-gaps.md` §1.4 — Agent Account & Session Management (gap analysis)
- `src/automedia/core/credential_loader.py` — Existing flat credential store (to be deprecated)
- `src/automedia/adapters/base.py` — BasePlatformAdapter (to be extended)
- `src/automedia/adapters/platforms/wechat_publisher.py` — WeChat auth pattern (client_credential)
- `src/automedia/adapters/platforms/zhihu_publisher.py` — Cookie auth pattern
- `docs/user/open-core.md` — Community vs Commercial feature split
- `docs/user/omni-integration.md` — PRD-2: Omni Adapter Layer (Omni三件套集成) — OPP extraction, OL localization, ORF format conversion; no direct dependency on PRD-4
- `docs/dev/developer-guide.md` — PRD-1: Production Layer (通用化) — core pipeline, 20 gates, platform adapters; consumers of PRD-4 authenticated sessions
