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
| `prompts/` | Built-in Jinja2 prompt templates (11 templates) with platform-scoped resolution (18 platform overrides for 6 platforms) |

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
