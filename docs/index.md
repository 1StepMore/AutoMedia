---
title: Home
description: AutoMedia — automated media production pipeline for content teams and AI coding agents.
---

# Welcome to AutoMedia

Automated Media Production Pipeline — for content teams and AI coding agents.

---

## What is AutoMedia?

AutoMedia automates content production from **topic selection** through **draft writing**, **video generation**, **subtitle rendering**, and **multi-platform publishing**. It handles the repetitive parts of media production so you can focus on creative decisions.

**Stats:** 33,619 LOC (core) · ~90,000+ LOC (total) · 442+ Python files · Python 3.11+ · MIT License

---

## Features

- **Three-layer API** — Python SDK / CLI (13 commands) / MCP Server (41 tools)
- **21 quality gates** — G0-G5 (copy), V0-V7 (video/quality), H0 (human review), L1-L4 (lifecycle)
- **6-layer configuration** — defaults → project → user → overrides → prompts → env vars
- **Topic pool** — SQLite-backed with scoring, dedup, scheduling
- **Platform adapters** — Extensible publish targets
- **Omni Triad** — OPP (extraction), OL (localization), ORF (format conversion)
- **Human-in-the-loop** — Review gates for content and video quality approval
- **MCP-native** — Works with Claude Desktop/Code, OpenCode, Codex CLI, Cline, OpenClaw

---

## Quick Start

```bash
# Install
pip install -e .

# Initialize configuration
automedia init

# Check dependencies
automedia doctor

# Run full pipeline
automedia run --topic "Your Topic Here" --brand my-brand

# Text-only mode (skip video generation)
automedia run --topic "..." --brand my-brand --mode text_only
```

---

## Documentation

| Section | Description |
|---------|-------------|
| [Developer Guide](dev/developer-guide.md) | Full setup and development guide |
| [API Reference](user/api-reference.md) | Python SDK API documentation |
| [CLI Reference](user/cli-reference.md) | Command-line interface reference |
| [MCP Setup](user/mcp-setup.md) | MCP server setup for AI agents |
| [HITL Framework](user/hitl-framework.md) | Human-in-the-loop review gates |
| [Omni Triad Integration](user/omni-integration.md) | OPP, OL, ORF adapter docs |
| [Asset Library](user/asset-library.md) | Persistent searchable asset storage |

---

## Runbook

Troubleshooting and operational guides:

| Guide | Description |
|-------|-------------|
| [Gate Failure Modes](dev/gate-failure-modes.md) | Diagnosing and fixing gate failures |
| [Production Workflow](user/production-workflow.md) | Daily production operations |
| [Cron Troubleshooting](dev/cron-troubleshooting.md) | Debugging scheduled jobs |
| [API Gotchas](dev/api-gotchas.md) | Common API pitfalls and solutions |

---

## For AI Agents

AutoMedia is MCP-native. Connect any MCP client to get started:

```bash
python -m automedia.mcp.server
```

See [MCP Setup](mcp-setup.md) for client configuration examples (Claude Desktop, OpenCode, Codex CLI, Hermes Agent).

---

## License

MIT License. See [LICENSE](https://github.com/1stepmore/automedia/blob/main/LICENSE) for details.
