---
title: Developer Guide
description: Build the AutoMedia development environment from scratch, including prerequisites, installation steps, and development workflow.
---

# AutoMedia Developer Guide

## From Scratch Setup

### Prerequisites

AutoMedia depends on the following external tools at runtime. Make sure they are in your `$PATH` before installing the package:

- Python 3.11+
- FFmpeg
- Bun (for HyperFrames rendering)
- edge-tts CLI
- Whisper (faster-whisper or openai-whisper)
- Chrome/Chromium (headless mode)
- ComfyUI (optional, image generation)

> **Tip:** All external dependencies come pre-installed in the Docker image. Use `docker run -it --rm kevinzhow/automedia-pipeline:latest automedia doctor` to verify without local setup.

#### Python 3.11+

| Platform | Install |
|----------|---------|
| Ubuntu | `sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv python3-pip` |
| macOS | `brew install python@3.11` |
| Windows | `winget install Python.Python.3.11` or download from [python.org](https://www.python.org/downloads/) |

Verify: `python3 --version` (or `python --version` on Windows)

#### FFmpeg

| Platform | Install |
|----------|---------|
| Ubuntu | `sudo apt-get update && sudo apt-get install -y ffmpeg` |
| macOS | `brew install ffmpeg` |
| Windows | `winget install "FFmpeg (Essentials Build)"` or download from [ffmpeg.org](https://ffmpeg.org/download.html) |

Verify: `ffmpeg -version`

#### Bun

| Platform | Install |
|----------|---------|
| Ubuntu / macOS | `curl -fsSL https://bun.sh/install \| bash` |
| Windows | `powershell -c "irm https://bun.sh/install.ps1 \| iex"` |
| Any (via npm) | `npm install -g bun` |

Verify: `bun --version`

#### edge-tts CLI

```bash
pip install edge-tts
```

Verify: `edge-tts --help`

#### Whisper

Choose one:

```bash
# faster-whisper (recommended)
pip install faster-whisper

# openai-whisper (alternative)
pip install openai-whisper
```

Verify:

```bash
python -c "import faster_whisper; print(faster_whisper.__version__)"
# or
python -c "import whisper; print(whisper.__version__)"
```

#### Chrome/Chromium

| Platform | Install |
|----------|---------|
| Ubuntu | `sudo apt-get update && sudo apt-get install -y chromium-browser` |
| macOS | `brew install --cask google-chrome` |
| Windows | `winget install Google.Chrome` |

Verify: `google-chrome --version` (or `chromium-browser --version` on Ubuntu)

#### ComfyUI (optional)

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt
```

See the [ComfyUI repository](https://github.com/comfyanonymous/ComfyUI) for full setup.

Verify: `http://localhost:8188` is reachable after starting the server.

### Installation

```bash
# Clone the repository
git clone <repo-url> && cd AutoMedia

# Editable mode install
pip install -e .

# Install optional dependencies
pip install -e ".[mcp]"     # MCP server support
pip install -e ".[openai]"  # OpenAI provider
pip install -e ".[anthropic]" # Anthropic provider
pip install -e ".[rich]"    # Rich text CLI output
```

### Initialization

```bash
# Interactive initialization — configure LLM provider and API key
automedia init

# Minimal config (non-interactive)
automedia init --template minimal

# File structure:
# .automedia/
#   config.yaml            # LLM provider, base_url, api_key
```

### Health Check

```bash
automedia doctor
```

Example output:

```
Dependency Check:
------------------------------------------------------------
Tool             Installed    Version
------------------------------------------------------------
✓ python         yes          3.11.4
✓ bun            yes          1.1.30
✓ ffmpeg         yes          ffmpeg version 7.0.2
✓ whisper        yes          whisper 20240930
✓ edge-tts       yes          edge-tts 6.1.3
✗ comfyui        no           -
✓ chrome         yes          Google Chrome 126.0.6478.126
------------------------------------------------------------
```

Missing dependencies are marked in red. The system will not block execution, but the corresponding Gate will report an error at runtime.

### Running the Pipeline

```bash
automedia run --topic "AI Video Generation Tool Comparison" --brand my-brand
```

## Architecture Overview

AutoMedia uses a three-layer architecture:

```
External Call Layer
  Any MCP Client / Python SDK / CLI Terminal
        |              |              |
        v              v              v
  ┌──────────────────────────────────────┐
  │         MCP Server Layer             │  mcp official Python SDK
   │   select_topic, run_pipeline, ...    │  50 tools
  └────────────────┬─────────────────────┘
                   │
  ┌────────────────┴─────────────────────┐
  │         CLI Layer (typer)            │  automedia run / pool / ...
  └────────────────┬─────────────────────┘
                   │
  ┌────────────────┴─────────────────────┐
  │     automedia/ Core Python Package    │
  │                                      │
  │  core/      pipelines/    gates/     │
  │  adapters/  manifests/   hooks/      │
  │  pool/      cron/        mcp/        │
  └──────────────────────────────────────┘
```

### Core Subpackages

| Subpackage | Responsibility |
|------|------|
| `core/` | Configuration loading (`config_loader.py`), project management (`project.py`), credential management (`credential_loader.py`), health check (`doctor.py`), overrides (`overrides.py`), media specs (`media_spec.py`), workflows (`workflow.py`) |
| `pipelines/` | Pipeline orchestration (`runner.py`), Gate engine (`gate_engine.py`), audio/video pipelines |
| `gates/` | 21 Gate implementations including H0 + failure mode knowledge base (`failure_modes.py`) |
| `adapters/` | Platform publish adapter registry (`registry.py`) + base class (`base.py`) |
| `hooks/` | GateHook Protocol (`protocol.py`), MD5 tracking (`md5_tracker.py`) |
| `manifests/` | Built-in YAML default config (`defaults.yaml`), schema definitions |
| `pool/` | Topic pool SQLite database (`db.py`), collection/scoring/dedup |
| `cron/` | Scheduled job YAML definitions (`jobs.yaml`), pipeline schedule runner (`runner.py`) |
| `mcp/` | MCP Server implementation (`server.py`), stdio transport |
| `prompts/` | Built-in Jinja2 prompt templates (11 templates) with platform-scoped resolution (21 platform overrides for 7 platforms) |

### Unified Three-Layer Entry Point

All three layers share the same `run_full_pipeline()` implementation, avoiding code duplication:

```
CLI (typer)  -- parse argv --> call run_full_pipeline() -- print result
MCP Server   -- JSON-RPC  --> call run_full_pipeline() -- return JSON
SDK          -- import    --> call run_full_pipeline() -- return Python object
```

## Development Workflow

### Project Structure

```
automedia/                  # Core Python package
  core/                     # Infrastructure
  pipelines/                # Pipeline orchestration
  gates/                    # Gate implementations
  adapters/                 # Platform adapters
  hooks/                    # GateHook
  manifests/                # Config file schema
  pool/                     # Topic pool
  cron/                     # Scheduled tasks
  prompts/                  # Jinja2 prompt templates
  mcp/                      # MCP Server
  cli/                      # Typer CLI
tests/                      # Test directory
  test_cli/
  test_mcp/
  test_e2e/
docs/                       # Documentation (user/ + dev/)
```

### Running Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src/automedia

# Specific test file
pytest tests/test_runner.py

# E2E red line tests
pytest tests/test_e2e/ -v
```

### Adding a New Gate

1. Create a new file under `automedia/gates/`, inheriting from `BaseGate`
2. Define `_gate_name` and `_failure_mode` class attributes
3. Implement the `execute(self, gate_context) -> dict` method
4. Add a failure mode entry in `failure_modes.py`
5. Register the gate in `runner.py`'s gate lists if it should be included in any pipeline mode
6. Add corresponding tests in `tests/`

```python
from automedia.gates.base import BaseGate

class MyNewGate(BaseGate):
    _gate_name = "GX"
    _failure_mode = "stop"

    def execute(self, gate_context):
        # Your logic
        return {"passed": True, "gate": self._gate_name}
```

### Adding a New CLI Command

1. Create a file under `automedia/cli/commands/`
2. Define the command using typer
3. Register it in `automedia/cli/app.py`

### Gate Naming Convention

| Prefix | Range | Example |
|------|------|------|
| G0-G5 | Copy Gates | Fact check, humanizer, copy review, brand CTA |
| V0-V7 | Video Gates | Lint, Vision QA, Whisper, subtitle rendering |
| H0 | Human Review Gate | Human-in-the-loop content and video approval |
| L1-L4 | Lifecycle Gates | Publish log, archive validation, platform integrity, translation quality |

### Pipeline Modes

The pipeline supports eight modes, each running a different subset of gates. The mode is selected via the `--mode` CLI flag, the `mode` parameter in the SDK, or the `mode` field in the MCP `run_pipeline` tool.

| Mode | Gates Executed | Use Case |
|------|---------------|----------|
| `auto` | pre-gate → CW → G0-G5 → V0-V7 → H0 → L1-L4 | Full production pipeline: topic validation, content writing, all copy and video gates, lifecycle checks |
| `text_only` | CW → G0-G5 → L1-L4 | Draft-only output: content writing and copy gates, no video/rendering gates |
| `text_with_cover` | CW → G0-G5 → V0 → L1-L4 | Text output plus a single cover image |
| `video_only` | V0-V7 → H0 → L1-L4 | Video-only: reuse an existing draft, run all video and lifecycle gates |
| `image-carousel` | CW → G0-G5 → V0 → V6 → L1-L4 | Carousel-image output for social platforms |
| `social-thread` | CW → G0-G5 → L1-L4 | Thread-style posts for social platforms |
| `short-video` | CW → G0-G5 → V0-V6 → H0 → L1-L4 | Short-form video (e.g. TikTok/Reels) |
| `qa_only` | G0 → G2 → G3 → V1 → V6 | Selective QA pass on existing content: targeted copy and video checks |

Gate lists are defined in `src/automedia/pipelines/runner.py` as `_AUTO_GATE_NAMES`, `_TEXT_ONLY_GATE_NAMES`, `_VIDEO_ONLY_GATE_NAMES`, and `_QA_ONLY_GATE_NAMES`.

## Configuration Hierarchy

Six layers stack from lowest to highest priority, with higher priority overriding lower:

1. Built-in `automedia/manifests/defaults.yaml`
2. Project `.automedia/` directory
3. User `~/.automedia/` directory
4. `~/.automedia/overrides/rules/*.yaml`
5. `~/.automedia/overrides/prompts/*.j2`
6. Environment variables `AUTOMEDIA_*` + explicit overrides parameter

## Key Technical Decisions

- **Gate blocking**: If a Gate with `failure_mode="stop"` fails, the Pipeline stops immediately
- **GateHook read-only**: Hooks are observers, cannot modify Gate behavior
- **MD5 tracking**: Each Gate's output is written to `pipeline_md5.json`, Red Line 7
- **Archive red line**: Only user `--force` can archive, agent must not archive (Red Line 8)
- **External scheduling**: External crond calls `automedia cron run`, no built-in scheduler

## Enforcement Mechanisms

<!-- Condensed from: docs/archived/enforcement-mechanisms.md (full historical version archived) -->

### RL8 — Archive Constraint (HARD, Automated)

The `archive_project` MCP tool and `automedia archive` CLI command refuse to archive a project unless its status is `"published"` or the `--force` flag is explicitly passed. This enforces Red Line 8, the core constraint that only the user may force-archive.

- **Location:** `automedia/mcp/server.py` (MCP tool), `automedia/cli/commands/archive.py` (CLI command)
- **How it works:** Checks project status before archiving. Rejects if status is not `published` and `--force` is not set.
- **Bypass:** `--force` / `force=True` (user only, agents must not use)

### Pre-Commit Hooks (SOFT, Automated)

`.pre-commit-config.yaml` configures ruff, mypy, conventional commits, and other checks, running automatically on every `git commit`. Can be skipped with `--no-verify`, but GitHub CI still catches failures.

- **Location:** `.pre-commit-config.yaml`
- **How it works:** pre-commit framework executes all hooks before each commit.
- **Bypass:** `git commit --no-verify` (CI provides a safety net)

### Gate Failure Modes (SOFT, Automated)

Every pipeline gate defines a `_failure_mode` attribute:

- **`"stop"`:** halts the entire pipeline on failure
- **`"retry"`:** automatically retries the gate (triggers content regeneration)

Defined in `automedia/gates/failure_modes.py`. See `docs/dev/gate-failure-modes.md` for details.

### H0 Human Review Gate (SOFT, Automated)

`H0HumanReviewGate` pauses the pipeline before publishing, waiting for human approval. Skips automatically when `auto_publish=True` is configured.

- **Location:** `automedia/gates/h0_human_review.py`
- **CLI:** `automedia hitl approve &lt;project_id&gt; H0`
- **Bypass:** `--skip-review` flag or `auto_publish=True` config

### Red Lines (Discipline Constraints, Not Automated)

Beyond RL8 (automated), the remaining red lines rely on developer discipline and code review.

| RL | Constraint | Enforcement |
|----|-----------|-------------|
| RL1 | Must not archive non-published projects with `--force` | Automated |
| RL2 | Must not commit production data, topic pool contents, or credentials to git | Developer discipline |
| RL3 | Must not modify `mcp_allowlist.yaml` without explicit user request | Developer discipline |
| RL4 | Tests must use synthetic fixtures from `tests/fixtures/synth/` | Developer discipline |
| RL5 | Must use `automedia archive` command, never manual directory operations | Developer discipline |
| RL6 | Follow gate naming convention: G0-G5, V0-V7, L1-L4, H0, CW, pre-gate | Developer discipline |
| RL7 | Must add new gates to `failure_modes.py` | Developer discipline |
| RL8 | Must run pre-commit checks before committing | Pre-commit hooks (automated) |
| RL9 | Respect GateHook readonly contract -- observe but do not modify | Developer discipline |

> Note: RL numbering matches AGENTS.md section 5. Original RL9 (decision provenance) has been removed.

### Gate List

21 gates across six phases. Gate order: pre-gate `→` CW `→` G0-G5 `→` V0-V7 `→` H0 `→` L1-L4.

| Phase | Gate | Name | Failure Mode |
|-------|------|------|-------------|
| Pre | pre-gate | Topic selection validation | stop |
| Writing | CW | Content writing | stop |
| Copy | G0 | Fact check | stop |
| Copy | G1 | Humanizer | retry |
| Copy | G2 | Copy review | retry |
| Copy | G3 | Brand CTA | stop |
| Copy | G4 | WeChat checklist | stop |
| Copy | G5 | HTML hard check | stop |
| Video | V0 | Lint | stop |
| Video | V1 | Vision QA | stop |
| Video | V2 | Pre-send Whisper | stop |
| Video | V3 | Content semantic | stop |
| Video | V4 | TTS brand asset | stop |
| Video | V5 | MP3 vs SRT | retry |
| Video | V6 | Subtitle render | stop |
| Video | V7 | Six-step hard check | stop |
| Review | H0 | Human review | stop |
| Lifecycle | L1 | Publish log schema | stop |
| Lifecycle | L2 | Archive validation | stop |
| Lifecycle | L3 | Platform integrity | stop |
| Lifecycle | L4 | Translation quality | retry |

### Pipeline Modes

Eight modes select different gate subsets, defined in `automedia/pipelines/runner.py`:

| Mode | Gates | Use Case |
|------|-------|----------|
| `auto` | pre-gate `→` CW `→` G0-G5 `→` V0-V7 `→` H0 `→` L1-L4 | Full production pipeline |
| `text_only` | CW `→` G0-G5 `→` L1-L4 | Draft-only output |
| `text_with_cover` | CW `→` G0-G5 `→` V0 `→` L1-L4 | Text + cover image |
| `video_only` | V0-V7 `→` H0 `→` L1-L4 | Video-only, reuse existing draft |
| `image-carousel` | CW `→` G0-G5 `→` V0 `→` V6 `→` L1-L4 | Carousel-image output |
| `social-thread` | CW `→` G0-G5 `→` L1-L4 | Thread-style posts |
| `short-video` | CW `→` G0-G5 `→` V0-V6 `→` H0 `→` L1-L4 | Short-form video |
| `qa_only` | G0 `→` G2 `→` G3 `→` V1 `→` V6 | Selective QA pass |

## Account & Publishing Layer (PRD-4)

<!-- Condensed from: docs/dev/PRD-4.md (full PRD archived) -->

PRD-4 provides the account infrastructure that enables AI agents to autonomously connect to, manage, and publish content on social media platforms. It sits alongside the existing production (PRD-1), Omni adapter (PRD-2), and decision (PRD-3) layers.

### Architecture

```
PRD-4 Layer
  +---------------------------+   +------------------------------+
  |  Auth Flow Engine          |   |  Account Registry            |
  |  (OAuth2 / Cookie /       |   |  (encrypted credential       |
  |   API Key / QR)            |   |   store, account profiles)   |
  +-------------+-------------+   +------------+-----------------+
                |                             |
                v                             v
  +----------------------------------------------+
  |            Session Manager                     |
  |  (token cache, refresh, expiry detection,     |
  |   health monitoring, stale session alerting)   |
  +----------------------+-----------------------+
                         |
                         v
  +----------------------------------------------+
  |  PRD-1 Adapters (WeChat, Zhihu, etc.)        |
  |  + Future adapters (YouTube, TikTok, etc.)    |
  +----------------------------------------------+
                         |
                         v
  MCP Tools & CLI - connect_account, list_accounts,
  get_account_health, disconnect_account
```

### Key Components

- **AccountRegistry:** CRUD for platform accounts with per-platform profiles, label-based lookup, and encrypted credential persistence (`automedia/accounts/registry.py`).
- **AuthFlowEngine:** Pluggable authentication supporting OAuth2 (authorization_code + client_credentials), cookie-based auth, and API key flows (`automedia/accounts/auth/`).
- **SessionManager:** TTL-aware token cache with automatic refresh, concurrency locks, rate-limit backoff, and health monitoring (`automedia/accounts/session.py`).

### Encryption Model

Account credentials are stored encrypted at rest using AES-256-GCM. Files are organized as `~/.automedia/accounts/{platform}/{account_id}.json.enc` with a master index at `accounts.index.json`. The encryption key is derived from `AUTOMEDIA_MASTER_KEY`, system keyring, or hardware-bound key (future).

### MCP Tools

Four account management tools added to the MCP surface:

- `connect_account(platform, auth_type, credentials, label)` -- register a new platform account
- `list_accounts(platform, status)` -- list registered accounts with health status
- `get_account_health(account_id)` -- check an account's session validity
- `disconnect_account(account_id)` -- remove an account and revoke tokens

### CLI Commands

`automedia account connect|list|health|disconnect` provides full account lifecycle management from the terminal.

## Architecture Decisions

<!-- Source: docs/dev/adr/architecture-decisions.md -->

### ADR-001: Singleton Registry Unification

**Status:** Accepted `·` Effort: Medium (1-2 days)

#### Context

Three singleton registries exist in the codebase with different internal mechanics:

| Registry | File | Singleton Mechanism | Registration Style | API Surface |
|----------|------|-------------------|-------------------|-------------|
| `GateRegistry` | `gates/base.py` | `__new__` with `_instance` class var | `__init_subclass__` auto-registration + manual `register()` | `register()`, `get()`, `list()`, `clear()`, `get_all()`, `__contains__`, `__len__`, `__repr__` |
| `AdapterRegistry` | `adapters/registry.py` | `__new__` with `_instance` class var | Manual `register()` | `register()`, `get()`, `list()`, `clear()` -- all `@classmethod` |
| `OmniToolRegistry` | `omni/registry.py` | `__new__` with `_instance` class var | Manual `register()` | `register()`, `get()`, `list_tools()`, `list()` (deprecated), `clear()` -- all `@classmethod` |

All three share a core pattern (singleton instance, string-keyed dict, CRUD methods) but diverge in whether methods are `@classmethod` vs instance methods, naming conventions, and extras like `get_all()`, `__contains__`, and validation logic.

#### Options Considered

**Option A: Leave as-is (Do nothing).** Zero risk but perpetuates inconsistency.

**Option B: Extract a common `BaseRegistry` mixin class.** DRY, consistent API, one place to fix if the pattern evolves. Requires a minor version bump and updating all three registries in one PR.

**Option C: Standardize `OmniToolRegistry` and `AdapterRegistry` to match `GateRegistry` interface.** Less refactoring than Option B but duplication remains.

#### Recommended Approach

**Option B: Extract a common `BaseRegistry` mixin class.**

Implementation plan:

1. Create `automedia/core/registry.py` with a `BaseRegistry` that implements singleton via `__new__`, provides `register(key, value)`, `get(key)`, `list()`, `clear()`, `__contains__`, `__len__`, `__repr__`, and a `_validate(key, value)` hook for subclasses.
2. Refactor `GateRegistry` to inherit from `BaseRegistry`, override `_validate()` for regex and duplicate checks.
3. Refactor `AdapterRegistry` to inherit from `BaseRegistry`, override `_validate()` to enforce non-empty `platform_name`.
4. Refactor `OmniToolRegistry` to inherit from `BaseRegistry`, keep `list_tools()` as primary and `list()` as deprecated alias.

#### Rationale

The three registries share roughly 70% structural code. Extracting a base eliminates duplication and makes adding a new registry trivial (10 lines instead of 60). A minor version bump signals backward-compatible addition.

#### Watch Out For

- Module-level import order: `BaseRegistry` must be importable without circular deps.
- `GateRegistry.__init_subclass__` auto-registration is unique to gates and should stay in `BaseGate`, not in `BaseRegistry`.
- Test `clear()` isolation must reset instance state, not class state, to avoid cross-module test leakage.

### ADR-002: HITL `↔` Decision Layer Decoupling

**Status:** Implemented `·` Effort: Medium (1-2 days)

> **Note:** This ADR was rendered moot by the D3 cleanup, which removed the entire `automedia/decision/` package. The HITL framework now has no dependency on the decision layer.

#### Context

The `hitl/` and `decision/` packages had a bidirectional import dependency:

| Direction | File | Import | Severity |
|-----------|------|--------|----------|
| `hitl/` `→` `decision/` | `hitl/config.py:11` | `from automedia.decision import dependency` | **Hard** -- module-level, used at import time |
| `hitl/` `→` `decision/` | `hitl/executor.py:29` | `from automedia.decision.base import DecisionArtifact` | **Medium** -- type annotation |
| `decision/` `→` `hitl/` | `decision/orchestrator.py:35` | `from automedia.hitl.executor import NodeExecutor` | **Soft** -- wrapped in try/except |
| `decision/` `→` `hitl/` | `decision/cli/solution.py:344` | `from automedia.hitl.config import HITLConfig` | **Hard** -- direct import |

This meant importing `HITLConfig` immediately pulled in the entire decision graph, and HITL could not be used or tested without the decision package installed.

#### Options Considered

**Option A: Define a `NodeProvider` Protocol in HITL, inject from decision.** Clean dependency inversion; HITL becomes fully standalone; testable with mock providers. Requires minor breaking change to `HITLConfig.__init__` signature.

**Option B: Move preset construction entirely into the decision layer.** Decision owns its node metadata; HITL has zero knowledge of decision. Adds boilerplate bridge module.

**Option C: Soften with deferred import + type stub.** Minimal change but does not truly decouple.

#### Recommended Approach

**Option A: Define a `NodeProvider` Protocol in HITL, inject from decision.**

Implementation plan:

1. Create `automedia/hitl/protocol.py` with a `NodeProvider` protocol class.
2. Refactor `hitl/config.py` to accept an optional `node_provider` parameter and make `_BUILTIN_PRESETS` lazy.
3. Refactor `hitl/executor.py` to use a local `DecisionArtifact` Protocol or guard with `TYPE_CHECKING`.
4. Create `automedia/decision/hitl_provider.py` that wires decision as `NodeProvider`.
5. Refactor `decision/orchestrator.py` to use the provider pattern.

#### Rationale

Standalone HITL framework importable and testable without decision. Clean one-way dependency direction (`decision/` `→` `hitl/`). Backward compatible via optional parameter.

### ADR-003: Rename `platform/` to Avoid stdlib Conflict

**Status:** Accepted `·` Effort: Quick (&lt; 1 hour)

#### Context

The directory `src/automedia/platform/` contains `xiaohongshu.py` and `zhihu_draft.py`. Python 3 has a stdlib module called `platform`. When any file inside `automedia` does `import platform`, the import system may resolve to the local `automedia.platform` package instead of the stdlib, depending on `sys.path` order. No file currently uses `import platform`, but any future or third-party code that does will be silently broken.

Additionally, the two modules are conceptually "platform-specific draft formatting" and belong more naturally under `automedia/adapters/platforms/`.

#### Options Considered

**Option A: Rename to `platform_drafts/`.** Simple, avoids conflict, clear name. Breaks external imports of `automedia.platform`.

**Option B: Merge into `adapters/platforms/`.** Eliminates the namespace entirely and consolidates all platform adapters in one place. Risk of naming collision with existing `XiaohongshuPublisher`.

**Option C: Keep but add `# type: ignore` and absolute imports.** Fragile; everyone must remember the workaround.

#### Recommended Approach

**Option A: Rename to `platform_drafts/`** (with backward-compat shim).

Implementation plan:

1. `git mv src/automedia/platform/ src/automedia/platform_drafts/`
2. Update `platform_drafts/__init__.py` imports.
3. Create `src/automedia/platform/__init__.py` as a backward-compat shim with deprecation warning.
4. Update all existing imports of `automedia.platform` across the codebase.
5. Schedule removal of the shim for v2.0.

#### Rationale

Minimizes risk (rename is fast, localized, no business logic changes). Backward compat via shim `__init__.py`. No merge complexity unlike Option B. Touches only 4 files.

#### Watch Out For

- Use `git mv` to preserve file history.
- Announce deprecation in CHANGELOG under a "Deprecations" section for v1.x, remove shim in v2.0.

### ADR-004: Decompose `mcp/server.py` Monolith

**Status:** Accepted `·` Effort: Medium (1-2 days)

> **Note:** This ADR was partially implemented. The tools extraction (`mcp/tools.py`) was completed, but the full 4-module split (allowlist, tools, resources, server) was not fully carried out.

#### Context

`src/automedia/mcp/server.py` was 1,228 lines with a single public API surface (`create_server()` + tool functions). It contained 5 distinct logical sections:

| Section | Lines | Contents |
|---------|-------|----------|
| Allowlist helpers | 50-145 | `_load_allowlist`, `check_path_allowed`, `_require_allowed` |
| Helper utilities | 148-220 | `_resolve_projects_dir`, `_discover_projects`, `_project_assets` |
| Pipeline tracker | 226-233 | Global `_pipeline_tracker` dict, `_lock`, `_SERVER_START` |
| Tool handlers (14) | 237-941 | All tool functions (each 30-120 lines) |
| Server factory + resources | 971-1189 | `create_server()`, 3 resource functions |
| CLI entry point | 1197-1228 | `main()` |

The file was imported from 50 import sites across 7 test files, so any decomposition had to preserve backward-compatible import paths.

#### Options Considered

**Option A: Split into 4 modules with backward-compat re-exports.** Clean separation, single-responsibility, each module roughly 300-400 lines. Backward compat via re-exports. 50 test import sites need updating (mitigated by re-exports).

**Option B: Extract tools only.** Minimal diff, addresses the largest section, but leaves 600+ lines in `server.py`.

**Option C: Keep monolithic.** Zero risk but the file continues to grow with each new tool.

#### Recommended Approach

**Option A: Split into 4 modules with backward-compat re-exports.**

Implementation plan:

1. Create `mcp/allowlist.py` for allowlist helpers and constants.
2. Create `mcp/tools.py` for all 14 tool handler functions.
3. Create `mcp/resources.py` for helper utilities, pipeline tracker, and resource functions.
4. Update `mcp/server.py` to import from submodules, keep `create_server()` and `main()`, add backward-compat re-exports.
5. Update `mcp/__init__.py` imports to point to `mcp/tools.py` for individual tools.

#### Rationale

Backward compat guaranteed via re-exports (zero changes to 50 test import sites). Clear single-responsibility modules. Incremental adoption possible file-by-file.

#### Watch Out For

- `_pipeline_tracker` accessed by multiple tools -- use a shared `_state` module.
- `_ALLOWED_OUTPUT_FORMATS` used by `format_output` -- ensure accessible from `tools.py`.
- Test path imports continue to work through re-exports.
- `create_server()` will still be roughly 200 lines after extraction but that is acceptable for declarative boilerplate.
