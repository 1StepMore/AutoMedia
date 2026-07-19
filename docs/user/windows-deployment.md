---
title: Windows Deployment
description: Set up AutoMedia on Windows — WSL2, Docker Desktop, and native Windows paths.
---

# Windows Deployment

AutoMedia runs on Windows through three paths. Pick the one that fits your setup:

- **WSL2 (recommended)** — Full Linux environment on Windows. Best compatibility.
- **Docker Desktop** — Containerized setup, no manual dependency install.
- **Native Windows** — Runs directly on Windows with Python via winget.

## Prerequisites

Before any path, make sure you have:

- Windows 10 version 2004+ or Windows 11
- 8 GB RAM minimum (16 GB recommended)
- Admin rights for software installation
- [Git for Windows](https://git-scm.com/download/win) (`winget install Git.Git`)
- At least 10 GB free disk space

---

## Path 1: WSL2 Setup (Recommended)

WSL2 gives you a full Linux kernel inside Windows. This is the smoothest way to run AutoMedia, because all Linux tooling (FFmpeg, Bun, edge-tts) works without translation layers.

### 1. Install WSL2

Open PowerShell as Administrator and run:

```powershell
wsl --install -d Ubuntu-24.04
```

This installs WSL2 and Ubuntu 24.04. Restart your machine when prompted.

After reboot, verify:

```powershell
wsl -l -v
```

You should see `Ubuntu-24.04` running version 2.

### 2. Install AutoMedia inside WSL2

Open your WSL2 terminal (type `wsl` in PowerShell or start "Ubuntu" from Start Menu):

```bash
# Update packages
sudo apt-get update && sudo apt-get upgrade -y

# Install Python 3.11+
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Install FFmpeg
sudo apt-get install -y ffmpeg

# Install Bun
curl -fsSL https://bun.sh/install | bash

# Reload PATH for Bun
source ~/.bashrc

# Install edge-tts
pip install edge-tts

# Install Whisper (choose one)
pip install faster-whisper

# Clone AutoMedia
git clone https://github.com/1stepmore/automedia.git
cd automedia

# Run setup script
bash scripts/setup.sh
```

### 3. Access Windows Files from WSL2

Your Windows drives are mounted under `/mnt/`:

```bash
# Access C: drive
cd /mnt/c/Users/YourName/projects

# Or work inside WSL2's native filesystem (faster for I/O)
cd ~/automedia
```

> **Tip:** Work inside the WSL2 filesystem (`~/automedia`) for better performance. The `/mnt/c` mount is slower for file I/O.

### 4. MCP Server in WSL2

The MCP server runs inside WSL2. Configure your MCP client to point to the WSL2 Python:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "wsl",
      "args": ["python", "-m", "automedia.mcp.server"],
      "env": {
        "AUTOMEDIA_LLM_API_KEY": "sk-xxx"
      }
    }
  }
}
```

Some MCP clients (Claude Desktop, OpenCode) can invoke WSL commands directly. If your client runs on Windows and needs to talk to WSL2, use `wsl` as the command.

### 5. WSL2 Management

| Action | Command (PowerShell) |
|--------|---------------------|
| Start WSL2 | `wsl` |
| Shut down WSL2 | `wsl --shutdown` |
| List distros | `wsl -l -v` |
| Set default version | `wsl --set-default-version 2` |
| Open file explorer | `wsl --cd ~` then `explorer.exe .` |

---

## Path 2: Docker Desktop

If you prefer containers over managing dependencies, Docker Desktop is the quickest path.

### 1. Install Docker Desktop

```powershell
winget install Docker.DockerDesktop
```

After install, launch Docker Desktop, go to **Settings > Resources > WSL Integration**, and enable integration with your Ubuntu distro.

### 2. Pull and Run AutoMedia

```powershell
docker pull kevinzhow/automedia-pipeline:latest
docker run -it --rm kevinzhow/automedia-pipeline:latest automedia doctor
```

### 3. Use with Local Directories

Mount your Windows project directory into the container:

```powershell
docker run -it --rm `
  -v C:\Users\YourName\projects:/data `
  -e AUTOMEDIA_LLM_API_KEY=sk-xxx `
  kevinzhow/automedia-pipeline:latest `
  automedia run --topic "Your Topic" --brand my-brand
```

### 4. MCP Server via Docker

Run the MCP server as a Docker container:

```powershell
docker run -d --name automedia-mcp `
  -v C:\Users\YourName\.automedia:/home/automedia/.automedia `
  -e AUTOMEDIA_LLM_API_KEY=sk-xxx `
  kevinzhow/automedia-pipeline:latest `
  python -m automedia.mcp.server
```

For clients on the Windows host, configure:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "docker",
      "args": [
        "exec", "-i", "automedia-mcp",
        "python", "-m", "automedia.mcp.server"
      ],
      "env": {
        "AUTOMEDIA_LLM_API_KEY": "sk-xxx"
      }
    }
  }
}
```

---

## Path 3: Native Windows Setup

Run AutoMedia directly on Windows without WSL2 or Docker.

### 1. Install Python 3.11+

```powershell
winget install Python.Python.3.11
```

Close and reopen PowerShell, then verify:

```powershell
python --version
```

### 2. Install FFmpeg

```powershell
winget install "FFmpeg (Essentials Build)"
```

Verify:

```powershell
ffmpeg -version
```

Add FFmpeg to your PATH if winget doesn't do it automatically:

```powershell
$ffmpegPath = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\FFmpeg.Essentials_Build_Microsoft.Winget.Source_*\ffmpeg.exe"
$resolved = Resolve-Path $ffmpegPath
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";" + $resolved.Directory, "User")
```

### 3. Install Bun

```powershell
powershell -c "irm https://bun.sh/install.ps1 | iex"
```

Verify (reopen PowerShell):

```powershell
bun --version
```

### 4. Install Google Chrome

```powershell
winget install Google.Chrome
```

### 5. Clone and Setup AutoMedia

```powershell
git clone https://github.com/1stepmore/automedia.git
cd automedia
```

Create a virtual environment and install:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[all]"
```

> **Note:** If you get an execution policy error when activating the venv, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

Initialize configuration:

```powershell
automedia init
automedia doctor
```

### 6. Environment Variables

Set AutoMedia environment variables. You can add these to your PowerShell profile (`$PROFILE`):

```powershell
$env:AUTOMEDIA_LLM_API_KEY = "sk-xxx"
$env:AUTOMEDIA_PROJECTS_DIR = "$env:USERPROFILE\automedia-projects"
```

To make them permanent, add them to your PowerShell profile:

```powershell
# Check if profile exists
Test-Path $PROFILE

# If not, create it
New-Item -Path $PROFILE -ItemType File -Force

# Edit profile
notepad $PROFILE
```

Add this line to the profile:

```powershell
$env:AUTOMEDIA_LLM_API_KEY = "sk-xxx"
```

### 7. Install edge-tts and Whisper

```powershell
pip install edge-tts
pip install faster-whisper
```

### 8. Path Differences on Windows

AutoMedia reads and writes files using Python path handling, which works on Windows. But be aware of these differences:

| Concept | Linux/WSL2 | Windows |
|---------|-----------|---------|
| Config directory | `~/.automedia/` | `$env:USERPROFILE\.automedia\` |
| Project separator | `/` | `\` (AutoMedia normalizes internally) |
| Virtual environment | `.venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| Python command | `python3` | `python` |
| WSL paths | `/mnt/c/Users/...` | `C:\Users\...` |

### 9. Run the Windows Setup Script

For a one-command setup, use the provided PowerShell script:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\scripts\setup.ps1
```

See [Scripts Reference](#scripts-reference) for details.

---

## MCP Server as Windows Service (NSSM)

For production deployments on Windows, run the MCP server as a Windows service using NSSM (Non-Sucking Service Manager).

### 1. Install NSSM

```powershell
winget install NSSM.NSSM
```

Or download from [nssm.cc](https://nssm.cc/download) and add to PATH.

### 2. Create the Service

```powershell
nssm install AutoMedia-MCP "C:\path\to\automedia\.venv\Scripts\python.exe" "-m automedia.mcp.server"
```

Set the working directory and environment:

```powershell
nssm set AutoMedia-MCP AppDirectory "C:\path\to\automedia"
nssm set AutoMedia-MCP AppEnvironmentExtra AUTOMEDIA_LLM_API_KEY=sk-xxx AUTOMEDIA_LOG_LEVEL=INFO
```

### 3. Manage the Service

```powershell
# Start
nssm start AutoMedia-MCP

# Stop
nssm stop AutoMedia-MCP

# Restart
nssm restart AutoMedia-MCP

# Status
nssm status AutoMedia-MCP
```

Or use the standard PowerShell service cmdlets:

```powershell
Get-Service AutoMedia-MCP
Start-Service AutoMedia-MCP
Stop-Service AutoMedia-MCP
```

### 4. View Logs

NSSM writes logs to the directory specified during install. By default, these go to `C:\path\to\automedia\logs\`. Check:

```powershell
Get-Content "C:\path\to\automedia\logs\AutoMedia-MCP.log" -Tail 50
```

---

## Environment Variables Reference

| Variable | Description | Windows Example |
|----------|-------------|-----------------|
| `AUTOMEDIA_LLM_API_KEY` | LLM API key | `sk-xxx` |
| `AUTOMEDIA_LLM_BASE_URL` | Custom API endpoint | `https://api.deepseek.com/v1` |
| `AUTOMEDIA_LLM_PROVIDER` | LLM provider name | `deepseek` |
| `AUTOMEDIA_LLM_MODEL` | Model identifier | `deepseek-chat` |
| `AUTOMEDIA_PROJECTS_DIR` | Projects root directory | `C:\Users\You\automedia-projects` |
| `AUTOMEDIA_MCP_ALLOWLIST_PATH` | Custom allowlist path | `C:\Users\You\.automedia\allowlist.yaml` |
| `AUTOMEDIA_MASTER_KEY` | Master key for credential encryption | (32+ hex chars) |
| `AUTOMEDIA_LOG_LEVEL` | Log level | `INFO`, `DEBUG`, `WARNING` |

Set them in PowerShell:

```powershell
$env:AUTOMEDIA_PROJECTS_DIR = "C:\Users\You\automedia-projects"
[Environment]::SetEnvironmentVariable("AUTOMEDIA_PROJECTS_DIR", "C:\Users\You\automedia-projects", "User")
```

The second command makes it permanent for your user account.

---

## Scripts Reference

| Script | Purpose | How to Run (Windows) |
|--------|---------|---------------------|
| `scripts/setup.ps1` | One-command venv + install + init | `.\scripts\setup.ps1` |
| `scripts/setup.sh` | Linux/WSL2 setup (same as setup.ps1) | `bash scripts/setup.sh` (in WSL2) |
| `scripts/run-tests.sh` | pytest with coverage | `bash scripts/run-tests.sh` (in WSL2) |
| `scripts/mcp-server.sh` | MCP launcher | WSL2 only (uses SIGTERM handler) |

### setup.ps1 Details

The PowerShell setup script (`scripts/setup.ps1`) does the following:

1. Checks for Python 3.11+
2. Creates a Python virtual environment (`.venv`)
3. Activates the virtual environment
4. Installs AutoMedia with `pip install -e ".[all]"`
5. Installs FFmpeg via winget (if missing)
6. Installs Bun via the official install script (if missing)
7. Runs `automedia init` to initialize configuration
8. Runs `automedia doctor` to verify dependencies

---

## Troubleshooting

### WSL2 Issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `wsl: command not found` | WSL2 not installed | Run `wsl --install -d Ubuntu-24.04` as Admin |
| WSL2 is slow on `/mnt/c/` | Cross-filesystem I/O | Move project to WSL2 native fs: `cp -r /mnt/c/... ~/automedia` |
| `vmmem` uses too much RAM | WSL2 memory limit | Create `%USERPROFILE%\.wslconfig` with `memory=8GB` |
| Network issues in WSL2 | VPN or proxy conflict | Restart WSL2: `wsl --shutdown` then `wsl` |
| `System has not been booted with systemd` | WSL2 defaults to init | Add `systemd=true` to `/etc/wsl.conf` in WSL2, then `wsl --shutdown` |

### Docker Desktop Issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Docker Desktop fails to start | WSL2 not installed/updated | `wsl --update` then restart Docker Desktop |
| `docker: command not found` | Not in PATH | Reinstall Docker Desktop or add to PATH manually |
| Volume mounts empty | Windows path with wrong format | Use forward slashes: `-v C:/Users/...:/data` |
| Container exits immediately | Missing environment or config | Check logs: `docker logs automedia-mcp` |

### Native Windows Issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `python: command not found` | Python not in PATH | Reinstall with "Add Python to PATH" checked, or run `$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")` |
| `ffmpeg: command not found` | FFmpeg not in PATH | Run `refreshenv` or restart PowerShell. Or add manually: `[Environment]::SetEnvironmentVariable("Path", "$env:Path;C:\tools\ffmpeg\bin", "User")` |
| Execution policy blocks scripts | PowerShell security | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `venv` activation fails | Execution policy | Same fix as above. Then run `.\\.venv\\Scripts\\Activate.ps1` |
| Bun install hangs | Network/firewall issue | Try with `-SkipCertificateCheck`: `[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }` before the install command |
| Long path errors | Windows MAX_PATH limit | Enable long paths: `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force` |
| Audio processing fails | Missing codecs | Install FFmpeg full build (not essentials) from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) |

### MCP Client on Windows

If your MCP client (Claude Desktop, OpenCode) runs on the Windows host and needs to connect to AutoMedia:

- **With WSL2:** Configure the client to run `wsl python -m automedia.mcp.server` as the command
- **With Docker:** Configure the client to run `docker exec -i automedia-mcp python -m automedia.mcp.server`
- **Native:** Use the full path to the venv Python: `C:\path\to\automedia\.venv\Scripts\python.exe -m automedia.mcp.server`

### Getting Help

If you run into Windows-specific issues not covered here:

1. Check the [AutoMedia Troubleshooting Guide](../dev/agent-troubleshooting.md)
2. Open a GitHub issue with your Windows version and the path you're using (WSL2/Docker/native)
3. Include the output of `automedia doctor` and your PowerShell version (`$PSVersionTable.PSVersion`)
