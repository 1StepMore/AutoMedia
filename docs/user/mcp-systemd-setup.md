---
title: MCP systemd Setup
description: Run the AutoMedia MCP server as a persistent systemd service with auto-restart on failure.
---

# MCP Server — systemd Service Setup

Run the AutoMedia MCP server as a persistent systemd service so it stays
alive across reboots and restarts automatically on failure.

## Prerequisites

- AutoMedia installed in a Python environment reachable by the systemd unit.
- `sudo` access on the host where the service will run.

## Files

| File | Purpose |
|------|---------|
| `deploy/systemd/automedia-mcp.service` | systemd unit definition |
| `deploy/systemd/automedia-mcp.env` | Environment variable template |
| `docs/user/mcp-systemd-setup.md` | This guide |

## Installation

### 1. Copy the service unit

```bash
sudo cp deploy/systemd/automedia-mcp.service /etc/systemd/system/
```

### 2. Create the env directory and copy the env file

```bash
sudo mkdir -p /etc/automedia
sudo cp deploy/systemd/automedia-mcp.env /etc/automedia/automedia-mcp.env
sudo chmod 600 /etc/automedia/automedia-mcp.env
```

### 3. Edit the env file

```bash
sudo vim /etc/automedia/automedia-mcp.env
```

At minimum, set `AUTOMEDIA_LLM_API_KEY`. Uncomment and adjust other
variables as needed.

### 4. Review the service unit

If your Python environment is not the system default (e.g. you use a
virtualenv), edit the `ExecStart` path in the service file:

```bash
sudo vim /etc/systemd/system/automedia-mcp.service
```

Change:

```
ExecStart=python -m automedia.mcp.server
```

to:

```
ExecStart=/home/automedia/.venv/bin/python -m automedia.mcp.server
```

Also adjust `WorkingDirectory` to match your deployment layout.

### 5. Reload systemd and enable the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable automedia-mcp
```

### 6. Start the service

```bash
sudo systemctl start automedia-mcp
```

### 7. Verify the service is running

```bash
sudo systemctl status automedia-mcp
```

Expected output includes `Active: active (running)`.

### 8. Security hardening note

The service files ship with `ProtectHome=read-only` enabled. Since
AutoMedia reads user configuration from `~/.automedia/`, the service
files also include `ReadWritePaths=/home/*/.automedia` to grant the
service access to user-level config while keeping the rest of `/home/`
protected.

If you deploy with a non-standard home directory layout, adjust
`ReadWritePaths` accordingly — for example:

```ini
ReadWritePaths=/opt/automedia/.automedia
```

### 9. View logs

```bash
# Follow new log entries
sudo journalctl -u automedia-mcp -f

# View the last 100 lines
sudo journalctl -u automedia-mcp -n 100

# View all logs since the service started
sudo journalctl -u automedia-mcp --since "5 minutes ago"
```

## Management

| Action | Command |
|--------|---------|
| Start | `sudo systemctl start automedia-mcp` |
| Stop | `sudo systemctl stop automedia-mcp` |
| Restart | `sudo systemctl restart automedia-mcp` |
| Status | `sudo systemctl status automedia-mcp` |
| Enable on boot | `sudo systemctl enable automedia-mcp` |
| Disable on boot | `sudo systemctl disable automedia-mcp` |
| View logs | `sudo journalctl -u automedia-mcp` |
| Follow logs | `sudo journalctl -u automedia-mcp -f` |

## Verification

Check that the MCP server registers its tools correctly:

```bash
python -m automedia.mcp.server --show-tools
```

If using stdio transport, test connectivity from the CLI:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | sudo -u automedia python -m automedia.mcp.server
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `python: command not found` | Python not on systemd `PATH` | Use absolute path to Python in `ExecStart` |
| Permission denied on env file | Wrong ownership or mode | `sudo chmod 600 /etc/automedia/automedia-mcp.env` |
| Service starts then immediately exits | Missing API key or import error | Check logs with `journalctl -u automedia-mcp -n 50` |
| `WorkingDirectory` does not exist | Path mismatch | Create the directory or update `WorkingDirectory` in the unit file |
