# AutoMedia

Automated Media Production Pipeline — for content teams and AI coding agents.

[![CI](https://img.shields.io/github/actions/workflow/status/1stepmore/automedia/ci.yml?branch=main&label=CI)](https://github.com/1stepmore/automedia/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](https://github.com/1stepmore/automedia/blob/main/LICENSE)
[![Agent Ready](https://img.shields.io/badge/agent-ready-purple)](https://github.com/1stepmore/automedia/blob/main/AGENTS.md)

This README serves **both human developers and AI coding agents** (OpenCode, Claude Code, Codex CLI, OpenClaw, Hermes Agent) as the primary entry point. For detailed agent-role context, constraints, and codebase map, read [AGENTS.md](https://github.com/1stepmore/automedia/blob/main/AGENTS.md).

## Quick Overview

AutoMedia automates content production from topic selection through draft writing, video generation, subtitle rendering, and multi-platform publishing. It handles the repetitive parts of media production so you can focus on creative decisions.

23,118 LOC (core) · 86,905 LOC (total) · 442 Python files · Python 3.11+ · 2,047 tests (0 failing) · MIT License

### For AI Agents

If you are an AI coding agent entering this codebase:

1. **Read [AGENTS.md](https://github.com/1stepmore/automedia/blob/main/AGENTS.md)** — agent-role context, constraints, directory layout, MCP/CLI references, red lines
2. **Connect MCP** — Start the MCP server (`python -m automedia.mcp.server`) or configure your tool's MCP client (see [Three-Layer API](#three-layer-api))
3. **Explore config files** — `opencode.json`, `.claude/`, `.env.example` for tool-specific setup
4. **Find tests** — `tests/` directory, run with `make test` or `pytest`

## Features

- **Three-layer API**: SDK / CLI (12 commands) / MCP Server (22 tools)
- **20 quality gates**: G0-G5 (copy), V0-V7 (video/quality), L1-L4 (lifecycle), plus pre-gate and CW
- **6-layer configuration hierarchy**: defaults → project → user → overrides → env vars
- **Topic pool**: SQLite-backed with scoring, dedup, scheduling
- **Platform adapter system**: Extensible publish targets
- **Account & credential management**: AES-256-GCM encrypted store, OAuth2/Cookie/API Key auth flows, session management
- **Omni Triad**: OPP (extraction), OL (localization), ORF (format conversion)
- **Human-in-the-loop**: Review gates for content and video quality approval
- **MCP-native**: Works with Claude Desktop/Code, OpenCode, Codex CLI, Cline, OpenClaw, Hermes Agent

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Agent Quickstart](#agent-quickstart)
- [Three-Layer API](#three-layer-api)
- [Agent Configuration](#agent-configuration)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Gate System](#gate-system)
- [Security](#security)
- [Development](#development)
- [Testing](#testing)
- [Project Status](#project-status)
- [License](#license)
- [Documentation Index](#documentation-index)

## Installation

### Quick start with Docker

Start using AutoMedia without any local dependencies:

```bash
docker pull kevinzhow/automedia-pipeline:latest
docker run -it --rm kevinzhow/automedia-pipeline:latest automedia doctor
```

A devcontainer configuration is also available at `.devcontainer/devcontainer.json` for VS Code Remote.

### Manual installation

> **License notice:** Optional extras `[omni-pdf]` and `[omni]` install PyMuPDF,
> which is licensed under AGPL v3. Ensure compliance with the AGPL before using
> these extras in your project.

**Prerequisites:**

- Python 3.11+
- FFmpeg
- Bun
- edge-tts CLI
- Whisper (faster-whisper or openai-whisper)
- Chrome/Chromium (headless mode for video rendering)
- ComfyUI (optional, for custom video generation)

> **Tip:** All external dependencies come pre-installed in the [Docker image](#quick-start-with-docker). Use that to skip local setup.

#### Python 3.11+

AutoMedia requires Python 3.11 or newer.

| Platform | Install |
|----------|---------|
| Ubuntu | `sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv python3-pip` |
| macOS | `brew install python@3.11` |
| Windows | `winget install Python.Python.3.11` or download from [python.org](https://www.python.org/downloads/) |

Verify: `python3 --version` (or `python --version` on Windows)

#### FFmpeg

Audio/video encoding, decoding, format conversion, and frame extraction.

| Platform | Install |
|----------|---------|
| Ubuntu | `sudo apt-get update && sudo apt-get install -y ffmpeg` |
| macOS | `brew install ffmpeg` |
| Windows | `winget install "FFmpeg (Essentials Build)"` or download from [ffmpeg.org](https://ffmpeg.org/download.html) |

Verify: `ffmpeg -version`

#### Bun

JavaScript runtime for HyperFrames subtitle rendering and video assembly.

| Platform | Install |
|----------|---------|
| Ubuntu / macOS | `curl -fsSL https://bun.sh/install \| bash` |
| Windows | `powershell -c "irm https://bun.sh/install.ps1 \| iex"` |
| Any (via npm) | `npm install -g bun` |

Verify: `bun --version`

#### edge-tts CLI

Python-based text-to-speech engine using Microsoft Edge TTS service.

```bash
pip install edge-tts
```

Verify: `edge-tts --help`

#### Whisper

Speech-to-text engine for subtitle generation. Choose one:

```bash
# Recommended: faster-whisper (faster, lower memory)
pip install faster-whisper

# Alternative: openai-whisper
pip install openai-whisper
```

Verify:

```bash
# faster-whisper
python -c "import faster_whisper; print(faster_whisper.__version__)"

# openai-whisper
python -c "import whisper; print(whisper.__version__)"
```

#### Chrome/Chromium

Used headless for video rendering and screenshot capture.

| Platform | Install |
|----------|---------|
| Ubuntu | `sudo apt-get update && sudo apt-get install -y chromium-browser` |
| macOS | `brew install --cask google-chrome` |
| Windows | `winget install Google.Chrome` |

Verify: `google-chrome --version` (or `chromium-browser --version` on Ubuntu)

#### ComfyUI (optional)

Custom video generation with AI models. Required only for pipelines that use AI-generated visuals.

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt
```

See the [ComfyUI repository](https://github.com/comfyanonymous/ComfyUI) for full setup.

Verify: Start the server (`python main.py`) and check `http://localhost:8188` is reachable.

> **Docker alternative:** All external dependencies are pre-installed in the Docker image. See [Quick start with Docker](#quick-start-with-docker).

```bash
pip install -e .

# With extras
pip install -e ".[dev]"       # development (LLM providers, mcp, rich, test)
pip install -e ".[mcp]"       # MCP server only
pip install -e ".[openai]"    # OpenAI provider
pip install -e ".[anthropic]" # Anthropic provider
```

### Development installation

```bash
git clone <repo-url> && cd AutoMedia

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

Or use the setup script:

```bash
bash scripts/setup.sh
```

## Quick Start

```bash
# Initialize configuration
automedia init

# Check dependencies
automedia doctor

# Run full pipeline (auto mode)
automedia run --topic "Your Topic Here" --brand my-brand

# Text-only mode (skip video generation)
automedia run --topic "..." --brand my-brand --mode text_only
```

## Agent Quickstart

New to this codebase? Here's your orientation path:

```
Step 1: Read AGENTS.md       → Codebase map, constraints, red lines (10 MUST/MUST NOT)
Step 2: Review agent config  → opencode.json (OpenCode), .claude/ (Claude Code)
Step 3: Start MCP server     → python -m automedia.mcp.server
Step 4: Verify setup         → automedia doctor
Step 5: Try a pipeline       → automedia run --topic "..." --brand my-brand --mode text_only
```

**Files every agent should read:**

| File | Purpose | Read by |
|------|---------|---------|
| `AGENTS.md` | Universal agent context (constraints, layout, MCP/CLI refs, red lines) | OpenCode, Claude Code, Codex CLI, Hermes Agent |
| `opencode.json` | OpenCode MCP server binding + agent instructions | OpenCode |
| `.claude/settings.json` | Claude Code MCP server config | Claude Code |
| `.claude/rules.md` | Claude Code project rules | Claude Code |
| `.env.example` | Environment variable reference | All tools |

## Three-Layer API

AutoMedia exposes three interfaces to the same `run_full_pipeline()` implementation.

### Python SDK

```python
from automedia import run_full_pipeline

result = run_full_pipeline(
    topic="AI video tools comparison",
    brand="my-brand",
    mode="auto",
)
```

### CLI (12 commands)

| Command | Description |
|---------|-------------|
| `automedia run` | Execute production pipeline |
| `automedia pool` | Topic pool management (list, add, score) |
| `automedia projects` | List and manage production projects |
| `automedia adapter` | Platform adapter management |
| `automedia cron` | Execute scheduled cron jobs |
| `automedia account` | Platform account management (connect, list, health, disconnect, refresh) |
| `automedia archive` | Archive a project (Red Line 8: requires `--force` unless published) |
| `automedia init` | Initialize AutoMedia configuration |
| `automedia doctor` | Check system dependencies and environment health |
| `automedia omni` | Omni Triad operations (extract, translate, convert) |
| `automedia hitl` | Human-in-the-loop review operations |
| `automedia onboard` | Onboarding wizard |

### MCP Server (22 tools)

Start:

```bash
python -m automedia.mcp.server
```

| Tool | Description |
|------|-------------|
| `health_check` | Return server health status (version, uptime, tool count) |
| `select_topic` | Select highest-scored pending topic from pool |
| `research_topics` | Research trending topics within a category using LLM |
| `run_brand_strategy` | Generate a brand strategy using LLM analysis |
| `run_pipeline` | Execute full production pipeline (background, async) |
| `run_pipeline_from_strategy` | Generate content strategy via LLM then execute pipeline |
| `get_pipeline_progress` | Poll a running pipeline's gate-by-gate progress |
| `get_pipeline_status` | Query project status from its info file |
| `list_projects` | List all projects under a base directory |
| `get_project_assets` | List asset files in a project directory |
| `archive_project` | Archive a project (enforces Red Line 8) |
| `list_topic_pool` | List topics in the pool with optional filters |
| `register_platform_adapter` | Register a publish adapter stub |
| `extract_brief` | Extract content brief from document (OPP) |
| `localize_content` | Translate markdown content (OL shield pipeline) |
| `localize_output` | Translate all project drafts into multiple languages |
| `format_output` | Convert content format (ORF adapter) |
| `evaluate_content_quality` | Score content quality against criteria (clarity, accuracy, brand voice, etc.) |
| `connect_account` | Register a new platform account for publishing |
| `list_accounts` | List all registered accounts with optional filters |
| `get_account_health` | Check an account's health status |
| `disconnect_account` | Disconnect/remove a platform account |

### MCP Client Configuration Examples

**Claude Desktop / Claude Code:**

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"],
      "env": {"AUTOMEDIA_LLM_API_KEY": "sk-xxx"}
    }
  }
}
```

**OpenCode** (in `opencode.json`):

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"]
    }
  }
}
```

**Codex CLI** (in `.codex/config.json` or global config):

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"],
      "env": {"AUTOMEDIA_LLM_API_KEY": "sk-xxx"}
    }
  }
}
```

**OpenClaw** — supports MCP via its plugin system; configure in `~/.openclaw/` or use the Gateway dashboard.

**Hermes Agent** (in `~/.hermes/config.yaml`):

```yaml
mcp_servers:
  automedia:
    command: python
    args: ["-m", "automedia.mcp.server"]
    env:
      AUTOMEDIA_LLM_API_KEY: "sk-xxx"
```

Hermes also reads `AGENTS.md` from the project root as its primary project context — no additional config needed for project awareness.

## Agent Configuration

The project ships agent-specific config files at the repository root:

| File | Tool | What it does |
|------|------|-------------|
| `opencode.json` | OpenCode | MCP server binding + agent instructions for Build/Plan modes |
| `.claude/settings.json` | Claude Code | MCP server configuration |
| `.claude/rules.md` | Claude Code | Project-level rules, constraints, and conventions |
| `AGENTS.md` | Universal | Codebase map, 10 agent constraints, MCP/CLI references, red lines |
| `.env.example` | Universal | All supported environment variables with documentation |

All tools also read `AGENTS.md` for project context — it's the single source of truth for agent-role information. Hermes Agent additionally supports `.hermes.md` (highest priority), but since this project targets multiple agent types, `AGENTS.md` is the canonical choice (per Hermes docs: *"Use AGENTS.md when the same project will also be worked on by other agents"*).

## Architecture

```
  +------------------------------------------+
  |  Any MCP Client / SDK / CLI Terminal      |
  +-----------+-------------------+-----------+
              |                   |
  +-----------+----+     +--------+-----------+
  |  MCP Server    |     |  CLI (typer)       |
  |  22 tools      |     |  12 commands       |
  +-----------+----+     +--------+-----------+
              |                   |
  +-----------+-------------------+------------+
  |      automedia/ Python Package             |
  |  core/ pipelines/ gates/ adapters/         |
  |  accounts/ hooks/ manifests/ pool/ cron/   |
  |  mcp/ cli/ hitl/ omni/                     |
  +--------------------------------------------+
```

### Core Subpackages

| Package | Responsibility |
|---------|---------------|
| `core/` | Config loading (6-layer), project management, credential loading, health checks |
| `pipelines/` | Pipeline orchestration, GateEngine, audio/video pipelines |
| `gates/` | 20 gate implementations + failure mode knowledge base |
| `hooks/` | GateHook observer protocol (readonly), MD5 tracking, metrics |
| `adapters/` | Platform publish adapter registry + base classes |
| `accounts/` | Encrypted credential store, account registry, auth flow engine, session manager |
| `manifests/` | Built-in YAML defaults, brand profile schema, model config schema |
| `pool/` | Topic pool SQLite DB, collector, scorer, dedup |
| `cron/` | Scheduled job definitions (triggered by external crond) |
| `mcp/` | MCP server implementation (stdio transport, path allowlist) |
| `cli/` | Typer CLI application (12 command modules) |
| `hitl/` | Human-in-the-loop framework |
| `omni/` | Omni Triad adapters (OPP extraction, OL localization, ORF conversion) |
| `asset_library/` | Vector store, document ingest, similarity search |

## Configuration

Six-layer priority hierarchy (lowest to highest):

1. **Built-in defaults**: `automedia/manifests/defaults.yaml`
2. **Project config**: `.automedia/` directory
3. **User config**: `~/.automedia/` directory
4. **Override rules**: `~/.automedia/overrides/rules/*.yaml`
5. **Override prompts**: `~/.automedia/overrides/prompts/*.j2`
6. **Environment variables**: `AUTOMEDIA_*` + explicit CLI/MCP overrides

Each layer merges with the one below it. See `.env.example` for all supported environment variables.

## Gate System

Gates are quality checks that run at specific points in the pipeline. Each gate has a failure mode (`"stop"` halts the pipeline, `"retry"` triggers content regeneration).

| Range | Count | Purpose |
|-------|-------|---------|
| Pre-gate | 1 | Topic selection validation |
| CW | 1 | Content writing |
| G0-G5 | 6 | Copy gates: fact check, humanizer, copy review, brand CTA, WeChat checks, HTML lint |
| V0-V7 | 8 | Video gates: lint, vision QA, Whisper, content semantic, TTS brand asset, MP3×SRT, subtitle render, six-step hard check |
| L1-L4 | 4 | Lifecycle gates: publish log schema, archive validation, platform integrity, translation quality |

**Total: 20 gates.** Gate order: D0 → pre-gate → CW → G0-G5 → V0-V7 → L1-L4.

## Security

- **Red Line 8**: `archive_project` / `automedia archive` refuses unless status is `"published"` or `force=True`. Agents MUST NOT circumvent.
- **Path allowlist**: MCP server (`mcp_allowlist.yaml`) restricts file access to configured directories. Empty list = deny all paths. Do not modify without explicit user request.
- **Encrypted credential store**: Platform credentials encrypted at rest with AES-256-GCM; master key derived from `AUTOMEDIA_MASTER_KEY` via SHA-256. Credentials never appear in logs or MCP responses.
- **Credential isolation**: Credentials loaded from encrypted store, env vars, or system keyring, never persisted to config files.
- **No production data in tests**: Use synthetic fixtures from `tests/fixtures/synth/` only.
- **Git secrets**: `.env`, `credentials.yaml`, `*.pem`, `*.key`, `*.token` all gitignored.

## Development

### Prerequisites (dev)

```bash
pip install -e ".[dev]"
pre-commit install
```

### Makefile Targets

```bash
make install        # Install base package
make install-dev    # Install with dev dependencies
make test           # Run full test suite
make test-coverage  # Run with coverage report
make lint           # Run ruff
make typecheck      # Run mypy
make pre-commit     # Run pre-commit on all files
make doctor         # Check system dependencies
make clean          # Clean build artifacts
```

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/setup.sh` | One-command venv + install + init + doctor |
| `scripts/run-tests.sh` | pytest with coverage |
| `scripts/mcp-server.sh` | MCP launcher with SIGTERM handler |
| `scripts/doctor.sh` | Dependency checker (python, ffmpeg, bun, whisper, edge-tts, chrome, comfyui) |

## Testing

```bash
# Full test suite
pytest

# With coverage
pytest --cov=src/automedia

# By marker
pytest -m e2e        # End-to-end tests
pytest -m redline    # Red line enforcement tests
pytest -m slow       # Slow tests (video/audio processing)

# Specific test directory
pytest tests/test_gates/ -v
pytest tests/test_cli/ -v
pytest tests/test_mcp/ -v
```

## Project Status

Active development. 2,047 tests passing, 0 failing. 86,905 LOC across 442 Python files (23,118 LOC in automedia/ core).

## License

MIT License. See `LICENSE` for details.

## Documentation Index

| Document | Language | Audience |
|----------|----------|----------|
| `AGENTS.md` | English | AI coding agents — codebase map, constraints, MCP/CLI refs |
| `README.md` (this file) | English | Human developers + AI agents — entry point, install, quick start |
| `docs/dev/developer-guide.md` | English | Full developer guide |
| `docs/user/api-reference.md` | English | SDK API reference |
| `docs/user/cli-reference.md` | English | CLI command reference |
| `docs/user/mcp-setup.md` | English | MCP server setup guide |
| `docs/user/omni-integration.md` | English | Omni Triad integration |
| `docs/user/hitl-framework.md` | English | HITL framework |
| `docs/user/asset-library.md` | English | Asset library |
| `docs/runbook/gate-failure-modes.md` | English | Gate failure troubleshooting |
| `docs/runbook/production-workflow.md` | English | Production operations |
| `docs/runbook/cron-troubleshooting.md` | English | Cron job debugging |
| `docs/runbook/api-gotchas.md` | English | Common API pitfalls |
| `CHANGELOG.md` | English | Version history and release notes |
