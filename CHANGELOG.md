# Changelog

## [Unreleased]

### Added

- **Windows Deployment Support**: Full Windows deployment guide at `docs/user/windows-deployment.md` (WSL2, Docker Desktop, native Windows). PowerShell setup script at `scripts/setup.ps1`. Deployment overview at `docs/user/deployment.md` with method comparison table.

- **Gate Modifier YAML Overrides**: OverridesLoader now accepts `gates.include`, `gates.exclude`, `gates.override_failure_mode` keys in YAML override rules. `validate_gate_modifiers()` returns `(included, excluded, overrides)` tuple for type-safe gate list composition. `override_failure_mode` applied per-instance via `object.__setattr__` (no BaseGate class mutation).

- **Docker Compose Profiles**: `docker-compose.yml` with `mcp-full` profile bundling bun, edge-tts, whisper, and chromium for full-dependency containers. `Dockerfile` streamlined for profile-based dependency injection.

- **Concurrency Control**: Pipeline concurrency semaphore (max 3 simultaneous pipelines) in MCP tools. `active_pipelines.json` session tracker at `~/.automedia/` with `fcntl.flock` file locking, 24h timeout → `"lost"` cleanup, and `list_active_pipelines()` MCP tool for agent inspection.

- **`[all]` PyPI Extra**: New `[all]` pip install extra that includes `[dev]`, `[mcp]`, `[omni]`, `[openai]`, `[anthropic]` — full package functionality with a single extra. AGPL notice for omni extras (PyMuPDF).

- **Onboarding MCP Tools**: `health_check` now reports `first_run` status and version. New `onboard()` MCP tool for guided setup. Error code system expanded from 6→13 codes with structured resolution fields in `MCPErrorCode`.

- **CI/CD Deploy Validation**: New `validate-deploy` CI job that builds the Docker image and runs `systemd-analyze verify` on service files. Full CI pipeline with lint, typecheck, test, security scan, and deploy validation.

- **Cost Data Exposure**: `_UsageTracker` cost and token data exposed per-thread on `run_pipeline` result. No cross-pipeline aggregation — per-invocation only.

### Fixed

- **Bug 3 — Incorrect log level in structured fallback**: `llm_client.py` structured response fallback changed from `logger.info` to `logger.warning` to match the actual severity of the event (Issue #48).

- **Issue #48 Bug 1 — PROJECTS_DIR env var not wired**: `Project.init()` now respects `AUTOMEDIA_PROJECTS_DIR` environment variable. When `base_dir=None`, the env var value is used as the projects root directory. Explicit `base_dir` parameter still takes precedence.

- **Issue #51 Bug 1 — FAKE_LLM mock not dispatched correctly**: `llm_client.py` now short-circuits all three public functions (`llm_complete`, `llm_complete_structured_safe`, `llm_complete_structured`) when `AUTOMEDIA_FAKE_LLM=1` is set. Structured responses dispatch to a type-specific fake (`G0CheckResult`, `G1CheckResult`, `G2CheckResult`) based on the target model name.

- **Issue #51 Bug 2 — platforms param missing from run_pipeline chain**: New `platforms` parameter added to `run_pipeline` (MCP), `run_full_pipeline` (SDK), `_run_pipeline`, and `_select_gates`. When provided, only gate modifiers for the requested platforms are applied. Accepts comma-separated string (MCP) or `list[str] | None` (SDK).

- **8 stale test assertions updated**: Fixed outdated enum member sets, resolution strings, error-code defaults, tool-name lists, and exception-type mismatches in MCP and runner tests.

### Changed

- **`_compose_gate_list()`**: OverridesLoader `gates` rules now feed into gate composition at runtime. `_collect_platform_gate_modifiers()` merges platform-specific gate modifiers from overrides.
- **`_build_gates_from_names()`**: Applies `override_failure_mode` from gate modifiers per-instance via `object.__setattr__`.
- **MCP server healthcheck**: deployed `healthcheck.sh` performs real MCP ping via `python -m automedia.mcp.server --ping`. systemd service requires `network-online.target`.

- **Bilibili Platform Onboarding**: Added Bilibili to `_PLATFORM_CATEGORIES` (video-first routing), `defaults.yaml` platform config, and 6 platform-scoped Jinja2 prompt templates (content_writer, copy_review_g2, humanizer_g1, brand_strategy, pipeline_strategy, content_quality). YouTube and Twitter also added to `_PLATFORM_CATEGORIES` for correct auto-mode pipeline derivation.

- **Platform-Aware Workflow Customization (F49-F55)**: Comprehensive platform-scoped pipeline customization system covering prompt templates, media specs, gate modifiers, cron scheduling, reusable workflows, and director mode.

- **Platform-Scoped Prompt Resolution**: `load_prompt(name, platform=...)` with 3-layer resolution (brand → platform → global → built-in). 18 platform-scoped Jinja2 templates (6 platforms × 3 gates) plus 18 MCP-scoped equivalents. OverridesLoader extended with `load_prompts(brand, platform)` and per-platform prompt directories.

- **PlatformMediaSpec Data Model**: Dataclass with width/height/aspect_ratio for 19 platforms. `get_platform_media_spec()` resolver injected into gate_context for per-platform media adaptation.

- **Gate Modifier System**: Override YAML rules support `gates.include`, `gates.exclude`, `gates.override_failure_mode`. `validate_gate_modifiers()` and `_compose_gate_list()` in runner.py for runtime gate list composition.

- **Platform-Aware Cron Scheduling**: `add_cron_schedule` MCP tool extended with `platform` and `mode` parameters. `list_cron_schedules` supports `--platform`/`--mode` filtering. New `automedia cron run-pipeline` CLI command with `--name` and `--pool-db` options.

- **Workflow System**: `Workflow` dataclass and `WorkflowLoader` in `automedia/core/workflow.py` with `load()`, `load_all()`, `extends` inheritance, and circular dependency detection. `_merge_workflow_config()` in runner.py merges workflow settings into pipeline config. `list_workflows` MCP tool and `workflow` parameter on `run_pipeline`/`run_pipeline_from_strategy`.

- **Director HITL Preset**: `DirectorPreset` with 8 review nodes (topic, content, brand, wechat, vision, tts, subtitle, publish) in `automedia/hitl/presets/director.py` + YAML preset. GateEngine extended with `pause_on_approval`, `resume()`, and `_engine_registry` for pausing at specific gates pending human approval. MCP tools: `approve_gate`, `reject_gate`, `get_pending_approvals`.

- **MCP Tools**: 5 new tools — `list_overridable_templates`, `list_workflows`, `approve_gate`, `reject_gate`, `get_pending_approvals`. Total tool count: 50.

- **Override Discoverability**: `list_overridable_templates` MCP tool and `docs/dev/override-reference.md` documenting the full override system with prompt resolution order, rule schema, and 5 worked examples.

### Changed

- **`run_full_pipeline()`**: New parameters `workflow` (workflow name from `workflows.yaml`) and `director` (enable director mode with HITL gate approval).
- **`run_pipeline` / `run_pipeline_from_strategy` MCP tools**: Accept `workflow` and `director` parameters.
- **`GateEngine`**: Added `pause_on_approval` flag and `resume()` method for director-mode gate pausing.
- **Config resolution**: 6-layer hierarchy now includes per-platform prompt resolution as a sub-layer within the overrides layer.

## [1.1.0](https://github.com/1StepMore/AutoMedia/compare/automedia-v1.0.0...automedia-v1.1.0) (2026-07-18)


### Features

* **accounts:** implement PRD-4 Agent Account & Publishing Management Layer ([09bf6d0](https://github.com/1StepMore/AutoMedia/commit/09bf6d0d88e48eb4a8671a4f70371df717683a27))
* **adapters:** add 7 manual-only stub adapters + fix twitter default ([8632d48](https://github.com/1StepMore/AutoMedia/commit/8632d486ff5f8b6d360e5e8724cbef73bcb7389a))
* **adapters:** implement adapter framework with WeChat + Feishu ([9245b40](https://github.com/1StepMore/AutoMedia/commit/9245b40dc555a1f6cc2a3335785e485e4a458388))
* add default hyperframes template files ([ff39225](https://github.com/1StepMore/AutoMedia/commit/ff3922559c117489e711bea47fbd07b764a501a6))
* add project-validation skill, framework doc, and core/cron tests ([8cbdfc9](https://github.com/1StepMore/AutoMedia/commit/8cbdfc90d34a61c94048c8b50a65be59b6b22c09))
* **asset-library:** implement Asset Library with SQLite + Chroma ([67975c5](https://github.com/1StepMore/AutoMedia/commit/67975c589bb8a6b9fbf9f0370f845f191d1cf36a))
* **cli:** add automedia mcp discover command ([5095177](https://github.com/1StepMore/AutoMedia/commit/5095177a3bac4e3be3e56c6a95e5626af413f5f9))
* **cli:** add comprehensive onboarding wizard ([1415ea7](https://github.com/1StepMore/AutoMedia/commit/1415ea7291e74f294ae32313f6d594f2b0138316))
* **cli:** implement full CLI layer (9 subcommands) ([19747e3](https://github.com/1StepMore/AutoMedia/commit/19747e3e0033c20d4375a4bd6cb335db5b5557c4))
* **cli:** implement W2 CLI commands and cron jobs ([2ba3d43](https://github.com/1StepMore/AutoMedia/commit/2ba3d43e75749bacc6b998a287065a7ef4183b3a))
* **cli:** register PRD-3 CLI commands for hitl/license/sop/tenant ([c299977](https://github.com/1StepMore/AutoMedia/commit/c29997711618f33ba279ff33cad5b71f2d55080c))
* **cli:** update init command to write nested model_config.yaml ([8913254](https://github.com/1StepMore/AutoMedia/commit/89132544959367a96ae310dc9ba2cdb28c4ee207))
* close F27, F20, F37 remaining gaps + F25 doc fix ([e8be7ad](https://github.com/1StepMore/AutoMedia/commit/e8be7ad44719982ef9c9bce1dd6dcd9a963910e0))
* close F27/F18/F25 gaps + add 9 platform adapters ([127d990](https://github.com/1StepMore/AutoMedia/commit/127d9907e9cacb11277bf86a567c2c38553b404b))
* **config:** add backward-compat mapping from pipeline.image.* to engines.image.* ([22c3425](https://github.com/1StepMore/AutoMedia/commit/22c3425f8e21a91543daf69876548cfba28a9161))
* **config:** implement overrides subsystem + brand/model schemas ([553ea51](https://github.com/1StepMore/AutoMedia/commit/553ea5193b8294430ed5a617d162aa499482c560))
* **core:** add dotenv .env file loading on import ([7cf0ee3](https://github.com/1StepMore/AutoMedia/commit/7cf0ee31b3b6b48c976633d42420c153b0650f63))
* **core:** add env var priority for credential resolution ([640de45](https://github.com/1StepMore/AutoMedia/commit/640de453ff89f77a8eeecf0e1d7857980556ed20))
* **core:** add get_user_config_dir() with AUTOMEDIA_CONFIG_DIR override ([94bc244](https://github.com/1StepMore/AutoMedia/commit/94bc2442e9e3f5b479b8f7871e18811cc5fb658b))
* **core:** add project directory compatibility scanner for W1-T32 ([61f627f](https://github.com/1StepMore/AutoMedia/commit/61f627f349c4e2437b238dd9662f7ff6c9a59d3f))
* **core:** add tenacity-based LLM retry/backoff ([33bd156](https://github.com/1StepMore/AutoMedia/commit/33bd156a72b2212d3b6ea822da16daccb86ef3eb))
* **core:** implement 3-layer credential_loader ([ebe8e39](https://github.com/1StepMore/AutoMedia/commit/ebe8e39f988f97c0f7dad4507f6f4a506caf22f7))
* **core:** implement 6-layer config_loader ([c01a7f3](https://github.com/1StepMore/AutoMedia/commit/c01a7f3d90ac2489582255755a6476f677a14328))
* **core:** implement LLM client for AI text generation ([05fe64a](https://github.com/1StepMore/AutoMedia/commit/05fe64adca3f10b0f45c5d390077d770c69888ac))
* **core:** implement pool DB, doctor, failure_modes + MiniMax cleanup ([b89bbfb](https://github.com/1StepMore/AutoMedia/commit/b89bbfb79e4875efe5319db04073de355d63083a))
* **core:** implement Project.init with path safety ([d0c5c14](https://github.com/1StepMore/AutoMedia/commit/d0c5c1492231fa3f7da6beba042358d5dc5bd0ae))
* **core:** initialize automedia package skeleton + gitignore ([8b823e9](https://github.com/1StepMore/AutoMedia/commit/8b823e9c90400544228ae6657784d36f861b7038))
* **cron:** implement jobs.yaml template with 4 scheduled jobs ([4e90861](https://github.com/1StepMore/AutoMedia/commit/4e9086199fd330ea9a008a795fb0764fb5a7a8a9))
* **decision:** implement PRD-3 Decision Layer SDK ([8109fa6](https://github.com/1StepMore/AutoMedia/commit/8109fa6246577d6e7e39e2475be9229d5beefd24))
* **deploy:** add MCP systemd service template and setup docs ([1c8bd85](https://github.com/1StepMore/AutoMedia/commit/1c8bd8586b8ce7e4ee13d8f1148e4572ed835228))
* **doctor:** add Chrome headless probe, CLI warning, and config key ([eb95965](https://github.com/1StepMore/AutoMedia/commit/eb959656a21447191900754dcb0f0b6c92a8e293))
* **engines:** add engine infrastructure (registry, errors, base, factory, config) ([6501968](https://github.com/1StepMore/AutoMedia/commit/65019680cd3c17ccf4d0adad8ce410658920f4c1))
* **engines:** implement 4 concrete engines (TTS, ASR, ComfyUI, HyperFrames) ([c43f326](https://github.com/1StepMore/AutoMedia/commit/c43f326110dc661206c95c0b021136a1aa07e346))
* **gates:** add expected_vs_actual gate result field — batch 1/6 ([6de9e79](https://github.com/1StepMore/AutoMedia/commit/6de9e798421219e50ac02160e35156ac6d8f8eb9))
* **gates:** add expected_vs_actual gate result field — batch 2/6 ([7cde4a5](https://github.com/1StepMore/AutoMedia/commit/7cde4a5366af2f842d52ab9469ae236b1aa309a5))
* **gates:** add expected_vs_actual gate result field — batch 3/6 ([26f672e](https://github.com/1StepMore/AutoMedia/commit/26f672ef9e02525639a761c94cdc3f7da7a09b94))
* **gates:** add expected_vs_actual gate result field — batch 4/6 ([bae8805](https://github.com/1StepMore/AutoMedia/commit/bae8805ed4108cdec94c8f4c8f2026ef5c7f206c))
* **gates:** add expected_vs_actual gate result field — batch 5/6 ([8976960](https://github.com/1StepMore/AutoMedia/commit/89769600b5c83bd2f08b44d69bdddc769946e6b8))
* **gates:** add expected_vs_actual gate result field — batch 6/6 ([3ccb366](https://github.com/1StepMore/AutoMedia/commit/3ccb36602c0c5fd9e3fc22d5fe77f4e70be4bdf0))
* **gates:** Add LLM evaluation path to G1 humanizer (G0 pattern, regex fallback) ([44cab68](https://github.com/1StepMore/AutoMedia/commit/44cab68d2ccdc1bf3e804201d9077786bd9ebe5f))
* **gates:** add RL6 gate naming enforcement and RL7 failure_modes completeness check ([2cee120](https://github.com/1StepMore/AutoMedia/commit/2cee120d788a7b4c360a745a8b71bc1e04da30ef))
* **gates:** implement BaseGate ABC + GateRegistry ([0b17e1d](https://github.com/1StepMore/AutoMedia/commit/0b17e1de0856b1e529acb2800543753af9190609))
* **gates:** implement ContentWriterGate for LLM-based article generation ([4819e6a](https://github.com/1StepMore/AutoMedia/commit/4819e6a0e30ce3360672398208b85c5b6d039e59))
* **gates:** implement G0 fact_check gate ([8d4c187](https://github.com/1StepMore/AutoMedia/commit/8d4c187ab1d5d46219d4b3c9d9d6a4cc340037dc))
* **gates:** implement G1 humanizer gate with 9 AI pattern detectors ([e2725d4](https://github.com/1StepMore/AutoMedia/commit/e2725d4c7de8db9c24529354f488ba6332aa7650))
* **gates:** implement G2 copy_review 5-round structural review ([96f871b](https://github.com/1StepMore/AutoMedia/commit/96f871b043b6c38c5531f4863615622104b1ce8f))
* **gates:** implement G3 brand_cta zero-tolerance gate ([367a600](https://github.com/1StepMore/AutoMedia/commit/367a600e3ec643b9817e8f74bb409de1cc9979c2))
* **gates:** implement G4 wechat_checklist + G5 html_hard gates ([359ce94](https://github.com/1StepMore/AutoMedia/commit/359ce94bd3b75dc28f3e360edaa60dda76d9a100))
* **gates:** implement L1-L3 lifecycle + topic_selection gates ([ea3f2c1](https://github.com/1StepMore/AutoMedia/commit/ea3f2c13124073764703a4876be4f9c7e154bfbc))
* **gates:** implement V0-V7 video track gates (8 gates) ([40b73da](https://github.com/1StepMore/AutoMedia/commit/40b73da1b83be4368c2f3b6f3c828dfec94e4edd))
* **hitl:** implement HITL Framework with 2 presets ([f07cacb](https://github.com/1StepMore/AutoMedia/commit/f07cacb6d48e84f0ce6fd18211e2f8b522d0108d))
* **hooks:** implement GateHook Protocol with read-only observer ([dfccdba](https://github.com/1StepMore/AutoMedia/commit/dfccdbaf28dec1a5835f209551971519a5ac9846))
* **hooks:** implement MD5 tracking for pipeline artifacts ([539a554](https://github.com/1StepMore/AutoMedia/commit/539a554096c66becb45bd11a852f3a3f6a6509c3))
* **hyperframes:** pass chrome_path as HYPERFRAMES_BROWSER_PATH env var ([70d7a05](https://github.com/1StepMore/AutoMedia/commit/70d7a05617e34e02f85015364a5271a7807cf6f5))
* **infra:** Wave 1 foundation — structured output fallback, Jinja2 prompts, decision_mode deprecation, baseline ([8bbcb82](https://github.com/1StepMore/AutoMedia/commit/8bbcb82b35d5baf9b8d0180368e985268358e4fa))
* **infra:** Wave 1-2 — LLM helpers, dead code removal (tenant/license/sop/decision CLI/dependency/preflight) ([e580c8a](https://github.com/1StepMore/AutoMedia/commit/e580c8ab4760c2d2a16f99da5607c3950684df31))
* **infra:** Wave 2-3 — D0 removal, Pydantic models, enhanced prompts, test mocks ([0360184](https://github.com/1StepMore/AutoMedia/commit/0360184169356d0e8265d2593f058b0874cdb099))
* **infra:** Waves 3-4 — MCP tools wiring, decision layer deletion, artifact preservation ([9a07712](https://github.com/1StepMore/AutoMedia/commit/9a0771259028d0064de042259481538c8413fb14))
* **infra:** Waves 5-8 — G0/G2 LLM conversion, cleanup, docs, final verification ([cab2c2a](https://github.com/1StepMore/AutoMedia/commit/cab2c2a55216d4934333108d2fc3f1b548380332))
* **license:** implement open-core license system ([00e042f](https://github.com/1StepMore/AutoMedia/commit/00e042fef2f8541ee6759a020c4b1614e469a164))
* **mcp:** add 4 new LLM-driven MCP tools (18→22 tools) ([af4c200](https://github.com/1StepMore/AutoMedia/commit/af4c2009f172bd5f550fc7865618e365144bca2c))
* **mcp:** add engine_health + update_engine_config tools, dynamic tool count ([a40ace5](https://github.com/1StepMore/AutoMedia/commit/a40ace5ecca3f9d81e20a6fef374b1c4001d1f93))
* **mcp:** add non-blocking run_pipeline and get_pipeline_progress tools ([677b28d](https://github.com/1StepMore/AutoMedia/commit/677b28d4ed2188a79638d1c612dec8179f1a6144))
* **mcp:** Add Pattern-A mode alongside 4 MCP tools (pattern='a'|'b') ([73abbb5](https://github.com/1StepMore/AutoMedia/commit/73abbb56b31030059d42a14b77865aedf76940e0))
* **mcp:** add search_assets, get_cron_health, test_cron_schedule tools ([b4a1261](https://github.com/1StepMore/AutoMedia/commit/b4a12614c243cd9b9857e5d2d4568fc856989f33))
* **mcp:** add server_types.py and mcp_error.py foundation ([28f0636](https://github.com/1StepMore/AutoMedia/commit/28f06362f117c0c2144b1b46b9f310f6fb6ccbc5))
* **mcp:** enhance register_platform_adapter stub with validation and docs ([9454310](https://github.com/1StepMore/AutoMedia/commit/9454310d97a804e537673d45f5afe5540cabafd1))
* **mcp:** implement MCP server with 8 tools + path allowlist ([fcea85d](https://github.com/1StepMore/AutoMedia/commit/fcea85d4add3279fcb4191553722fe24930cf065))
* **mcp:** pipeline control flags and retry metadata in GateEngine ([4594453](https://github.com/1StepMore/AutoMedia/commit/4594453bb322b8df6a0e271f5e473a178cb54663))
* **mcp:** pipeline control MCP tools and mcp_help introspection tool ([d8264ba](https://github.com/1StepMore/AutoMedia/commit/d8264bada2d5284ccfab37588a3fe788384be8d6))
* **mcp:** type constraints, structured errors, and E501 fixes on tools/accounts ([3f1750c](https://github.com/1StepMore/AutoMedia/commit/3f1750c071c23515dcf4f2f729a7fadbdde95f46))
* **omni:** implement PRD-2 Omni triad adapter subsystem ([12f3473](https://github.com/1StepMore/AutoMedia/commit/12f34739ea47354b33dc7185569a887a8e58d1ea))
* **pipeline:** Add LLM-generated detailed image prompts for ComfyUI ([e09390a](https://github.com/1StepMore/AutoMedia/commit/e09390a48865be1599ded324d8d35a77c5bc3c14))
* **pipeline:** add video production step in runner.py + full engine test suite (82 tests) ([a1b68ec](https://github.com/1StepMore/AutoMedia/commit/a1b68ec0e69210f0df764b4e46052d93a399ba82))
* **pipeline:** implement audio pipeline (edge-tts TTS + Whisper ASR) ([fb75291](https://github.com/1StepMore/AutoMedia/commit/fb75291b2ee6de58a23d739d3fa70c3588eb2616))
* **pipeline:** implement image pipeline (ComfyUI + PIL + Vision QA deg) ([a01036f](https://github.com/1StepMore/AutoMedia/commit/a01036f7c7bdbb74e7f30debec49b74ed0cee291))
* **pipelines:** add pipeline progress tracking with GateProgressEvent ([59aac4b](https://github.com/1StepMore/AutoMedia/commit/59aac4b7ae022a2d092ad9a10593b62e2c240c59))
* **pipelines:** implement GateEngine + run_full_pipeline runner ([01439f4](https://github.com/1StepMore/AutoMedia/commit/01439f407f71076316a3c3852be8e6b36a9b6f8d))
* **pool:** Add LLM semantic scoring alongside keyword correlation ([6d5879b](https://github.com/1StepMore/AutoMedia/commit/6d5879b00658424e392078aba462991a07d50ef1))
* **pool:** implement collector, scorer, dedup subsystems ([709e221](https://github.com/1StepMore/AutoMedia/commit/709e221984238aa70e42f6abd2269f93a53b5592))
* provision default hyperframes project in engine ([7a22f45](https://github.com/1StepMore/AutoMedia/commit/7a22f45f2773edea8bf3220762a1aedeb9004074))
* **sop:** implement SOP Runner with Jinja2 templates ([bdff39d](https://github.com/1StepMore/AutoMedia/commit/bdff39d4f2c20acf8cd28224dddf0c256b7aa61d))
* **tenant:** implement multi-tenant core subsystem ([043912f](https://github.com/1StepMore/AutoMedia/commit/043912faed2af8ac34ce0473ef9f27a9d6cff748))
* **test:** implement E2E test suite + 8 Red Line enforcement ([397635d](https://github.com/1StepMore/AutoMedia/commit/397635d556f5acce05bdc95d6f4d93cafcb6a471))


### Bug Fixes

* 3 real bugs found by real E2E workflow test ([0da4285](https://github.com/1StepMore/AutoMedia/commit/0da42857b4f82fea234850aa086825cf759cddce))
* 3 test isolation issues ([#27](https://github.com/1StepMore/AutoMedia/issues/27), [#28](https://github.com/1StepMore/AutoMedia/issues/28), [#29](https://github.com/1StepMore/AutoMedia/issues/29)) ([85c7087](https://github.com/1StepMore/AutoMedia/commit/85c70879e95723c9c471a1042a674724f9b47078))
* add continue-on-error to pip-audit & trivy (pre-existing dependency/infra issues) ([962d24c](https://github.com/1StepMore/AutoMedia/commit/962d24cfacf5e13da023fc30ceb63764bbaa9c88))
* **changelog:** register_omni_adapter → register_platform_adapter ([139c3da](https://github.com/1StepMore/AutoMedia/commit/139c3dacbfd7eafcd999d876133a0b0293274717))
* **ci:** add dev extras group with test dependencies (openai, mcp, cryptography) ([088086f](https://github.com/1StepMore/AutoMedia/commit/088086fe31d624777323c459a580b9b48ec8a024))
* **ci:** add missing build.py module with 4 build-mode decision agents ([ed98b17](https://github.com/1StepMore/AutoMedia/commit/ed98b17d98b4e31bb849eeee7b30c52a1f2fac21))
* **ci:** add missing Pillow dependency to fix CI import error ([1e15344](https://github.com/1StepMore/AutoMedia/commit/1e15344ab4eab330176f974d7901a815d00ee175))
* **ci:** align build.py agent implementations with E2E test expectations ([0333532](https://github.com/1StepMore/AutoMedia/commit/03335328cc1fbaffdabc0b2bc0719c887b80c19c))
* **ci:** align build.py agents with unit test expectations for fields, metadata, phase ([9f62e9d](https://github.com/1StepMore/AutoMedia/commit/9f62e9d62f7931bd0d44eeb7bb666f7ebc6b76b4))
* **ci:** disable rich ANSI color in CliRunner for test_omni_flag_in_help ([0a07b1b](https://github.com/1StepMore/AutoMedia/commit/0a07b1bb16cb75d00e8cc0d7b109b3673d563bf5))
* **ci:** fix mypy invalid --exit-zero flag and gitleaks shallow clone ([f84fcf1](https://github.com/1StepMore/AutoMedia/commit/f84fcf1061eab2f3669a007ab1cf07ef51af82cd))
* **ci:** guard ol_mcp import with ImportError for graceful degradation ([2adbc9b](https://github.com/1StepMore/AutoMedia/commit/2adbc9b250a55ed72ef10ee00858b76e46ea08db))
* **ci:** handle ImportError before FileNotFoundError for ol_mcp graceful degradation ([b8b042d](https://github.com/1StepMore/AutoMedia/commit/b8b042d51bf57cbe28541523a7c15313021d1eeb))
* **ci:** replace typing.override with typing_extensions.override for Python 3.11 compat ([110eb1b](https://github.com/1StepMore/AutoMedia/commit/110eb1b6bbd584024d496d66d1a085ba31707fdb))
* **ci:** strip ANSI codes from CliRunner output in test assertions ([f71aa59](https://github.com/1StepMore/AutoMedia/commit/f71aa5986185ecbe264df61300e08f57e5015024))
* **ci:** track dependency-graph.yaml in git (was excluded by .gitignore) ([3b80ff1](https://github.com/1StepMore/AutoMedia/commit/3b80ff1c2045c065c1fb145850a2032b60764da3))
* clean up .gitignore, git-tracked artifacts, and systemd config ([ebb9ba1](https://github.com/1StepMore/AutoMedia/commit/ebb9ba1425851bed369bb46a2f095784716d9fb4))
* **cli:** add retry kwargs to CLIPipelineProgress to prevent TypeError on quality retry ([#32](https://github.com/1StepMore/AutoMedia/issues/32)) ([15461b3](https://github.com/1StepMore/AutoMedia/commit/15461b322e45630b2742e61037aaba97bf5dd245))
* **cli:** fix typer._click import crash for typer&lt;0.12 ([472fac9](https://github.com/1StepMore/AutoMedia/commit/472fac9451ef058add362dfe3c0df1cb10d69108))
* **cli:** resolve 8 ruff lint errors across CLI commands ([34e2bc2](https://github.com/1StepMore/AutoMedia/commit/34e2bc286d0842d1b41ae266c6594df8273bdaf2))
* **cli:** validate empty string for --brand CLI option ([#33](https://github.com/1StepMore/AutoMedia/issues/33)) ([55ded78](https://github.com/1StepMore/AutoMedia/commit/55ded783ecbb993587479e0af70fd00d7ab9e22a))
* core quality improvements across all modules ([2189515](https://github.com/1StepMore/AutoMedia/commit/21895159918bac8d79497419a50291fe0eb06f37))
* **core:** fix env-to-config LLM key mapping and numeric type conversion ([409f283](https://github.com/1StepMore/AutoMedia/commit/409f28357a38799b8360b4340b143733ba7617cd))
* **deps:** add httpx as explicit dependency ([d35e119](https://github.com/1StepMore/AutoMedia/commit/d35e1198c17a14be695913b113b7db3ca808079a))
* **deps:** add missing click dependency, lazy-import httpx in oauth2 ([c0f043d](https://github.com/1StepMore/AutoMedia/commit/c0f043d8db40bfb4569adc7fc52bc2c683bc4fd7))
* **engines:** generate valid ComfyUI node-graph workflow instead of metadata dict ([b5054f1](https://github.com/1StepMore/AutoMedia/commit/b5054f148334717e750b1a518b7234b660abd8f1))
* fix project directory numbering — 03_subtitle→04_subtitle, 04_review→05_review, 05_publish→06_publish ([418e068](https://github.com/1StepMore/AutoMedia/commit/418e06850d3f08d3a0a885a0e31df72647d83cc9))
* **gates:** Change G2 enable_llm default to True (match G0) ([f2c5756](https://github.com/1StepMore/AutoMedia/commit/f2c5756508de0652871fc05c04b3e104f8e1dfba))
* **gates:** guard G3 brand_cta against None brand_profile crash ([#34](https://github.com/1StepMore/AutoMedia/issues/34)) ([ecd5849](https://github.com/1StepMore/AutoMedia/commit/ecd584991957de79b0068011dca7e85ce3c657f2))
* integrate D0 Gate, R9 status, force-provenance, pool migration ([c197e9f](https://github.com/1StepMore/AutoMedia/commit/c197e9f333f5dc190b469b7f75106359088ee437))
* **mcp:** add development paths to allowlist ([cabb524](https://github.com/1StepMore/AutoMedia/commit/cabb5247327d5e29a392b5488a1a682c715656c4))
* **mcp:** Add error handling to 2 tools + add pool_add_topic + publish_content tools ([33e1a4c](https://github.com/1StepMore/AutoMedia/commit/33e1a4c2bb6c5eb4b428801e196ef94ba2f5d7e4))
* **mcp:** clarify research_topics TAVILY dependency; feat(docs): native skill copies per agent ([938e16b](https://github.com/1StepMore/AutoMedia/commit/938e16bd72d7e79d09b1d06bdd25c79af5e89fae))
* **mcp:** migrate last old-format error, structure mcp_help with parameters, refresh docstrings ([7b998bb](https://github.com/1StepMore/AutoMedia/commit/7b998bb5b6f7b1a797f78f12f44927fecfe8198b))
* pre-existing test failures — GateRegistry isolation, E2E marker, name conflicts ([26ec2e7](https://github.com/1StepMore/AutoMedia/commit/26ec2e7f4c5fb9d9946b854294a79389ac7c4aad))
* remove dead loop in collector.py (leftover from prior refactor) ([620d857](https://github.com/1StepMore/AutoMedia/commit/620d857e7f9aaf99902908dde2e8c3b5b1998cd2))
* remove pip-audit --fail-on flag (removed in v2.10+), fix 13 mypy errors ([ec6cc8b](https://github.com/1StepMore/AutoMedia/commit/ec6cc8b457298aa8a3d237e566c6d6cc774aa2bb))
* replace assert with cast to fix ruff S101 ([cefb6f3](https://github.com/1StepMore/AutoMedia/commit/cefb6f3d38a93f64e9ff4a3bff6e1ee90bb16a65))
* resolve CI failures across lint, security scan, checkov, and docker build ([e38ac16](https://github.com/1StepMore/AutoMedia/commit/e38ac16518378930f8bf51f82e73eba86e3d1db9))
* resolve CI failures and bump to v1.0.1 ([3035c64](https://github.com/1StepMore/AutoMedia/commit/3035c64983d602accc8d1998e70dbdc889400cea))
* resolve G82 test conflict and connect research_topics to Tavily ([2e3a577](https://github.com/1StepMore/AutoMedia/commit/2e3a5775db4425c18f7bdf3964070569dd3a64a7))
* resolve mypy syntax error in gate_engine.py ([98cbd85](https://github.com/1StepMore/AutoMedia/commit/98cbd859ce92107a5f25352598ed4731b93d6836))
* resolve ruff import-ordering error and remove duplicate MIT License classifier ([86eeba8](https://github.com/1StepMore/AutoMedia/commit/86eeba8ead18e1bd2edb3c65ad298521ad967a5c))
* **security:** add _require_allowed() check to publish_content MCP tool ([52f2812](https://github.com/1StepMore/AutoMedia/commit/52f2812a34c54307da7322b5c71f9155d45b32ab))
* swap isinstance(threading.Lock) for behavioral check - Lock is a factory fn, not a class ([db1edc6](https://github.com/1StepMore/AutoMedia/commit/db1edc645d835493e7ef9f84435b5af2bbde5282))
* **tests:** remove broken image_pipeline tests tied to legacy PIL fallback ([98f5223](https://github.com/1StepMore/AutoMedia/commit/98f5223b7f64b5cee38bfcb08bba85407b4ce3f3))
* **tests:** resolve 20 _USER_CFG_DIR test failures — use sys.modules to bypass init_cmd name shadowing ([89baeb1](https://github.com/1StepMore/AutoMedia/commit/89baeb10018c7f8b912f75f05691bdef89a660ed))
* **tests:** resolve gate name collisions between test gate files ([#31](https://github.com/1StepMore/AutoMedia/issues/31)) ([df22df2](https://github.com/1StepMore/AutoMedia/commit/df22df23cc9f3d4a720931d9a66634fe15235dbc))
* **tests:** update gate and smoke tests for engine abstraction compat ([b85d0df](https://github.com/1StepMore/AutoMedia/commit/b85d0df7fe61a318b93f1dd2071cc09a55027b7d))
* update MCP tool count from 33 to 41 in server.py ([07f6950](https://github.com/1StepMore/AutoMedia/commit/07f69502b8a36ea7d011f8d8330948af42309450))
* **verification:** address Final Verification Wave findings ([184750d](https://github.com/1StepMore/AutoMedia/commit/184750d0506e3acb45921cd553207edc6dc71f47))


### Documentation

* add agent-orientation analysis — comprehensive codebase diagnosis and refactoring roadmap ([50f0817](https://github.com/1StepMore/AutoMedia/commit/50f081719064a1756550b3dea33fa79df65ca8b1))
* add CODE_OF_CONDUCT and convert CHANGELOG to English ([ef7c0aa](https://github.com/1StepMore/AutoMedia/commit/ef7c0aaec7435cf700dd49c05f11855ff7cd72b2))
* add full documentation set (11 files) ([1ba61b9](https://github.com/1StepMore/AutoMedia/commit/1ba61b9f857e95885b7e4eb642a181419fcefd1a))
* add PRD-2 and PRD-3 documentation ([20385fb](https://github.com/1StepMore/AutoMedia/commit/20385fb2bc862fd452c7af8f747032e36b89fe9d))
* archive agent-orientation-analysis, sync 8 dev docs with founder-expectations ([dad7b73](https://github.com/1StepMore/AutoMedia/commit/dad7b73c0f53bd36980c780adcad6255f3d98996))
* fix documentation errors across README, AGENTS.md, and docs/ ([838db1f](https://github.com/1StepMore/AutoMedia/commit/838db1f60166daa92f1a6657ae4febeeb119e74c))
* fix mkdocs.yml broken navigation entries (remove 4 non-existent file refs) ([6723641](https://github.com/1StepMore/AutoMedia/commit/6723641e4c6a1a1b8c9bed60a6dc52dc3d2e792f))
* fix outdated sections in coverage-gaps.md and decision-layer.md, add project-audit.md with engine abstraction design ([1233db1](https://github.com/1StepMore/AutoMedia/commit/1233db17a03dc92ec83e574a2c335442ba652973))
* improve docstring coverage to 100% module-level, 93.2% function-level ([622e3e1](https://github.com/1StepMore/AutoMedia/commit/622e3e16620a4cb08004fe6d24987be1fd02cead))
* pre-release doc freshness sweep ([f10d610](https://github.com/1StepMore/AutoMedia/commit/f10d6106862dfdfd6bb3860ad401239d55a8ae34))
* remove stale AGENTS.md references to removed modules (tenant/license/sop/decision) ([42906fa](https://github.com/1StepMore/AutoMedia/commit/42906fa02524e26f07a76340a957b9c0a0791e31))
* restructure documentation and update founder-expectations.md with D3 agent-oriented review ([a1d8d02](https://github.com/1StepMore/AutoMedia/commit/a1d8d025f8a55217b348ca060ade013e01633d00))
* restructure README to Docker-first, update AGENTS.md with agent-readiness improvements ([f578ef1](https://github.com/1StepMore/AutoMedia/commit/f578ef185976f6ae7e2e518d58bffe0e2c137ad0))
* sync with MCP changes — tool count 33→41, mode tables 4→8, skill policy, error format ([a8ded3d](https://github.com/1StepMore/AutoMedia/commit/a8ded3dd6d86770eba318b44e35a22ff772df365))
* translate Chinese documentation to English across 19 files ([7e74755](https://github.com/1StepMore/AutoMedia/commit/7e747557abfd231240068ab4b7746bcb2043f6d0))
* update CHANGELOG, README, AGENTS.md, and docs for PRD-4 accounts subsystem ([3a79418](https://github.com/1StepMore/AutoMedia/commit/3a79418e2b749b786a969c9753b9ee0b83af4472))
* update CHANGELOG, README, CLI reference, API reference ([0bd9acc](https://github.com/1StepMore/AutoMedia/commit/0bd9accb09b167403a7074b2fc344fabfbedfa48))
* update Documentation Index to reflect English-translated docs ([a2b0582](https://github.com/1StepMore/AutoMedia/commit/a2b05823516c469cafe455b838c06b0e805e66e3))
* update pip install references in docs/ ([22cee12](https://github.com/1StepMore/AutoMedia/commit/22cee1222668d8d4a27dbcb1250501970b712d40))
* update priority matrix - F37/F42 resolved, F42 search_assets implemented ([6b78fe6](https://github.com/1StepMore/AutoMedia/commit/6b78fe6be6ca0bcaf8e4d5bdbcda610b16b456c1))
* update PyPI project name in publish workflow comments ([f8d0d20](https://github.com/1StepMore/AutoMedia/commit/f8d0d20c5defdf5627ae360ff265f8bd10920b1c))
* update README and AGENTS.md with publish-ready links and counts ([c3773f9](https://github.com/1StepMore/AutoMedia/commit/c3773f9112311ab37fc90ae571c9bf9a88ba4cb1))

## [Unreleased]

### Added

- **Founder Gap Closure — F27 (Video Without HyperFrames)**: Pipeline now detects HyperFrames at startup via `shutil.which()`. When absent, V0-V7 video gates return `status="skipped"` with a clear warning and suggestion to use `--mode text_only`. Doctor checks for HyperFrames availability.

- **Founder Gap Closure — F18 (Progress API)**: `get_progress()` now returns `gates_done[]`, `gates_remaining[]`, and `total_gates` fields. Agents no longer need to parse events to compute remaining gates.

- **Founder Gap Closure — F25 (G0 Without Source Material)**: G0 fact-check gate now returns `status="skipped"` when no source data is provided (instead of trivially passing all checks). Added LLM plausibility check via `fact_check_g0_plausibility.j2` prompt when LLM is enabled.

- **Founder Gap Closure — F42 (Asset Search MCP Tool)**: `search_assets(query, brand, limit, filters)` MCP tool exposing combined SQLite keyword + Chroma semantic search across produced content.

- **Founder Gap Closure — F37 (Cron Health MCP Tools)**: `get_cron_health()` reports cron job validation status. `test_cron_schedule(expression, count)` validates cron expressions and computes next N trigger times.

- **Founder Gap Closure — F24 (G1 LLM Path Verification)**: Verified G1 humanizer's LLM-first detection path works end-to-end. F24 priority downgraded from 🔴 P0 to 🟢 Working well.

- **9 New Platform Adapters**: YouTube Data API v3, Twitter/X API v2, Reddit API, TikTok Content Posting API, Facebook Graph API, Instagram Graph API, LinkedIn Posts API v2, Medium API, WordPress REST API — all following the `wechat_publisher.py` pattern with `httpx`, registered in `AdapterRegistry`.

- **7 Manual-Only Platform Stubs**: Douyin, Bilibili, Weibo, Toutiao, Baijiahao, Kuaishou, Juejin — all documented as intentional divergences (no public API for automated publishing).

- **Pipeline Mode Expansion**: 8 modes fully implemented: `auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`.

- **Batch Production**: `--topics` flag for `automedia run` and `batch_run` MCP tool for sequential multi-topic execution.

- **Config Introspection**: `get_config(key)` MCP tool with secret redaction and dot-notation traversal.

- **Cron Schedule Management**: `add_cron_schedule`, `list_cron_schedules`, `remove_cron_schedule` MCP tools for dynamic cron management.

### Changed

- **founder-expectations.md**: Complete D3 review pass. F07 (8 modes), F09 (structured errors), F24 (G1 hybrid LLM), F25/F26 (stop-mode recovery corrected), F32 (removed IM notifiers), F34 (platform matrix honest statuses), F35 (PublishEngine retry), F37 (cron tools), F42 (config + search tools), F48 (v1 readable) all updated. Priority matrix and action items refreshed.

- **Error Formatting**: Tracebacks suppressed in user-facing output. `--verbose` flag added to CLI commands for debug tracebacks. MCP tools return structured dicts with `str(exc)`.

- **`AUTOMATION_DEFAULTS`**: Extended to include all 20 registered platform adapters with appropriate auto/manual defaults.

### Changed

- **G2 (Copy Review)**: `enable_llm` default changed from `False` to `True` to match G0 behavior. LLM-based review is now enabled by default. Set `enable_llm: false` in gate config to disable. Added `isinstance(config, dict)` guard for robustness.

### Added

#### Account & Publishing Management (PRD-4)

- **Encrypted Credential Store**: AES-256-GCM encrypted storage for platform credentials with atomic index writes and fingerprint deduplication (`accounts/store.py`)
- **Account Registry**: Full CRUD for platform accounts with label uniqueness enforcement per platform (`accounts/registry.py`)
- **Auth Flow Engine**: OAuth2 Client Credentials and Authorization Code flows with PKCE/state support, localhost server for interactive login, Cookie auth, API Key auth (`accounts/auth/`)
- **Session Manager**: TTL-aware token cache with per-account thread-safe locking, rate-limit backoff with configurable cooldown (`accounts/session.py`)
- **Account Models**: Pydantic v2 models for account metadata, credentials, sessions (`accounts/models.py`)
- **Platform Adapter Auth Integration**: `authenticate()`, `refresh_session()`, `check_health()`, `get_analytics()` methods on `BasePlatformAdapter` with concrete defaults; `account_ids` parameter on `PublishEngine.publish_all()` with partial failure continuation
- **CLI**: `automedia account connect|list|health|disconnect|refresh` — 5 subcommands (16 total)
- **MCP Tools**: `connect_account`, `list_accounts`, `get_account_health`, `disconnect_account` — 4 new tools (18 total)
- **Credential Bridging**: `load_credential_with_account_fallback()` in `credential_loader.py` for backward-compatible credential resolution
- **Test Coverage**: 191 PRD-4-specific tests across accounts models, store, registry, auth flows, session, CLI, and MCP — all passing

#### Security

- **Master Key Encryption**: All platform credentials encrypted at rest with AES-256-GCM; key derived from `AUTOMEDIA_MASTER_KEY` environment variable via SHA-256
- **Credential Leak Prevention**: `SessionToken.__repr__` masks access/refresh tokens (shows first 8 chars); account credentials never appear in logs or MCP responses

## [1.0.0] - 2026-07-07

### Added

#### Core Library

- **Three-Layer Entry Points**: Python SDK (`from automedia import run_full_pipeline`), CLI (`automedia`), MCP Server (`python -m automedia.mcp.server`) three ways to invoke the pipeline
- **Configuration System**: Six-layer priority config loading (`config_loader.py`), supports built-in defaults, project-level, user-level, overrides, environment variables
- **Project Management**: `Project.init()` creates standard directory structure, automatic slugify and safe path validation
- **Credential Management**: Four-layer credential loading (`credential_loader.py`): environment variables > keyring > oscreds.yaml > credentials.yaml
- **Health Checks**: `Doctor` class checks python/bun/ffmpeg/whisper/edge-tts/comfyui/chrome dependencies

#### Pipeline Orchestration

- **GateEngine**: Sequential Gate execution engine, supports "stop" and "rewrite" failure modes
- **`run_full_pipeline()`**: Complete pipeline execution function, supports mode/resume_from/config_dir/tenant_id parameters
- **Four Run Modes**: auto (full pipeline), text_only (copy only), video_only (video only), qa_only (QA only)

#### Gate System

- **BaseGate** abstract base class, auto-registers to `GateRegistry`
- **Copy Gates (G0-G5)**: Fact check, Humanizer (de-AI-ify), copy review, brand CTA, WeChat checks, HTML hard gate
- **Video Gates (V0-V7)**: Lint, Vision QA, Pre-Send Whisper, content semantic, TTS brand asset, MP3 vs SRT, subtitle render, six-step hard gate
- **Lifecycle Gates (L1-L3)**: Publish log schema, archive validation, platform integrity
- **Failure Mode Knowledge Base**: `failure_modes.py` records common failure reasons and fix steps for each Gate

#### Hook System

- **GateHook Protocol**: Readonly observer pattern, three methods: `before_gate`, `after_gate`, `on_gate_failed`
- **MD5 Tracking**: `md5_tracker.py` records and verifies MD5 hashes for each Gate's output (Red Line 7)

#### CLI

- `automedia run`: Execute pipeline, supports --mode, --resume-from, --timeout
- `automedia pool`: Topic pool management (list/add/prune/attach-brief)
- `automedia projects`: Project listing and details (list/get/get-assets)
- `automedia archive`: Project archive (Red Line 8 enforced)
- `automedia adapter`: Platform adapter management (list/create)
- `automedia cron`: Scheduled task execution and health check (run/check-health)
- `automedia init`: Interactive/minimal config initialization
- `automedia doctor`: Dependency and environment health check
- `automedia omni`: Omni Triad operations (extract/translate/convert)
- `automedia hitl`: Human-in-the-loop review flow (config/preset)
- `automedia license`: License management (check/features)
- `automedia sop`: SOP flow execution (generate)
- `automedia tenant`: Multi-tenant management (create/list/delete/invite/members/audit-log)
- `automedia solution`: Decision layer solutions (next-node/approve-node/complete-node/preflight-check/validate-artifact)
- `automedia onboard`: Guided configuration wizard (list)

Total 15 top-level commands, 50+ subcommands.

#### MCP Server

- 13 MCP tools: select_topic, run_pipeline, get_pipeline_progress, get_pipeline_status, list_projects, get_project_assets, archive_project, list_topic_pool, register_platform_adapter, extract_brief, localize_content, localize_output, format_output
- Path allowlist security mechanism
- stdio transport, compatible with Claude Desktop / OpenCode / Cline / Codex CLI / Hermes Agent

#### Adapter System

- **BasePlatformAdapter**: Abstract base class defining publish/validate/platform_name
- **AdapterRegistry**: Global singleton registry, supports register/get/list/clear
- **Template Generation**: `automedia adapter create` generates adapter template code

#### Topic Pool

- **PoolDB**: SQLite topic pool CRUD, supports schema creation and migration
- **Scoring and Dedup**: Basic scorer and deduplication logic

#### Tech Stack

- Python 3.11+
- Typer (CLI)
- Pydantic 2.x (data models)
- PyYAML (configuration)
- MCP official Python SDK (MCP Server)
- SQLite3 (topic pool)

#### Documentation

- **Developer Guide** (`docs/dev/developer-guide.md`)
- **API Reference** (`docs/user/api-reference.md`)
- **CLI Reference** (`docs/user/cli-reference.md`)
- **MCP Setup Guide** (`docs/user/mcp-setup.md`)
- **Runbook**: Gate failure modes / Cron debugging / API pitfalls / Production workflow

### Changed

- Hermes Agent v0.17 coupling fully decoupled, all 20 coupling points resolved (17 resolved, 3 isolated)
- `skill_view(name='...')` to pure Python class + typer CLI
- `execute_code` sandbox to pure Python execution
- Hermes cron to external crond + `automedia cron run`
- `~/.hermes/` to `~/.automedia/` config directory
- OpenCode Go binding to swappable provider (OpenAI/Anthropic)
- Brand hardcoding to brand-profile.yaml configuration
- MiniMax API dependency completely removed

### Removed

- Hermes Agent runtime dependency
- `sys.path.insert` hack
- All user home directory and workspace hardcoded paths removed
- `hermes.*` runtime API calls
- Hermes proprietary log format and cron jobs.json

### Security

- Path safety: `sanitize_path()` rejects path traversal (`..`, `~`, `//`)
- Archive red line: agents must not archive, only user `--force` can bypass
- MCP path allowlist
- Credentials are not written to config files, loaded via environment variables or keyring
- tenant_id field reserved (multi-tenant foundation)
