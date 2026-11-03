---
title: Platform Capability Matrix
description: Every publisher's automation tier — API / browser automation / semi-auto / manual — with the credentials each needs.
---

# Platform Capability Matrix

Every registered publish target, its automation tier, and what a human must
supply. Tier drives the publish route: **Easy** platforms publish
unattended (respecting brand automation levels); **Hard** platforms stop for
a human at the last possible step.

Source of truth: the adapter docstrings under `src/automedia/adapters/platforms/`.
Update this table in the same change as an adapter.

## Easy — API publishing (unattended)

| Platform | API | Credentials | Publish behavior |
|---|---|---|---|
| wechat | WeChat official-account API | appid + secret (`WX_APPID`/`WX_APPSECRET`) | draft → publish per automation level |
| zhihu | Zhihu OAuth API | OAuth token | article publish |
| youtube | YouTube Data API v3 | OAuth2 | video upload (draft/public) |
| twitter | X API v2 | API key + secret + tokens | single/thread publish |
| reddit | Reddit OAuth2 (script app) | client id/secret + account | self-post to a subreddit |
| tiktok | TikTok Content Posting API | OAuth token | video publish |
| facebook | Graph API v22.0 | page access token | feed post + photos (~200 calls/h) |
| instagram | Instagram Graph API | IG business token | container two-step publish (caption ≤2200 chars) |
| linkedin | LinkedIn API | OAuth token | post/article |
| medium | Medium API | integration token | markdown draft (draft-first) |
| wordpress | WP REST API | application password | draft/publish + featured image |

## Hard — browser automation (stops before human confirmation)

| Platform | Automation | Credentials | Stop point |
|---|---|---|---|
| xiaohongshu | Playwright drives the creator publish page | login session via `automedia account login-capture xiaohongshu` (storage_state, encrypted) | form filled (title/body/images) + screenshot; **publish button never clicked** → `ready_for_confirmation` |

Enable with `platforms.xiaohongshu.publish_mode: browser` (default
`manual`). Session expiry and risk-control interstitials return structured
errors pointing back to `login-capture` — the flow is single-attempt by
design (see the anti-detection notes below).

## Manual — no automation today

| Platform | Reason | Human path |
|---|---|---|
| weibo | no server-side publish REST for media posts (mobile SDK only) | post via app/creator portal |
| kuaishou | no public publish API | post via app/creator portal |
| toutiao | no public publish API | post via creator portal |
| baijiahao | no public publish API | post via creator portal |
| juejin | no public publish API | post via web editor |
| douyin | manual-stub adapter | post via app |
| bilibili | manual-stub adapter | upload via creator portal |

All platforms accept the pipeline's drafts (`drafts/*.html|md`) — a human
copies from the project dir when publishing manually.

## Anti-detection & risk-control policy (documented, not evaded)

- **Identity consistency**: the browser session reuses the UA captured at
  login (`user_agent` in the account store) — mixing UAs across a session is
  the cheapest way to earn a risk-control flag.
- **Single-attempt**: one session, one fill, no retry loops. Risk controls
  punish rapid automated retries far more than single polite runs.
- **Stop and hand over**: any login redirect, risk-control interstitial, or
  unknown page structure aborts with a structured error and a manual-takeover
  path. No CAPTCHA solving, no fingerprint spoofing, no behavior simulation
  beyond normal form filling — those are evasion techniques this project
  deliberately does not implement.
- **Human confirmation is the boundary**: automation stops before every
  publish confirmation. The publish action itself is always human.

## Related

- [CLI reference — account login-capture](cli-reference.md)
- [Video engines](video-engines.md) (media artifacts the publishers consume)
- Issue #353 (browser publish engine + this matrix)
