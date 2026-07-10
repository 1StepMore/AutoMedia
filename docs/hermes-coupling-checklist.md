---
title: Hermes Coupling Checklist
description: Audit checklist confirming the new automedia/ package is fully decoupled from Hermes Agent v0.17.
---

# Hermes Coupling Points Checklist & Decoupling Verification

> **Audit objective**: Confirm the new `automedia/` package is fully decoupled from Hermes Agent v0.17
> **Audit date**: 2026-07-07
> **Status notes**:
> - `resolved` — Coupling point eliminated, no corresponding dependency in the new package code
> - `isolated` — Coupling point exists but is an external interface at the deployment/scheduling layer, does not affect library code independence

---

## Coupling Points Checklist

| # | Coupling Point | Status | New Package Solution | Original Hermes Reference |
|---|----------------|--------|---------------------|---------------------------|
| 1 | `skill_view(name='...')` syntax — registering view functions through Hermes Agent's SkillView API | `resolved` | New package has no `skill_view` calls. CLI is based on `typer`, MCP is based on the `mcp` official SDK, with no Hermes Agent registration logic | `@skill_view(...)` decorators in `00_核心脚本/*.py` |
| 2 | `~/.hermes/skills/productivity/automedia/scripts/` path hardcoded — script location depends on a fixed Hermes installation path | `resolved` | Scripts are located inside the `automedia/` package, resolved via `__file__` / `importlib.resources`, with no hardcoded absolute paths | All shell/Python entry files under the `scripts/` directory |
| 3 | `~/.hermes/skills/productivity/automedia/hooks/` path hardcoded — gate hook registration depends on a fixed Hermes installation path | `resolved` | Hooks moved to `automedia/hooks/`, pure Python `Protocol` implementation, registered through the `GateHook` interface, with no filesystem path dependencies | Hook scripts under the `hooks/` directory |
| 4 | Hermes home directory absolute path — multiple hardcoded user directory paths | `resolved` | No `.hermes` references at all. Config paths are unified as `~/.automedia/` (only used for loading, not hardcoded into code logic), see `config_loader.py` + `credential_loader.py` for details | String hardcoding in old scripts |
| 5 | Project path hardcoded | `resolved` | `Project.init()` (`automedia/core/project.py`) supports a `base_dir` parameter, defaults to `os.getcwd()`, fully configurable | `PROJECT_BASE` constant in the old AutoMedia `project_init.py` |
| 6 | `execute_code` sandbox dependency — Hermes Agent's built-in code sandbox execution environment | `resolved` | Pure Python execution, no sandbox. LLM calls go through a configurable `provider` (`~/.automedia/model_config.yaml`), all Gates are local Python classes | `self.skill.execute_code(...)` calls in old gates |
| 7 | Hermes cron scheduling — Hermes Agent's built-in cron job management (jobs.json format + Agent-level scheduling) | `isolated` | New package exposes cron jobs via CLI (`automedia cron run <job-name>`), scheduled by external crond / systemd timer / K8s CronJob. PRD-1 §6 explicitly defines this as a deployment-layer responsibility | Hermes Agent `cron/` module + `jobs.json` |
| 8 | OpenCode Go API default binding — LLM calls forced through `opencode-go` API, model selection limited to its supported model list | `resolved` | Configurable via `model_config.yaml`, supports OpenAI / Anthropic compatible formats. Users can freely switch providers and endpoints. See `defaults.yaml` + `credential_loader.resolve_api_key()` | Hardcoded `opencode_go` URL in old `llm_client.py` |
| 9 | MiniMax API dependency — text generation, image generation, TTS, subtitle proofreading, and other steps directly called MiniMax API | `resolved` | MiniMax dead code has been cleaned up. LLM calls abstracted into swappable providers, default `provider: ""` empty string (users configure as needed). R4 risk closed | Old `minimax_*.py` and `api_client.py` |
| 10 | `skill` loading path hardcoded — Hermes Agent loaded skill packages via fixed paths | `resolved` | New package has no 'skill' concept. Functionality is split into `pipelines/` (orchestration), `gates/` (gating), `adapters/` (platform adaptation), all loaded via Python imports | Hermes Agent `skill_loader.py` + old `skills/` directory |
| 11 | `sys.path.insert` hack — dynamically modifying Python module search paths at runtime | `resolved` | Zero `sys.path` modifications. All internal references use `automedia.` package imports, external dependencies declared via `pyproject.toml` | `sys.path.insert` in old `__init__.py` / `bootstrap.py` |
| 12 | Hermes `.env` dependency — credentials loaded through Hermes Agent's `.env` file | `resolved` | Four-layer credential loading (`credential_loader.py`): env var (`AUTOMEDIA_*`) → keyring → `oscreds.yaml` → `credentials.yaml`. No Hermes `.env` dependency | Hermes Agent `dotenv` loading logic + old `.env` |
| 13 | Hermes `jobs.json` cron format — scheduled tasks used Hermes-proprietary JSON schema | `isolated` | External cron directly calls `automedia cron run <job-name>` CLI. `~/.automedia/cron/jobs.yaml` uses plain YAML, not compatible with `jobs.json`. Externalized per PRD-1 §6 | Hermes Agent `jobs.json` file |
| 14 | Feishu/WeChat Official Account API brand hardcoding — brand-specific API endpoints, AppID, and Secret embedded directly in adapters | `resolved` | `wechat_publisher.py` + `feishu_notifier.py` are generic stubs, configured via `FEISHU_WEBHOOK_URL` / `WX_APPID` / `WX_APPSECRET` environment variables. Registration is pluggable via `AdapterRegistry` | `WX_APPID = "wx_xxx"` hardcoding in old `pre_wechat_upload.py` |
| 15 | Hermes Agent `artifacts/` directory convention — output fixed to Hermes-managed `artifacts/` path | `resolved` | `Project.init()` creates a standard directory structure (`01_content/`, `02_images/`, `03_video/`, etc.), all under `base_dir`, with no Hermes artifact constraints | `ARTIFACTS_DIR = ...` in old `pipeline_orchestrator.py` |
| 16 | Hermes Agent `pipeline_md5.json` path hardcoded | `resolved` | MD5 tracking retained (Red Line 7), but path is dynamically determined by `Project.project_dir`, no hardcoding. `md5_tracker.py` receives path via parameters | `PIPELINE_MD5_PATH` constant in old `pre_send_whisper_check.py` |
| 17 | Hermes Agent Gate registration API (`register_gate`) — Gates had to be registered through the Agent API | `resolved` | Gates are plain Python classes inheriting `BaseGate` (`automedia/gates/base.py`), orchestrated via YAML config in `pipeline_orchestrator.py`. No Agent API dependency | `register_gate()` in old `gate_registry.py` |
| 18 | Hermes Agent runtime introspection — code called `hermes.get_current_skill()`, `hermes.get_config()`, and other runtime APIs | `resolved` | No `hermes.*` calls at all. Configuration is loaded via the `load_config()` function, independent of Agent runtime context | `hermes.get_current_skill().config` calls in old gates |
| 19 | Hermes Agent log format — used Hermes-proprietary log schema | `resolved` | Python standard `logging` module. No Hermes log format dependency | Hermes JSON log format in old `log_config.py` |
| 20 | Hermes `model_config.yaml` fixed location — had to be at `~/.hermes/config/model_config.yaml` | `resolved` | `model_config.yaml` is loaded from `~/.automedia/`, path managed uniformly by `credential_loader` | Hermes Agent configuration directory convention |

---

## Decoupling Verification Summary

### Code Level (resolved: 17/20)

- **Hermes keywords**: `grep -r "hermes\|\.hermes\|skill_view\|execute_code" automedia/` → **0 matches** ✅
- **Hardcoded absolute paths**: No user-specific paths ✅
- **sys.path hack**: No `sys.path.insert` calls ✅
- **Hermes SDK dependency**: `pyproject.toml` has no `hermes-agent` or `hermes-sdk` ✅
- **MiniMax dead code**: `grep -ri "minimax" automedia/` → **0 matches** ✅

### Deployment Level (isolated: 3/20)

The following 3 items are external interfaces and fall under deployment responsibilities rather than library code issues:

| # | Coupling Point | Externalization Method | Responsible Party |
|---|----------------|----------------------|-------------------|
| 7 | Hermes cron scheduling | `automedia cron run` CLI + system crond / systemd timer | Operations/Deployment |
| 13 | jobs.json cron format | `~/.automedia/cron/jobs.yaml` + external cron invocation | Operations/Deployment |
| — | Combined total of the above two items | See PRD-1 §6 External Scheduling Architecture | — |

---

## Remaining Risks

| Risk | Description | Mitigation |
|------|-------------|------------|
| R4 (PRD-1) | MiniMax historical code not fully cleaned up | Eliminated through full repository search, zero matches in `automedia/` |
| Config migration | Users with old Hermes `model_config.yaml` need to manually copy it to `~/.automedia/` | Documentation needs migration steps marked, handled at M4 milestone |

---

*Checklist version: v1.0 · Corresponds to PRD-1 M1 exit criteria*
