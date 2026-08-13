---
title: Agent Quickstart
description: 6-step onboarding guide for AI coding agents entering the AutoMedia codebase — read AGENTS.md, install, connect MCP, verify setup, run a pipeline, next steps.
---

# Agent Quickstart

If you are an AI coding agent (OpenCode, Claude Code, Codex CLI, Cline, Hermes
Agent, or any MCP-compatible tool) and this is your first time in the AutoMedia
codebase, follow these six steps. They will get you from zero to running your
first production pipeline in a few minutes.

This guide assumes you have access to the repository and a basic Python
environment. Each step points to deeper reference docs for the details.

---

## Step 1: Read AGENTS.md

Start with **AGENTS.md** in the project root. It is the single source of truth
for agent-role context. Every agent reads it first, regardless of the tool you
use.

**What you will find in AGENTS.md:**

- Project overview (language, size, key dependencies, license)
- Directory layout (every directory and subpackage explained)
- Three entry points: MCP server, CLI, and Python SDK
- 10 agent constraints (MUST/MUST NOT red lines)
- Gate system overview (21 quality gates in pipeline order)
- MCP tools quick reference (50 tools with parameters)
- CLI commands quick reference (14 commands)
- Config key reference (AUTO MEDIA_* environment variables)
- Test conventions and common task patterns

> **Tip:** AGENTS.md is updated when the codebase changes. Re-read it if you
> are returning after a gap and things behave unexpectedly.

---

## Step 2: Install AutoMedia

You need the package installed to use the CLI, the MCP server, or the SDK.

### Recommended install (full capability)

```bash
pip install -e ".[dev]"
```

This gives you all LLM providers, the MCP server, rich output, and test tools.

### MCP-only install

```bash
pip install -e ".[mcp]"
```

### Docker (no local dependencies)

```bash
docker pull kevinzhow/automedia-pipeline:latest
docker run -it --rm kevinzhow/automedia-pipeline:latest automedia doctor
```

The Docker image comes with all external dependencies (FFmpeg, Bun, Whisper,
edge-tts, Chrome) pre-installed.

See the [Installation section in AGENTS.md](AGENTS.md) and
[README.md](README.md#installation) for platform-specific instructions.

---

## Step 3: Connect MCP

The MCP server gives AI agents access to 50 tools for pipeline execution, topic
management, publishing, localization, and more. Start the server in one terminal:

```bash
python -m automedia.mcp.server
```

Then configure your client to connect. Here are examples for the most common
tools.

### OpenCode

Edit `.opencode/package.json` or `~/.config/opencode/mcp.json`:

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

### Claude Code / Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"],
      "env": {
        "AUTOMEDIA_LLM_API_KEY": "sk-xxx"
      }
    }
  }
}
```

### Codex CLI

In `.codex/config.json` or global config:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"],
      "env": {
        "AUTOMEDIA_LLM_API_KEY": "sk-xxx"
      }
    }
  }
}
```

### Cline

Edit the VSCode extension config or `~/.config/cline/mcp.json`:

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

For all clients, set `AUTOMEDIA_LLM_API_KEY` to your LLM provider key either in
the config or as an environment variable. See
[docs/user/mcp-setup.md](docs/user/mcp-setup.md) for the full reference.

---

## Step 4: Verify Setup

Run the doctor command to check that all dependencies and configuration are
correct:

```bash
automedia doctor
```

If everything is green, you are ready to go. The doctor checks:

- Python version (3.11+)
- FFmpeg availability
- Bun runtime
- Whisper installation
- edge-tts CLI
- Chrome/Chromium (headless)
- ComfyUI (optional)
- Configuration health
- LLM provider connectivity

You can also verify the MCP server is working:

```bash
python -m automedia.mcp.server --show-tools
```

This lists all 50 registered tools without starting the server.

---

## Step 5: Run First Pipeline

Once the setup checks pass, run a pipeline in text-only mode (no video
generation) to test the full flow:

```bash
automedia run --topic "AI video tools comparison" --brand my-brand --mode text_only
```

This runs the pipeline through these gates:

1. Pre-gate (topic selection validation)
2. CW (content writing)
3. G0-G5 (fact check, humanizer, copy review, brand CTA, WeChat checklist, HTML lint)
4. L1-L4 (lifecycle gates: publish log schema, archive validation, platform integrity)

The pipeline creates a project directory under your configured output directory
with the generated content files.

For more options:

- **Auto mode (full video):** `automedia run --topic "..." --brand my-brand --mode auto`
- **Batch topics:** `automedia run --topic "topic1" --brand my-brand && automedia run --topic "topic2" --brand my-brand`
- **Via MCP:** Use the `run_pipeline` tool from your agent client

---

## Step 6: Next Steps

Now that you have a working pipeline, explore the deeper documentation:

| Resource | What it covers |
|----------|---------------|
| [AGENTS.md](AGENTS.md) | Codebase map, constraints, red lines (re-read as needed) |
| [docs/user/api-reference.md](docs/user/api-reference.md) | Full Python SDK reference (`run_full_pipeline`, `GateEngine`, `PipelineResult`) |
| [docs/user/cli-reference.md](docs/user/cli-reference.md) | All 14 CLI commands with examples |
| [docs/user/mcp-setup.md](docs/user/mcp-setup.md) | MCP server configuration, path allowlist, environment variables |
| [docs/user/production-workflow.md](docs/user/production-workflow.md) | Daily production SOPs, scheduling, publishing flow |
| [docs/user/hitl-framework.md](docs/user/hitl-framework.md) | Human-in-the-loop review and approval workflow |
| [docs/user/omni-integration.md](docs/user/omni-integration.md) | Omni Triad (extract, localize, convert) |
| [docs/dev/gate-failure-modes.md](docs/dev/gate-failure-modes.md) | Gate failure troubleshooting |
| [docs/dev/developer-guide.md](docs/dev/developer-guide.md) | Full developer guide for contributing |
