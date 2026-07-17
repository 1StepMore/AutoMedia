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
| `status` | `"success"`, `"failed"`, `"partial"` | Overall pipeline outcome |
| `gates_log` | `list[GateLogEntry]` | Per-gate pass/fail with duration and error |
| `error` | `str \| None` | Top-level error message (only for unexpected exceptions) |
| `assets` | `list[AssetInfo]` | Produced asset metadata (type, path, md5) |

A `status="partial"` means some gates passed but a `failure_mode="stop"` gate failed or a `failure_mode="retry"` gate failed and the pipeline continued.

**Step 3: Interpret gate failure modes**

Each gate has a `failure_mode` defined at the class level:

- **`"stop"`** — Halts the pipeline immediately on failure. The result will contain results only up to the failing gate. Gates with this mode: pre-gate, CW, G0, G3, G4, G5, V0, V1, V2, V3, V4, V6, V7, L1, L2, L3, L4, H0.
- **`"retry"`** — The gate can be retried. The pipeline continues even if this gate fails. Gates with this mode: G1, G2, V5.

Gates with `"retry"` mode can be retried by re-running the pipeline with `resume_from` set to the failed gate name.

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
    resume_from="G0",  # skip pre-gate, CW and start from G0
)
```

The `resume_from` value must match a gate name in the current mode's gate list (`_AUTO_GATE_NAMES`, `_TEXT_ONLY_GATE_NAMES`, etc. in `automedia/pipelines/runner.py`). If the name is not found, a `ValueError` is raised.

### Pipeline status values

| Status | Meaning | Next Steps |
|--------|---------|------------|
| `"success"` | All gates passed | Pipeline complete, assets ready |
| `"partial"` | Some gates failed, pipeline continued | Check `gates_log` for failures, retry specific gates |
| `"failed"` | Unexpected exception before or during execution | Check `error` field for stack trace |
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
2. Check the tool name against the 41 tools listed in AGENTS.md section 9
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

### H0 — Human Review Gate (Pre-Publish)

H0 is a pre-publish HITL gate. Failure means the pipeline is paused waiting for human review. Approve via the decision layer SDK (`from automedia.hitl import NodeExecutor; executor.approve_node(...)`) or pass `auto_publish=True` to skip HITL.

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
| `ValueError: Unknown pipeline mode '...'` | Invalid mode string passed to `run_full_pipeline()` | Use one of: `"auto"`, `"text_only"`, `"text_with_cover"`, `"video_only"`, `"qa_only"`, `"image-carousel"`, `"social-thread"`, `"short-video"` |
| `ValueError: resume_from gate '...' not found in mode '...' gate list` | `resume_from` value does not match any gate name for the current mode | Check the mode's gate list in `automedia/pipelines/runner.py` (`_AUTO_GATE_NAMES`, etc.) |
| `ModuleNotFoundError: No module named 'mcp'` | MCP dependencies not installed | Install with `pip install -e ".[mcp]"` |
| `Permission denied` when accessing files via MCP | Path is not in `mcp_allowlist.yaml` | Ask the user to add the path to the allowlist, or use a path under `/tmp/automedia/` |
| Brand name "壹目贯维" written as "一目贯维" | LLM writes homophone characters for the brand name | Add character-level verification in the prompt. The G3 gate rejects incorrect characters |
| `ValueError: topic_slug '...' produces empty slug after sanitisation` | Topic string contains no ASCII characters after slugification (e.g., pure CJK) | Add an ASCII keyword to the topic or set the topic to include Latin characters |
| `ValueError: Path must not contain '..'` | Path traversal detected in brand or base_dir | Check for `..`, `~`, or `//` in the path parameter |
| `Result has status="partial" with G0-V7 all passing` | A lifecycle gate (L1-L4) failed | Check L1-L4 gate outputs. These usually fail due to missing artifacts or schema mismatches |
| Audio/Video gates fail with "file not found" | Asset files were not produced by a previous gate | Run the pipeline without `resume_from` to ensure prerequisite gates execute |
| `PipelineProgress` shows gate stuck in `"running"` for >5 minutes | LLM call timed out or gate logic is hanging | Check network connectivity and LLM provider status. Restart the pipeline |
| `ffprobe` reports unexpected duration in V5 gate | MP3 audio file is corrupted or truncated | Re-generate the TTS audio and verify with `ffprobe` |

---

## 7. FFmpeg Video Synthesis Troubleshooting

Video synthesis depends on FFmpeg for encoding, decoding, and format conversion. Failures here produce unreadable or missing video output.

### FFmpeg not found

The pipeline checks for FFmpeg at startup via `automedia doctor`. If missing:

**Symptoms:** Pipeline fails at V0 (Lint) or V6 (Subtitle Render) with "ffmpeg not found" or "command not found".

**Fixes:**
- Install FFmpeg via your package manager: `sudo apt-get install ffmpeg` (Ubuntu) or `brew install ffmpeg` (macOS)
- Verify installation: `ffmpeg -version`
- If installed but not on `$PATH`, symlink it: `sudo ln -s /path/to/ffmpeg /usr/local/bin/ffmpeg`

### Video encoding fails

**Symptoms:** FFmpeg returns non-zero exit code; output file is 0 bytes or missing; log contains "Error while encoding" or " Unknown encoder".

**Common causes and fixes:**

| Cause | Log pattern | Fix |
|-------|-------------|-----|
| Codec not supported | `Unknown encoder 'libx264'` | Rebuild FFmpeg with `--enable-libx264` or use a codec available in your build |
| Pixel format mismatch | `Invalid pixel format` | Set `pix_fmt` to `yuv420p` for maximum compatibility |
| Resolution not divisible by 2 | `width not divisible by 2` | Pad dimensions to even numbers: `ffmpeg -i input -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" output` |
| Corrupted source frames | `Invalid data found when processing input` | Regenerate source images; check intermediate PNG files with `file` command |

### Audio-video sync issues

**Symptoms:** Audio and video tracks drift apart; lip-sync errors.

**Remediation:**
- Use the `-async 1` flag to resample audio to match video frame rate
- Verify source audio duration matches video duration with `ffprobe`
- Check subtitle timing in SRT files — misaligned cues cause visible sync issues

### Hardware acceleration

For GPU-accelerated encoding (h264_nvenc, h264_vaapi, etc.):

```bash
# Check available encoders
ffmpeg -encoders | grep nvenc   # NVIDIA
ffmpeg -encoders | grep vaapi   # Intel/AMD VAAPI

# Use hardware encoder in pipeline (set via config)
export AUTOMEDIA_FFMPEG_ENCODER=h264_nvenc
```

**Common pitfall:** Hardware encoders produce larger files at the same CRF value. Adjust `-crf` (lower = better quality, 18-23 recommended for software, 15-20 for hardware).

---

## 8. Session Persistence FAQ

### What is a pipeline "session"?

A session is a single invocation of `run_full_pipeline()`. Each session creates a project directory with a unique `project_id` derived from the topic and brand.

### Can I resume a failed session?

Yes. Use the `resume_from` parameter to skip already-passed gates:

```python
result = run_full_pipeline(
    topic="AI tools",
    brand="my-brand",
    resume_from="G0",  # skip pre-gate, CW
)
```

The pipeline reads `pipeline_md5.json` from the project directory to verify previous gate outputs before resuming.

### What data persists between sessions?

| Data | Location | Persists? |
|------|----------|-----------|
| Gate outputs (drafts, video, subtitles) | `project_dir/` | ✅ Yes, until archived |
| MD5 checksums | `project_dir/pipeline_md5.json` | ✅ Yes |
| Project metadata | `project_dir/00_project_info.json` | ✅ Yes |
| Topic pool | `pool_db` (SQLite) | ✅ Yes |
| Encrypted credentials | `~/.automedia/credentials/` | ✅ Yes |
| Runtime logs | stdout/stderr | ❌ No (use `AUTOMEDIA_LOG_FORMAT=json` for persistent log aggregation) |
| Gate context (in-memory state) | RAM | ❌ No — must be regenerated on resume |

### How do I list all past sessions?

```bash
# List all projects with their status
automedia projects list

# Or scan a custom base directory
python -c "
from automedia.pipelines.runner import run_full_pipeline
# Re-run previous pipeline to check status
"
```

For MCP users, use `list_projects(base_dir="/path/to/projects")`.

### Can two sessions run concurrently?

Yes, but with caveats:

- **Same project directory:** Not recommended — concurrent writes to `pipeline_md5.json` and output files cause race conditions.
- **Different projects:** Fully safe. Each session creates a unique `project_id`.
- **Shared resources (LLM API, disk I/O):** Rate limiting applies. Use `AUTOMEDIA_LLM_RETRY_MAX` and `AUTOMEDIA_LLM_RETRY_DELAY` to handle API throttling gracefully.

---

## 9. MCP Rate Limit Handling

The MCP server interacts with external APIs (LLM providers, platform publish endpoints) that enforce rate limits. When limits are hit, the server returns errors or degrades functionality.

### LLM API rate limits

**Symptom:** Gates that call the LLM (CW, G0, G2, G3, V3, L4) fail with errors like "429 Too Many Requests", "Rate limit exceeded", or "Request throttled".

**Built-in retry:** The LLM client (`automedia/core/llm_client.py`) uses tenacity with exponential backoff by default. Configure retry behavior via environment variables:

```bash
# Maximum retry attempts (default: 3)
export AUTOMEDIA_LLM_RETRY_MAX=5

# Base delay in seconds between retries (default: 2.0)
export AUTOMEDIA_LLM_RETRY_DELAY=4.0
```

### MCP server tool rate limiting

The MCP server itself does not enforce per-tool rate limits, but the underlying operations may trigger provider limits.

**Best practices to avoid rate limits:**

1. **Batch operations:** When processing multiple projects, add a delay between calls:
   ```python
   import time
   for project in projects:
       run_full_pipeline(topic=project["topic"], brand=project["brand"])
       time.sleep(5)  # Respect API rate window
   ```

2. **Use text_only mode for testing:** Avoids video generation API calls during development iterations.

3. **Monitor with get_pipeline_progress:** If a gate is stuck for >5 minutes, it may be waiting for a rate-limited API retry.

### V1 Vision API degradation

When the Vision API is rate limited, V1 (Vision QA) automatically degrades to pixel-luminance analysis. The QA report includes "降级" (degraded) in the output. Accuracy drops but the pipeline is not blocked.

### Handling publish API rate limits

Platform adapters handle rate limits differently. Most use exponential backoff with jitter. If publishing fails with rate limit errors:

```bash
# Check account health
automedia account health <account_id>

# The session manager (automedia/accounts/session.py) provides:
# - TTL-aware token caching
# - Per-account concurrency locks
# - Rate-limit backoff with configurable max retries
```

---

## 10. Extended Environment Variable Reference

Beyond the core variables in AGENTS.md section 11, the following variables are available:

### LLM Retry Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `AUTOMEDIA_LLM_RETRY_MAX` | Max retry attempts for transient LLM failures | `3` |
| `AUTOMEDIA_LLM_RETRY_DELAY` | Base delay (seconds) between retries (exponential backoff) | `2.0` |

### Logging & Debugging

| Variable | Purpose | Default |
|----------|---------|---------|
| `AUTOMEDIA_LOG_LEVEL` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `AUTOMEDIA_LOG_FORMAT` | Output format: `console` (human) or `json` (log aggregators) | `console` |
| `AUTOMEDIA_DOTENV_PATH` | Custom path to `.env` file loaded on startup | (auto) |

### MCP Server Network Mode

| Variable | Purpose | Default |
|----------|---------|---------|
| `AUTOMEDIA_MCP_ALLOWLIST_PATH` | Path to MCP allowlist YAML file | `<module_dir>/mcp_allowlist.yaml` |

### Credential Store

| Variable | Purpose | Default |
|----------|---------|---------|
| `AUTOMEDIA_MASTER_KEY` | AES-256-GCM master key for encrypted credential storage | (required for accounts) |

### Pipeline Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `AUTOMEDIA_DEFAULT_BRAND` | Default brand for pipelines | `my-brand` |
| `AUTOMEDIA_PROJECTS_DIR` | Root directory for projects (overrides working directory) | (auto) |
| `AUTOMEDIA_POOL_DB` | Path to the topic pool SQLite database | `./data/pool.db` |

---

## 11. type:ignore Fix Principles

When working with Python type annotations in the AutoMedia codebase, you may encounter situations where type checkers (mypy, pyright) report errors that cannot be resolved through normal type annotations. The `# type: ignore` comment is used as a last resort.

### When to use type:ignore

| Situation | Acceptable? | Alternative |
|-----------|-------------|-------------|
| Third-party library lacks stubs | ✅ Yes | Prefer installing types package (`pip install types-xxx`) |
| Dynamic attribute from framework (e.g., Pydantic model_config) | ✅ Yes | Consider `cast()` as alternative |
| Known mypy false positive | ✅ Yes | Link to upstream issue in comment |
| Code is being refactored and types are in flux | ⚠️ Temporarily | Remove once refactoring is complete |
| Avoidable type error (missing annotation, Any propagation) | ❌ No | Fix the root cause instead |
| Duck-typed protocol match that mypy cannot infer | ✅ Yes | Prefer `Protocol` + `isinstance()` check |

### type:ignore annotation format

```python
# Full suppression — only use when you've exhausted alternatives
x = some_dynamic_value  # type: ignore[attr-defined]

# Specific error code is preferred over blanket suppression
y = cast(str, possibly_str)  # Prefer cast() over type: ignore
z = possibly_str  # type: ignore[assignment]  # only when cast() doesn't work
```

**Required format conventions:**
1. Always specify the error code (e.g., `[arg-type]`, `[return-value]`, `[attr-defined]`)
2. Never use bare `# type: ignore` without a code — it suppresses all errors on that line
3. Add a brief comment explaining *why* the suppression is necessary when the reason is not obvious
4. Use `cast()` from `typing` as a preferred alternative when the value's type is known

### Acceptable error codes

| Error code | Meaning | Example use case |
|-----------|---------|-----------------|
| `[arg-type]` | Argument type mismatch | Passing dynamic data to a strictly-typed function |
| `[return-value]` | Return type mismatch | Function must return a literal union at runtime |
| `[attr-defined]` | Attribute not recognized | Dynamic/hybrid objects or Pydantic model fields set at runtime |
| `[union-attr]` | Attribute not on all union members | Accessing attribute on a narrowable union type |
| `[assignment]` | Variable type mismatch | Assigning broader type to narrower variable |
| `[comparison-overlap]` | Types cannot overlap | Intentional type-heterogeneous comparison (test assertion) |
| `[assert-type]` | Assertion type mismatch | Testing runtime type behavior deliberately |

### Review checklist

Before adding `# type: ignore` to any file:

- [ ] Can I import a types package instead? (`pip install types-xxx`)
- [ ] Can I use `cast()` from `typing` instead?
- [ ] Can I use `assert isinstance(x, ExpectedType)` to narrow?
- [ ] Is this a mypy configuration issue? (check `pyproject.toml` config)
- [ ] Is this a legitimate dynamic pattern that type checkers cannot express?

---

For detailed gate failure mode troubleshooting, see `docs/runbook/gate-failure-modes.md`.
