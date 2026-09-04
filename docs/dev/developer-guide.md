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
   │   select_topic, run_pipeline, ...    │  66 tools
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
| `gates/` | 33 Gate implementations including H0 + failure mode knowledge base (`failure_modes.py`) |
| `detectors/` | Pluggable AI-writing-taste detector framework (`base.py` BaseDetector ABC, `registry.py` DetectorRegistry, `deterministic.py` built-in detector reusing G1's 9 regex checks, `adapters.py` env-gated external detectors) |
| `adapters/` | Platform publish adapter registry (`registry.py`) + base class (`base.py`) |
| `hooks/` | GateHook Protocol (`protocol.py`), MD5 tracking (`md5_tracker.py`) |
| `manifests/` | Built-in YAML default config (`defaults.yaml`), schema definitions |
| `pool/` | Topic pool SQLite database (`db.py`), collection/scoring/dedup |
| `cron/` | Scheduled job YAML definitions (`jobs.yaml`), pipeline schedule runner (`runner.py`) |
| `mcp/` | MCP Server implementation (`server.py`), stdio transport |
| `prompts/` | Built-in Jinja2 prompt templates (11 templates) with platform-scoped resolution (30 platform overrides for 10 platforms) |

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
  detectors/                # AI-writing-taste detectors (issue #62)
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
| G0-G6 | Copy Gates | Fact check, humanizer, copy review, brand CTA, WeChat checks, HTML lint, tone check |
| V0-V7 | Video Gates | Lint, Vision QA, Whisper, subtitle rendering, content semantic, TTS brand asset, MP3×SRT, six-step hard |
| H0 | Human Review Gate | Human-in-the-loop content and video approval |
| L1-L4 | Lifecycle Gates | Publish log, archive validation, platform integrity, translation quality |
| D1-D7 | Distribution Gates | Standalone platform-specific rewrite gates (WeChat, Twitter/X, Zhihu, Xiaohongshu, Bilibili, YouTube, TikTok) |
| P1-P4 | Repurpose Gates | Sub-pipeline deep repurpose gates (WeChat, Twitter/X, Newsletter, Bilibili) |

### Pipeline Modes

The pipeline supports nine modes, each running a different subset of gates. The mode is selected via the `--mode` CLI flag, the `mode` parameter in the SDK, or the `mode` field in the MCP `run_pipeline` tool.

| Mode | Gates Executed | Use Case |
|------|---------------|----------|
| `auto` | pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4 | Full production pipeline: topic validation, content writing, all copy and video gates, lifecycle checks |
| `text_only` | CW → G0-G6 → H0 → L1-L4 | Draft-only output: content writing and copy gates, no video/rendering gates |
| `text_with_cover` | CW → G0-G6 → H0 → L1-L4 | Text output plus a single cover image |
| `video_only` | V0-V7 → H0 → L1-L4 | Video-only: reuse an existing draft, run all video and lifecycle gates |
| `image-carousel` | CW → G0-G6 → L1-L4 | Carousel-image output for social platforms |
| `social-thread` | CW → G0-G6 → L1-L4 | Thread-style posts for social platforms |
| `short-video` | pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4 | Short-form video (e.g. TikTok/Reels) |
| `qa_only` | G0 → G2 → G3 → V1 → V6 | Selective QA pass on existing content: targeted copy and video checks |
| `repurpose` | CW → G0-G6 → V0-V7 → H0 → L1-L4 → P1-P4 | Full pipeline followed by platform-specific deep repurpose gates |

Gate lists are defined in `src/automedia/pipelines/runner.py` as `_AUTO_GATE_NAMES`, `_TEXT_ONLY_GATE_NAMES`, `_VIDEO_ONLY_GATE_NAMES`, `_QA_ONLY_GATE_NAMES`, and `_REPURPOSE_GATE_NAMES`.

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
| RL6 | Follow gate naming convention: G0-G6, V0-V7, L1-L4, D1-D7, P1-P4, H0, CW, pre-gate | Developer discipline |
| RL7 | Must add new gates to `failure_modes.py` | Developer discipline |
| RL8 | Must run pre-commit checks before committing | Pre-commit hooks (automated) |
| RL9 | Respect GateHook readonly contract -- observe but do not modify | Developer discipline |

> Note: RL numbering matches AGENTS.md section 5. Original RL9 (decision provenance) has been removed.

### Gate List

33 gates across six phases plus standalone distribution gates and repurpose sub-pipelines. Gate order: pre-gate `→` CW `→` G0-G6 `→` V0-V7 `→` H0 `→` L1-L4. D-gates (D1-D7) are standalone and invoked via CLI/MCP — not part of the standard pipeline. P-gates (P1-P4) run as sub-pipelines at the end of `repurpose` mode.

| Phase | Gate | Name | Failure Mode |
|-------|------|------|-------------|
| Pre | pre-gate | Topic selection validation | stop |
| Writing | CW | Content writing (with inline SEO scoring) | stop |
| Copy | G0 | Fact check | stop |
| Copy | G1 | Humanizer | retry |
| Copy | G2 | Copy review | retry |
| Copy | G3 | Brand CTA | stop |
| Copy | G4 | WeChat checklist | stop |
| Copy | G5 | HTML hard check | stop |
| Copy | G6 | Tone check | stop |
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

### Distribution Gates (D1-D7)

Standalone rewrite gates invoked via `automedia distribute` CLI or `distribute_content` MCP tool. NOT part of the standard pipeline — run on-demand against already-published content.

| Gate | Platform | Purpose |
|------|----------|---------|
| D1 | WeChat | Rewrite content for WeChat Official Account format |
| D2 | Twitter/X | Rewrite content for Twitter/X short-form format |
| D3 | Zhihu | Rewrite content for Zhihu long-form article format |
| D4 | Xiaohongshu | Rewrite content for Xiaohongshu visual-first format |
| D5 | Bilibili | Rewrite content for Bilibili video+text format |
| D6 | YouTube | Rewrite content for YouTube video description format |
| D7 | TikTok | Rewrite content for TikTok short-video script format |

### Repurpose Gates (P1-P4)

Sub-pipeline gates that run at the end of `repurpose` mode, performing deep content repurposing for specific platforms.

| Gate | Platform | Purpose |
|------|----------|---------|
| P1 | WeChat | Deep repurpose for WeChat Official Account |
| P2 | Twitter/X | Deep repurpose for Twitter/X thread format |
| P3 | Newsletter | Deep repurpose for email newsletter format |
| P4 | Bilibili | Deep repurpose for Bilibili video+article format |

### Pipeline Modes

Nine modes select different gate subsets, defined in `automedia/pipelines/runner.py`:

| Mode | Gates | Use Case |
|------|-------|----------|
| `auto` | pre-gate `→` CW `→` G0-G6 `→` V0-V7 `→` H0 `→` L1-L4 | Full production pipeline |
| `text_only` | CW `→` G0-G6 `→` H0 `→` L1-L4 | Draft-only output |
| `text_with_cover` | CW `→` G0-G6 `→` H0 `→` L1-L4 | Text + cover image |
| `video_only` | V0-V7 `→` H0 `→` L1-L4 | Video-only, reuse existing draft |
| `image-carousel` | CW `→` G0-G6 `→` L1-L4 | Carousel-image output |
| `social-thread` | CW `→` G0-G6 `→` L1-L4 | Thread-style posts |
| `short-video` | pre-gate `→` CW `→` G0-G6 `→` V0-V7 `→` H0 `→` L1-L4 | Short-form video |
| `qa_only` | G0 `→` G2 `→` G3 `→` V1 `→` V6 | Selective QA pass |
| `repurpose` | CW `→` G0-G6 `→` V0-V7 `→` H0 `→` L1-L4 `→` P1-P4 | Full pipeline + deep repurpose for platform distribution |

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

<!-- Source: docs/adr/ -->

| ADR | File | Title |
|-----|------|-------|
| ADR-001 | docs/adr/ADR-001-singleton-registry-unification.md | Singleton Registry Unification |
| ADR-002 | docs/adr/ADR-002-hitl-decision-layer-decoupling.md | HITL ↔ Decision Layer Decoupling |
| ADR-003 | docs/adr/ADR-003-platform-rename-stdlib-conflict.md | Rename `platform/` to Avoid stdlib Conflict |
| ADR-004 | docs/adr/ADR-004-mcp-server-decomposition.md | Decompose `mcp/server.py` Monolith |
| ADR-005 | docs/adr/ADR-005-issue-driven-commits.md | Issue-Driven Atomic Commit Discipline |
| ADR-006 | docs/adr/ADR-006-graph-engineering-dag.md | Explicit Per-Mode Gate DAG: additive order-equivalent graph over `_MODE_MAP` (26 nodes), with opt-in `--auto-resume`, failure localization, and a read-only state view |
