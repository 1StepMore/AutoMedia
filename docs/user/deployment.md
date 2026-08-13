---
title: Deployment Options
description: Compare deployment methods for AutoMedia: Docker, native, systemd, and Windows.
---

# Deployment Options

AutoMedia supports four deployment methods. This document helps you choose
the right one and points to detailed setup instructions for each.

## Quick Comparison

| Option | Setup Time | Maintenance | Features | Recommended For |
|--------|-----------|-------------|----------|-----------------|
| Docker | 5-10 min | Low (single `docker pull`) | Full pipeline with all external deps pre-installed (FFmpeg, Bun, edge-tts, faster-whisper, Chromium). Docker Compose profiles for lightweight vs full. | Quick start, CI/CD pipelines, isolated environments, reproducible builds |
| Native (pip) | 30-60 min | Medium (manual dep updates) | Full control over every dependency. Choose which extras to install. Direct filesystem access without volume mounts. | Development, custom dependency setups, offline environments |
| systemd | 15-30 min | Low (auto-restart, logging) | Persistent MCP server, hourly cron job, one-shot pipeline units. Auto-restart on failure, boot-time enable. | Production Linux servers, 24/7 operation, headless deployment |
| Windows | 30-60 min | Medium (manual service setup) | Native Windows support for all CLI commands and MCP server. No WSL required. | Windows-only environments, hybrid Windows/Linux teams |

## Docker Deployment

The Docker image bundles AutoMedia with all external dependencies:
FFmpeg, Bun, edge-tts, faster-whisper, and Chromium. This is the fastest
way to get started.

- Pull the image: `docker pull kevinzhow/automedia-pipeline:latest`
- Run a command: `docker run -it --rm kevinzhow/automedia-pipeline:latest automedia doctor`
- Volume mount your data directories for persistence

For the MCP server, use Docker Compose. The `docker-compose.yml` file
defines three services:

- **app**. One-shot command runner.
- **mcp-server**. Base MCP server using stdio transport.
- **mcp-full**. Full-featured MCP server with Bun, edge-tts, faster-whisper,
  and Chromium. Gated behind the `full` profile. Build and run with
  `docker compose --profile full build mcp-full` and
  `docker compose --profile full up mcp-full`.

A devcontainer configuration (`.devcontainer/devcontainer.json`) is also
available for VS Code Remote development.

See [MCP Server Setup](mcp-setup.md) for detailed MCP configuration,
environment variables, and client setup.

## systemd Deployment

The `deploy/systemd/` directory contains three service units and one
timer, designed for production Linux servers:

| Unit | Type | Purpose |
|------|------|---------|
| `automedia-mcp.service` | `simple` | Persistent MCP server with auto-restart |
| `automedia-cron.service` | `oneshot` | Runs `automedia cron run` (triggered by timer) |
| `automedia-cron.timer` | timer | Fires the cron service hourly with a randomised delay |
| `automedia-pipeline.service` | `oneshot` | Runs a single pipeline. Topic and brand come from env file |

All units use `WorkingDirectory=/opt/automedia` and load environment
variables from files in `/etc/automedia/`. They ship with security
hardening enabled: `NoNewPrivileges=yes`, `PrivateTmp=yes`,
`ProtectSystem=full`, `ProtectHome=read-only`.

A healthcheck script at `deploy/systemd/healthcheck.sh` performs a
two-phase check: a fast `pgrep` pre-check followed by a real MCP
JSON-RPC ping.

For full installation and management instructions, see the
[archived systemd setup guide](../archived/mcp-systemd-setup.md).
The MCP server production deployment section in
[MCP Server Setup](mcp-setup.md#production-deployment-systemd) also
covers the same content with updated references.

## Windows Deployment

For Windows environments without WSL, AutoMedia can be installed and run
natively. All CLI commands and the MCP server work under Windows.

- Install Python 3.11+ via `winget` or python.org
- Install FFmpeg, Bun, Chromium using Windows package managers
- Run `pip install automedia-pipeline[all]` in a terminal

See [Windows Deployment](windows-deployment.md) for step-by-step
instructions covering PowerShell setup, service configuration, and
known Windows-specific issues.

## CI/CD Integration

### GitHub Actions

The Docker image is the recommended choice for CI/CD pipelines. Use
`docker run` directly in GitHub Actions jobs without installing any
Python dependencies:

```bash
docker run --rm \
  -e AUTOMEDIA_LLM_API_KEY="${{ secrets.AUTOMEDIA_LLM_API_KEY }}" \
  kevinzhow/automedia-pipeline:latest \
  automedia run --topic "..." --brand my-brand --mode text_only
```

For scheduled runs, use the `schedule` event in your workflow:

```yaml
on:
  schedule:
    - cron: "0 6 * * *"  # Daily at 06:00 UTC
```

For multi-topic batch pipelines, see the MCP `run_batch` tool.

### Cron (Native)

On Linux without systemd, use the host cron daemon:

```bash
# Run pipeline daily at 8 AM
0 8 * * * cd /opt/automedia && python -m automedia run --topic "..." --brand my-brand
```

The built-in `automedia cron` command handles topic selection, pipeline
execution, and logging. Configured schedules are stored in a SQLite
database and managed via the MCP `add_cron_schedule` /
`list_cron_schedules` / `remove_cron_schedule` tools.

See [Cron Troubleshooting](../dev/cron-troubleshooting.md) for debugging
scheduled jobs.

## Production Checklist

### Secrets Management

- Store `AUTOMEDIA_LLM_API_KEY` and platform credentials in the
  encrypted credential store, not in plaintext config files
- Use the `AUTOMEDIA_MASTER_KEY` environment variable for credential
  encryption (derived via SHA-256 to AES-256-GCM)
- Set `EnvironmentFile=` permissions to `600` for systemd deployments
- Never commit `.env`, `credentials.yaml`, `*.pem`, `*.key`, or `*.token`
  to version control (all gitignored by default)

### Health Checks

- Run `automedia doctor` to verify all system dependencies are present
- For MCP server monitoring, use `deploy/systemd/healthcheck.sh` which
  checks both process existence and JSON-RPC responsiveness
- Monitor via `sudo journalctl -u automedia-mcp -f` in systemd deployments
- The MCP `health_check` tool returns server uptime, version, and
  registered tool count
- The MCP `health_engine` tool checks TTS, ASR, image, and video
  engine status individually

### Monitoring

- **Logs**: systemd journals (`journalctl -u automedia-*`), or configure
  `AUTOMEDIA_LOG_LEVEL` to control verbosity
- **Alerts**: Configure a Feishu webhook via `FEISHU_WEBHOOK_URL` for
  pipeline failure notifications
- **Metrics**: The GateHook metrics collector (`automedia/hooks/metrics.py`)
  tracks gate pass/fail rates. Integrate with your monitoring stack via
  log scraping
- **Project tracking**: `list_projects` and `get_pipeline_status` in the
  MCP API let you query project state without filesystem access

### Backups

- **Project data**: Projects are stored under `AUTOMEDIA_PROJECTS_DIR`.
  Back up the entire projects directory periodically.
- **Topic pool**: The SQLite database (`pool.db`) contains your topic
  queue. Back it up alongside projects.
- **Configuration**: The `.automedia/` directory and
  `~/.automedia/overrides/` contain custom rules and prompt templates.
  Include these in your backup strategy.
- **Archive**: Use `automedia archive` (or the MCP `archive_project` tool)
  to move completed projects to a cold storage location. Archives can be
  purged after your retention period expires.
- **Credentials**: The encrypted credential store is tied to
  `AUTOMEDIA_MASTER_KEY`. Back up the store file but keep the master key
  separate and secure.

## Related Documentation

| Document | What It Covers |
|----------|---------------|
| [MCP Server Setup](mcp-setup.md) | MCP configuration, client setup, environment variables, path allowlist |
| [Production Workflow](production-workflow.md) | End-to-end production operations guide |
| [CLI Reference](cli-reference.md) | All CLI commands and their options |
| [API Reference](api-reference.md) | SDK function signatures |
| [Cron Troubleshooting](../dev/cron-troubleshooting.md) | Debugging scheduled job issues |
| [Security](../..) | Security model, path allowlist, credential store (see README Security section) |
