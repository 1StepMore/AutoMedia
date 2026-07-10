# Agent Troubleshooting Guide

This guide is for AI coding agents working with the AutoMedia codebase. It helps diagnose and fix common issues when running pipelines, dealing with configuration, or encountering gate failures.

---

## 1. Pipeline Failures

### Diagnosing a failed pipeline

When a pipeline returns a `PipelineResult` with `status="failed"` or `status="partial"`, follow these steps:

**Step 1: Check the project info file**

Every project stores metadata in `00_project_info.json` at the project root. Read this file first:

```bash
cat <project-dir>/00_project_info.json
```

The file contains `project_id`, `topic`, `brand`, `tenant_id`, and `created_at`. If this file is missing or malformed, the pipeline may not have initialized properly.

**Step 2: Check the PipelineResult**

The `run_full_pipeline()` function returns a `PipelineResult` dataclass:

| Field | Type | Meaning |
|-------|------|---------|
| `status` | `"success"`, `"failed"`, `"partial"`, `"rl9_violation"` | Overall pipeline outcome |
| `gates_log` | `list[GateLogEntry]` | Per-gate pass/fail with duration and error |
| `error` | `str \| None` | Top-level error message (only for unexpected exceptions) |
| `assets` | `list[AssetInfo]` | Produced asset metadata (type, path, md5) |

A `status="partial"` means some gates passed but a `failure_mode="stop"` gate failed or a `failure_mode="rewrite"` gate failed and the pipeline continued.

**Step 3: Interpret gate failure modes**

Each gate has a `failure_mode` defined at the class level:

- **`"stop"`** — Halts the pipeline immediately on failure. The result will contain results only up to the failing gate. Gates with this mode: D0, pre-gate, G0, G2, G3, G4, G5, V0, V3, V6, V7, L1, L2, L3, L4.
- **`"rewrite"`** — The gate can be retried. The pipeline continues even if this gate fails. Gates with this mode: CW, G1, V1, V2, V4, V5.

Gates with `"rewrite"` mode can be retried by re-running the pipeline with `resume_from` set to the failed gate name.

**Step 4: Read gate logs**

The `gates_log` field in `PipelineResult` contains `GateLogEntry` objects:

```
GateLogEntry(gate_name="G0", status="failed", duration_s=3.2, error="Source URL domain not found in content")
```

Check the `error` field of each failed entry. If the error message is generic (e.g. an LLM timeout), the failure may be transient.

**Step 5: Retry a failed pipeline**

Use the `resume_from` parameter to skip gates that already passed:

```python
result = run_full_pipeline(
    topic="AI tools",
    brand="my-brand",
    resume_from="G0",  # skip D0, pre-gate, CW and start from G0
)
```

The `resume_from` value must match a gate name in the current mode's gate list (`_AUTO_GATE_NAMES`, `_TEXT_ONLY_GATE_NAMES`, etc. in `automedia/pipelines/runner.py`). If the name is not found, a `ValueError` is raised.

### Pipeline status values

| Status | Meaning | Next Steps |
|--------|---------|------------|
| `"success"` | All gates passed | Pipeline complete, assets ready |
| `"partial"` | Some gates failed, pipeline continued | Check `gates_log` for failures, retry specific gates |
| `"failed"` | Unexpected exception before or during execution | Check `error` field for stack trace |
| `"rl9_violation"` | D0 gate rejected due to missing provenance | Run Decision Layer or use `force_provenance=True` |

---

## 2. Configuration Issues

### Missing environment variables

The most common config error is a missing `AUTOMEDIA_LLM_API_KEY`. The LLM client will return an authentication error that propagates as a gate failure (typically in CW, G0, or any LLM-dependent gate).

```bash
# Verify your environment variables are set
echo $AUTOMEDIA_LLM_API_KEY

# Expected output: sk-... (non-empty)
```

If the variable is missing, set it in your shell or in the MCP client config:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"],
      "env": {"AUTOMEDIA_LLM_API_KEY": "sk-your-key-here"}
    }
  }
}
```

### Wrong provider or model

The `AUTOMEDIA_LLM_PROVIDER` and `AUTOMEDIA_LLM_MODEL` variables must match a supported provider. Default values:

| Variable | Default | Acceptable Values |
|----------|---------|-------------------|
| `AUTOMEDIA_LLM_PROVIDER` | `deepseek` | `deepseek`, `openai`, `anthropic`, `openrouter` |
| `AUTOMEDIA_LLM_MODEL` | `deepseek-chat` | Depends on provider |
| `AUTOMEDIA_LLM_BASE_URL` | `https://api.deepseek.com/v1` | Provider-specific API endpoint |

Setting an unknown provider name will cause the LLM client initialization to fail. Check `automedia/core/llm_client.py` for the list of supported providers.

### 6-layer config merge order

Configuration merges from lowest to highest priority. A value in a higher-priority layer overrides the same key in lower layers:

1. Built-in `automedia/manifests/defaults.yaml`
2. Project `.automedia/` directory
3. User `~/.automedia/` directory
4. `~/.automedia/overrides/rules/*.yaml`
5. `~/.automedia/overrides/prompts/*.j2`
6. `AUTOMEDIA_*` environment variables + explicit `overrides` parameter

If a config value is not what you expect, check each layer in order. The `deep_merge()` function in `automedia/core/config_loader.py` recursively merges dicts and overwrites scalars.

### Using automedia doctor

The `automedia doctor` command checks system dependencies and config health:

```bash
automedia doctor
```

It verifies that `python`, `bun`, `ffmpeg`, `whisper`, `edge-tts`, `chrome`, and `comfyui` (optional) are available on `$PATH`. The implementation is in `automedia/core/doctor.py`.

If a dependency is missing, install it. For example:

```bash
# FFmpeg
sudo apt-get install ffmpeg   # Ubuntu/Debian
brew install ffmpeg           # macOS

# Bun
curl -fsSL https://bun.sh/install | bash

# Whisper
pip install faster-whisper

# Chrome/Chromium
sudo apt-get install chromium-browser
```

---

## 3. MCP Server Issues

### Server not starting

If `python -m automedia.mcp.server` fails silently or with an import error:

1. Make sure the package is installed: `pip install -e .`
2. Verify Python version is 3.11+: `python --version`
3. Check for missing dependencies: the MCP server requires the `mcp` Python package (install with `pip install -e ".[mcp]"`)

### Allowlist rejecting paths

All file operations through the MCP server are restricted by the path allowlist at `automedia/mcp/mcp_allowlist.yaml`. If you get a path rejection error:

```yaml
# mcp_allowlist.yaml
allowed_directories:
  - /tmp/automedia/
```

Only paths under the listed directories are accessible. If your project directory is outside the allowlist, the MCP server will reject the operation with a permission error.

**Do not modify `mcp_allowlist.yaml` without explicit user request** (Red Line 3 in AGENTS.md).

To work around allowlist restrictions:
- Place project directories under an already-allowed path (e.g. `/tmp/automedia/`)
- Ask the user to add the desired path to the allowlist
- Use the CLI directly instead of MCP tools (CLI has no path restrictions)

### Tool not found

If an MCP tool call returns "tool not found":

1. Verify the server is running: check that `python -m automedia.mcp.server` is still running
2. Check the tool name against the 13 tools listed in AGENTS.md section 9
3. Restart the server: kill the process and start it again

### Testing MCP tools directly

You can test MCP tools by running the server interactively:

```bash
# Start the server
python -m automedia.mcp.server

# In another terminal, send JSON-RPC messages over stdio
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m automedia.mcp.server
```

This prints all available tools and their parameters.

### Background pipeline progress

The MCP tool `run_pipeline` executes the pipeline in a background thread. Poll for progress with `get_pipeline_progress`:

```bash
# Get progress for a running pipeline
get_pipeline_progress(project_id="<project-id>")
```

The response includes `current_gate` (the gate currently executing) and `events` (list of completed gate events with status).

---

## 4. Gate Failures

For detailed mode-by-mode troubleshooting of each gate, see `docs/runbook/gate-failure-modes.md`. This section summarizes common patterns.

### D0 — Provenance Gate (RL9)

The D0 gate enforces Red Line 9: the pipeline must have a legitimate brand provenance decision before proceeding.

**Failure pattern:** Pipeline returns `status="rl9_violation"` and `gates_log` shows D0 with `status="failed"` and error about missing Decision Layer artifacts.

**Fixes:**
- Run the Decision Layer first: `automedia solution build --topic "..." --brand my-brand`
- Or bypass RL9: pass `force_provenance=True` to `run_full_pipeline()` or use `--confirm-bypass-rl9` on the CLI

### CW — Content Writer Gate

The CW gate uses the LLM to generate draft content. Failures here are usually LLM-related.

**Failure patterns:**
- Empty or error response from LLM provider (check API key, rate limits, network)
- Token limit exceeded (increase `max_tokens` or split content into sections)
- Topic brief too vague (enrich with more specific instructions)

### G0 — Fact Check Gate

The G0 gate performs 5-step verification. See `automedia/gates/failure_modes.py` for the full list of checks.

**Key gotcha:** LLMs often round or approximate numbers (e.g. "3.2%" becomes "about 3%"). The gate expects exact values from `source_data.key_numbers`. Force the LLM to use raw values.

### G3 — Brand CTA Gate

The brand name "壹目贯维" is frequently miswritten by LLMs as "一目贯维" or "壹目惯维". The gate does character-level verification.

**Fix:** Always verify the brand name character-by-character in the prompt.

### V1 — Vision QA Gate

When the Vision API rate limit is hit, V1 degrades to a pixel-luminance fallback. The QA report includes the word "降级" (degraded) in this case. Accuracy drops but the pipeline does not block.

### V5 — MP3 vs SRT Gate

This gate cross-validates audio duration against subtitle timing. A common failure is WPM exceeding 300. Fix by rewriting dense subtitle segments to reduce word count.

### L1-L4 — Lifecycle Gates

These gates validate publish logs, archives, platform integrity, and translation quality. They run after content and video gates. Failures here usually mean missing artifacts or schema mismatches.

---

## 5. CLI Command Debugging

### Verify command syntax

Every CLI command is defined in `automedia/cli/commands/`. The main app is in `automedia/cli/app.py`. Use the `--help` flag on any command:

```bash
automedia --help
automedia run --help
automedia archive --help
```

### Check project directory structure

A valid project has this structure:

```
<project-dir>/
├── 00_project_info.json         # Project metadata
├── 01_content/
│   └── drafts/                  # Generated drafts
├── 02_images/
│   └── cover/                   # Cover images
├── 03_video/                    # Video output
├── 04_subtitle/                 # Subtitle files
├── 05_review/                   # Review artifacts
└── 06_publish/                  # Publish logs
```

If `00_project_info.json` is missing, the project is incomplete. Run the pipeline again.

### Inspect gate output files

Each gate may produce output files in the project directory. Check the relevant subdirectory:

- CW gate output -> `01_content/drafts/`
- Image gates -> `02_images/cover/`
- Video gates -> `03_video/`
- Subtitle gates -> `04_subtitle/`

The `pipeline_md5.json` file in the project root records MD5 checksums of gate outputs. Compare against this to detect corruption:

```bash
cat <project-dir>/pipeline_md5.json
```

### Debugging with log levels

The pipeline uses `structlog` for structured logging. Set the `AUTOMEDIA_LOG_LEVEL` environment variable to control verbosity:

```bash
export AUTOMEDIA_LOG_LEVEL=debug
automedia run --topic "test" --brand my-brand
```

### Listing projects

List all projects and their status:

```bash
automedia projects list
```

This scans directories for `00_project_info.json` files and reads metadata from each.

---

## 6. Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `AUTOMEDIA_LLM_API_KEY` not set | Missing required environment variable | Set the API key: `export AUTOMEDIA_LLM_API_KEY=sk-...` or pass it in MCP config `env` |
| Gate returns `"passed": False` with no error message | Gate completed but found issues in content (e.g. fact check failed) | Check the `result` dict gate-specific details. See section 4 above and `docs/runbook/gate-failure-modes.md` |
| `ValueError: Unknown pipeline mode '...'` | Invalid mode string passed to `run_full_pipeline()` | Use one of: `"auto"`, `"text_only"`, `"video_only"`, `"qa_only"` |
| `ValueError: resume_from gate '...' not found in mode '...' gate list` | `resume_from` value does not match any gate name for the current mode | Check the mode's gate list in `automedia/pipelines/runner.py` (`_AUTO_GATE_NAMES`, etc.) |
| `ModuleNotFoundError: No module named 'mcp'` | MCP dependencies not installed | Install with `pip install -e ".[mcp]"` |
| `Permission denied` when accessing files via MCP | Path is not in `mcp_allowlist.yaml` | Ask the user to add the path to the allowlist, or use a path under `/tmp/automedia/` |
| `status="rl9_violation"` | D0 gate rejected due to missing decision provenance | Run Decision Layer first (`automedia solution build`) or pass `force_provenance=True` |
| Brand name "壹目贯维" written as "一目贯维" | LLM writes homophone characters for the brand name | Add character-level verification in the prompt. The G3 gate rejects incorrect characters |
| `ValueError: topic_slug '...' produces empty slug after sanitisation` | Topic string contains no ASCII characters after slugification (e.g., pure CJK) | Add an ASCII keyword to the topic or set the topic to include Latin characters |
| `ValueError: Path must not contain '..'` | Path traversal detected in brand or base_dir | Check for `..`, `~`, or `//` in the path parameter |
| `Result has status="partial" with G0-V7 all passing` | A lifecycle gate (L1-L4) failed | Check L1-L4 gate outputs. These usually fail due to missing artifacts or schema mismatches |
| Audio/Video gates fail with "file not found" | Asset files were not produced by a previous gate | Run the pipeline without `resume_from` to ensure prerequisite gates execute |
| `PipelineProgress` shows gate stuck in `"running"` for >5 minutes | LLM call timed out or gate logic is hanging | Check network connectivity and LLM provider status. Restart the pipeline |
| `ffprobe` reports unexpected duration in V5 gate | MP3 audio file is corrupted or truncated | Re-generate the TTS audio and verify with `ffprobe` |

---

For detailed gate failure mode troubleshooting, see `docs/runbook/gate-failure-modes.md`.
