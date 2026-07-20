---
title: API Reference
description: Python SDK API documentation — run_full_pipeline, GateEngine, PipelineResult, and all public interfaces.
---

# API Reference

## `run_full_pipeline()`

Core entry function, executes the full content production pipeline.

```python
from automedia import run_full_pipeline

result = run_full_pipeline(
    topic="AI Video Generation Tool Comparison",
    brand="my-brand",
    hooks=None,
    mode="auto",
    resume_from=None,
    config_dir=None,
    tenant_id="default",
    workflow=None,             # Workflow name from workflows.yaml
    director=False,            # Enable director mode (HITL gate approval)
    platform=None,             # Target platform for media spec resolution
)
```

### Parameters

| Parameter | Type | Default | Description |
|------|------|--------|------|
| `topic` | `str` | (required) | Content topic/theme |
| `brand` | `str` | (required) | Brand identifier, corresponds to brand-profile.yaml |
| `hooks` | `list[GateHook] \| None` | `None` | List of GateHook observers |
| `mode` | `str` | `"auto"` | Run mode: `auto`, `text_only`, `text_with_cover`, `video_only`, `qa_only`, `image-carousel`, `social-thread`, `short-video`, `repurpose` |
| `resume_from` | `str \| None` | `None` | Resume from a specific Gate (skip preceding Gates) |
| `config_dir` | `str \| None` | `None` | Path to project `.automedia/` config directory |
| `tenant_id` | `str` | `"default"` | Tenant/namespace identifier |
| `workflow` | `str \| None` | `None` | Workflow name from `workflows.yaml` — merges workflow config into pipeline |
| `director` | `bool` | `False` | Enable director mode — pauses at H0 gate for human approval via MCP approve/reject tools |
| `platform` | `str \| None` | `None` | Target platform name for media spec resolution and prompt scoping |

### mode Options

| mode | Executed Gates | Use Case |
|------|-----------|----------|
| `auto` | pre-gate + CW + G0-G6 + V0-V7 + H0 + L1-L4 | Full pipeline production |
| `text_only` | CW + G0-G6 + L1-L4 | Text-only production |
| `text_with_cover` | CW + G0-G6 + V0 + L1-L4 | Text plus cover image |
| `video_only` | V0-V7 + H0 + L1-L4 | Video-only production |
| `image-carousel` | CW + G0-G6 + V0 + V6 + L1-L4 | Carousel image output |
| `social-thread` | CW + G0-G6 + L1-L4 | Thread-style social posts |
| `short-video` | CW + G0-G6 + V0-V6 + H0 + L1-L4 | Short-form video |
| `qa_only` | G0 + G2 + G3 + V1 + V6 | Quality review only |
| `repurpose` | CW + G0-G6 + V0-V7 + H0 + L1-L4 + P1-P4 | Full pipeline + deep platform repurpose |

### Return Value

Returns a `PipelineResult` object.

## PipelineResult

```python
@dataclass
class PipelineResult:
    status: Literal["success", "failed", "partial"]
    project_id: str
    project_dir: str
    topic: str
    brand: str
    assets: list[AssetInfo]
    gates_log: list[GateLogEntry]
    start_time: float            # time.monotonic() start value
    end_time: float              # time.monotonic() end value
    total_duration_s: float      # Total duration (seconds)
    error: str | None = None
```

### Field Descriptions

| Field | Type | Description |
|------|------|------|
| `status` | `str` | `"success"` all passed, `"partial"` partial failure but not blocking, `"failed"` abnormal termination |
| `project_id` | `str` | 12-character hex unique ID |
| `project_dir` | `str` | Absolute path to project root directory |
| `assets` | `list[AssetInfo]` | List of output assets |
| `gates_log` | `list[GateLogEntry]` | Execution log for each Gate |
| `error` | `str \| None` | Error info (only populated when status="failed") |

## AssetInfo

```python
@dataclass
class AssetInfo:
    type: str            # Asset type (e.g. "video", "article", "image", "audio")
    path: str            # Asset file path
    platform: str = ""   # Target platform (e.g. "wechat")
    md5: str = ""        # File MD5 hash
```

## GateLogEntry

```python
@dataclass
class GateLogEntry:
    gate_name: str                     # Gate name (e.g. "G0", "V1")
    status: Literal["passed", "failed", "error"]  # Execution status
    duration_s: float                  # Execution duration (seconds)
    error: str | None = None           # Error message
```

## GateHook Protocol

```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class GateHook(Protocol):
    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None: ...
    def after_gate(self, gate_name: str, context: dict[str, Any], result: dict[str, Any]) -> None: ...
    def on_gate_failed(self, gate_name: str, context: dict[str, Any], error: Exception) -> None: ...
```

All three methods are read-only observers and must return `None`. They must not modify Gate behavior or block execution.

### `before_gate(gate_name, context)`

Called before Gate execution. `context` contains an immutable snapshot of topic, brand, project directory, etc.

### `after_gate(gate_name, context, result)`

Called after Gate execution succeeds. `result` contains pass/fail status, duration, and key metrics.

### `on_gate_failed(gate_name, context, error)`

Called when a Gate raises an exception. Note that even if the hook is called, the Pipeline will still decide whether to stop based on the failure_mode.

### GateObserver

Convenient default empty implementation for subclassing:

```python
from automedia.hooks.protocol import GateObserver

class MyHook(GateObserver):
    def after_gate(self, gate_name, context, result):
        print(f"Gate {gate_name} completed: {result.get('passed')}")
```

### MD5 Tracker Hook

Built-in MD5 tracking Hook:

```python
from automedia.hooks.md5_tracker import record_md5, verify_md5, get_pipeline_md5

# Record file MD5
record_md5(project_dir, "G0", "/path/to/output.txt")

# Verify file integrity
is_valid = verify_md5(project_dir, "G0", "/path/to/output.txt")

# Read all MD5 records
all_md5 = get_pipeline_md5(project_dir)
```

## Project

```python
from automedia.core.project import Project

project = Project.init(
    topic_slug="AI Video Generation Tool Comparison",
    brand="my-brand",
    tenant_id="default",
    base_dir=None,   # Defaults to os.getcwd()
)
```

### `Project.init()` Parameters

| Parameter | Type | Default | Description |
|------|------|--------|------|
| `topic_slug` | `str` | (required) | Original topic string, auto slugified into directory name |
| `brand` | `str` | (required) | Brand identifier, validated for path safety |
| `tenant_id` | `str` | `"default"` | Tenant identifier |
| `base_dir` | `str \| None` | `None` | Parent directory for projects, defaults to current working directory |

### Created Directory Structure

```
{date}_{slug}/
  00_project_info.json    # Project metadata
  01_content/drafts/      # Content drafts
  02_images/cover/        # Cover images
  03_video/               # Video files
  03_subtitle/            # Subtitle files
  04_review/              # Review records
  05_publish/             # Published outputs
```

### `Project` Fields

| Field | Type | Description |
|------|------|------|
| `project_id` | `str` | uuid4().hex[:12] short unique ID |
| `project_dir` | `str` | Absolute path to project root directory |
| `topic` | `str` | Original topic |
| `brand` | `str` | Brand identifier |
| `tenant_id` | `str` | Tenant identifier |
| `created_at` | `str` | ISO-8601 creation timestamp |

## `load_config()`

```python
from automedia.core.config_loader import load_config

config = load_config(
    config_dir=None,   # Project .automedia/ path, defaults to $CWD/.automedia/
    overrides=None,    # Highest priority key-value pairs
)
```

Returns the fully merged config dictionary, with six priority levels (lowest to highest):

1. Built-in `automedia/manifests/defaults.yaml`
2. Project `.automedia/` directory YAML
3. User `~/.automedia/` directory YAML
4. `~/.automedia/overrides/rules/*.yaml`
5. `~/.automedia/overrides/prompts/*.j2`
6. `AUTOMEDIA_*` environment variables + `overrides` parameter

## BaseGate

```python
from automedia.gates.base import BaseGate

class MyGate(BaseGate):
    _gate_name = "GX"           # Unique Gate identifier
    _failure_mode = "stop"      # "stop" blocks pipeline, "retry" continues

    def execute(self, gate_context: dict) -> dict:
        # gate_context contains topic, brand, project_dir, config, etc.
        return {"passed": True, "gate": self._gate_name}
```

## GateEngine

```python
from automedia.pipelines.gate_engine import GateEngine

# Constructor
engine = GateEngine(gates, hooks=hooks)

# Execute all Gates
success, results = engine.run(gate_context)

# Execute and return all results (even if stopped early)
all_results = engine.run_with_results(gate_context)
```

## GateRegistry

```python
from automedia.gates.base import _registry

# Registered Gates are automatically registered via __init_subclass__
_registry.list()              # Returns list of all Gate names
_registry.get("G0")           # Get Gate class
"G0" in _registry             # Check if registered
```

## AdapterRegistry

```python
from automedia.adapters.registry import AdapterRegistry

AdapterRegistry.register(WechatPublisher)
cls = AdapterRegistry.get("wechat")
AdapterRegistry.list()        # List all registered platforms
```

## Doctor

```python
from automedia.core.doctor import Doctor

doctor = Doctor()
results = doctor.check_dependencies()
# Returns [{"name": "python", "installed": True, "version": "...", "path": "..."}, ...]
```

## Account Management (PRD-4)

### `AccountRegistry`

```python
from automedia.accounts.registry import AccountRegistry

registry = AccountRegistry()

# Register a new account
meta = registry.register(
    platform="wechat",
    credentials={"cookie": "sessionid=abc123"},
    label="Main WeChat",
    auth_type="cookie",
)
# Returns: {"account_id": "acc_wechat_a1b2c3d4", "platform": "wechat", ...}

# List accounts
all_accounts = registry.list()
wechat_accounts = registry.list(platform="wechat")

# Get single account
info = registry.get("acc_wechat_a1b2c3d4")

# Delete account
registry.delete("acc_wechat_a1b2c3d4")
```

### `AccountStore`

```python
from automedia.accounts.store import AccountStore

store = AccountStore()

# Store credentials (encrypted with AES-256-GCM)
store.put("acc_wechat_a1b2c3d4", {"cookie": "sessionid=abc123"}, auth_type="cookie", label="")

# Retrieve credentials
creds = store.get("acc_wechat_a1b2c3d4")

# List all stored account IDs
ids = store.list()

# Delete
store.delete("acc_wechat_a1b2c3d4")
```

### `AuthFlowEngine`

```python
from automedia.accounts.auth import AuthFlowEngine

engine = AuthFlowEngine(store)

# Authenticate using stored credentials
result = engine.authenticate("acc_wechat_a1b2c3d4")
# Returns AuthResult with access_token, expires_at, etc.

# Supported auth flows:
# - CookieAuthFlow: Cookie-based authentication
# - APIKeyAuthFlow: API key authentication
# - OAuth2ClientCredentialsFlow: OAuth2 client credentials grant
# - OAuth2AuthCodeFlow: OAuth2 authorization code (with localhost server)
```

### `SessionManager`

```python
from automedia.accounts.session import SessionManager

session_mgr = SessionManager(store)

# Get a cached session (auto-refreshes if expired)
session = session_mgr.get_session("acc_wechat_a1b2c3d4")

# Invalidate a session
session_mgr.invalidate("acc_wechat_a1b2c3d4")
```

### Credential Loading (Backward Compatible)

```python
from automedia.core.credential_loader import load_credential_with_account_fallback

# Tries PRD-4 account store first, falls back to legacy credential loading
creds = load_credential_with_account_fallback(
    account_id="acc_wechat_a1b2c3d4",
    platform="wechat",
    env_var="WECHAT_COOKIE",
)
```

## `sanitize_path()`

```python
from automedia.core.project import sanitize_path

safe_path = sanitize_path("/valid/path")  # Validate and normalize path
# Rejects "..", "~", "//" patterns
```
