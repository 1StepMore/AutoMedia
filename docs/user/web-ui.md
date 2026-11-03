---
title: Local Web UI
description: The minimal loopback-only web interface — config, one-run, results, accounts.
---

# Local Web UI (minimal)

`automedia ui` serves a **single-page, loopback-only** interface for people
who don't want to memorize CLI commands. It is deliberately minimal — not a
SaaS, no auth, no remote access.

```bash
pip install '.[webui]'      # fastapi + uvicorn
automedia ui                # http://127.0.0.1:8765 (loopback only)
automedia ui --port 9000
```

## What each zone does

| Zone | What it shows / does |
|---|---|
| 配置 | Merged config (secrets redacted) + `doctor`-style dependency table |
| 跑一次 | Start one pipeline run (`run_full_pipeline`) in a background thread; live progress via the pipeline's `PipelineProgress` tracker |
| 结果 | Project list under `AUTOMEDIA_PROJECTS_DIR` + per-project JSON detail |
| 账号 | Registered accounts (metadata only — never credentials). `login-capture` / `connect` stay terminal commands: they need a headed browser / real TTY |

## Security posture — read this before exposing anything

- Binds **127.0.0.1 only**; there is no authentication. Do not proxy it to a
  public interface, and do not run it on a shared machine you don't trust.
- Secrets in the config view are redacted by key name; account endpoints
  never include credential payloads.
- Everything the UI does goes through the same SDK the CLI/MCP use — there is
  no second business logic layer to keep in sync.

## Related

- [Account & Credential Management](account-management.md)
- [Platform Capability Matrix](platform-capability-matrix.md)
- Issue #358 (this feature)
