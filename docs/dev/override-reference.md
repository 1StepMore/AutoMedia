# Override System Reference

AutoMedia's 6-layer configuration hierarchy includes an overrides layer
that lets users customize Gate rules and LLM prompt templates at
global, platform, and brand scope.

## Directory Layout

```
~/.automedia/overrides/
├── rules/                    # Gate rule overrides (YAML)
│   ├── 001-brand-voice.yaml
│   ├── 002-platform-config.yaml
│   └── ...
└── prompts/                  # Prompt template overrides (Jinja2)
    ├── content_writer.j2     # Global override
    ├── wechat/               # Platform-scoped prompts
    │   └── content_writer.j2
    └── my-brand/             # Brand-scoped prompts
        └── content_writer.j2
```

## Prompt Template Reference

11 built-in Jinja2 templates are shipped with AutoMedia in
`src/automedia/prompts/`.  Each can be overridden by placing a `.j2` file
with the same stem in `~/.automedia/overrides/prompts/`.

| Template | Variables | Purpose |
|----------|-----------|---------|
| `brand_strategy` | `brand_name`, `industry`, `target_audience`, `context` | Generate brand positioning, audience analysis, and messaging via LLM |
| `content_quality` | `content`, `criteria`, `brand` | Score content quality against specified criteria (clarity, accuracy, brand voice, etc.) |
| `content_writer` | `topic`, `brand` | Write a full article draft for Chinese social media (WeChat, Xiaohongshu, Bilibili) |
| `copy_review_g2` | `content`, `brand_guidelines` | Evaluate tone, style, and brand compliance (Gate G2) |
| `fact_check_g0` | `content` | Verify factual claims against known knowledge (Gate G0) |
| `fact_check_g0_plausibility` | `content`, `topic` | Plausibility check when no source material is available (Gate G0) |
| `humanizer_g1` | `content` | Detect AI writing patterns, assess natural readability (Gate G1) |
| `image_prompt` | `topic`, `brand`, `image_index` | Generate Stable Diffusion / ComfyUI image prompts for cover art |
| `pipeline_strategy` | `topic`, `brand`, `mode`, `context` | Design content production strategy — structure, platform distribution, angles |
| `topic_research` | `category`, `count`, `trending_data` | Research trending topics within a category, recommend angles |
| `platforms/wechat/content_writer` | `topic`, `brand`, `tone`, `platform`, `audience`, `brand_guidelines` | WeChat-specific long-form article writer (platform-scoped override of `content_writer`) |

### Usage in Python

```python
from automedia.prompts import load_prompt

# Load with default (built-in) template
prompt = load_prompt("brand_strategy", brand_name="Acme", industry="SaaS")

# Load with platform-scoped resolution
prompt = load_prompt("content_writer", platform="wechat", topic="AI Trends", brand="Acme")
```

## Rule YAML Schema

Gate rule files live in `~/.automedia/overrides/rules/*.yaml`.  Each file
contains one or more rule dicts.

### Supported Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `gates` | `dict` | Yes | Gate modifier configuration |
| `gates.include` | `list[str]` | No | Gates to add to the pipeline for this platform |
| `gates.exclude` | `list[str]` | No | Gates to remove from the pipeline for this platform |
| `gates.override_failure_mode` | `dict[str, str]` | No | Override failure mode per gate (`"stop"` or `"rewrite"`) |
| `brand` | `str` | No | Brand scope (rule applies only to this brand when present) |
| `platform` | `str` | No | Platform scope (rule applies only to this platform when present) |
| `engines` | `dict` | No | Engine configuration overrides |
| `engines.tts` | `dict` | No | Text-to-speech engine settings |
| `engines.asr` | `dict` | No | Automatic speech recognition settings |
| `engines.image` | `dict` | No | Image generation engine settings |
| `engines.video` | `dict` | No | Video engine settings |
| `media_specs` | `dict` | No | Per-platform media resolution specs (width, height, aspect ratio) |

### Example Rule

```yaml
# ~/.automedia/overrides/rules/wechat-gate-config.yaml
brand: my-brand
platform: wechat
gates:
  include:
    - G6
  exclude:
    - V3
  override_failure_mode:
    G0: rewrite
engines:
  tts:
    voice: zh-CN-XiaoxiaoNeural
    rate: +10%
media_specs:
  wechat:
    width: 900
    height: 600
    aspect_ratio: "3:2"
```

## Resolution Order

Prompt templates and rules follow a layered resolution from most specific
to most general:

### Prompt Resolution

| Priority | Scope | Path |
|----------|-------|------|
| 1 (highest) | Brand | `~/.automedia/overrides/prompts/<brand>/<name>.j2` |
| 2 | Platform | `~/.automedia/overrides/prompts/<platform>/<name>.j2` |
| 3 | Global | `~/.automedia/overrides/prompts/<name>.j2` |
| 4 (fallback) | Built-in | `src/automedia/prompts/<name>.j2` |

### Rule Resolution

| Priority | Scope | Path |
|----------|-------|------|
| 1 (highest) | Brand + Platform | `rules/<file>.yaml` with `brand` AND `platform` matching |
| 2 | Brand only | `rules/<file>.yaml` with `brand` matching |
| 3 | Platform only | `rules/<file>.yaml` with `platform` matching |
| 4 (fallback) | Global | `rules/<file>.yaml` with no `brand` or `platform` key |

## File Naming Conventions

- **Rule files**: `~/.automedia/overrides/rules/<descriptive-name>.yaml`
  — use kebab-case or numeric prefixes for ordering
- **Prompt overrides**: `~/.automedia/overrides/prompts/<name>.j2`
  — the stem must match the built-in template name exactly
- **Platform-scoped prompts**: `~/.automedia/overrides/prompts/<platform>/<name>.j2`
  — platform name in lowercase
- **Brand-scoped prompts**: `~/.automedia/overrides/prompts/<brand>/<name>.j2`
  — brand name in lowercase

## Concrete Examples

### Example 1: Customize the Content Writer Prompt

Create a global override that changes the content writer style:

```bash
mkdir -p ~/.automedia/overrides/prompts
```

```jinja2
{# ~/.automedia/overrides/prompts/content_writer.j2 #}
You are a technical content writer. Write a detailed, research-backed
article in Simplified Chinese about {{ topic }} for {{ brand }}.

Requirements:
- Start with a data-driven hook (statistic or research finding)
- Use H2 subheadings every 300 characters
- Include at least one comparison table
- End with a "Key Takeaways" bullet list
- 1000-2000 characters
```

### Example 2: Platform-Specific Prompt Override

Override the content writer only for the WeChat platform:

```bash
mkdir -p ~/.automedia/overrides/prompts/wechat
```

```jinja2
{# ~/.automedia/overrides/prompts/wechat/content_writer.j2 #}
You are a senior WeChat Official Account editor. Write an authoritative
long-form article about {{ topic }} for {{ brand }} in Simplified Chinese.

Requirements:
- 2500-4000 characters
- Formal but engaging tone
- Open with a provocative question
- Use blockquotes for expert opinions
- Suggest image placements with [IMAGE: description]
- End with an engagement CTA (comment/share/follow)
```

### Example 3: Gate Rule Override

Override the fact-check gate to rewrite instead of stop, and add a
custom gate for the WeChat platform:

```yaml
# ~/.automedia/overrides/rules/wechat-overrides.yaml
platform: wechat
gates:
  override_failure_mode:
    G0: rewrite      # Retry fact-check instead of halting pipeline
  include:
    - G6             # Add a custom G6 gate
```

### Example 4: Brand + Platform Rule

Scoped to both brand and platform — applies only when running brand
"acme" on platform "xiaohongshu":

```yaml
# ~/.automedia/overrides/rules/acme-xhs.yaml
brand: acme
platform: xiaohongshu
gates:
  exclude:
    - V0
    - V1
    - V2
media_specs:
  xiaohongshu:
    width: 1242
    height: 1660
    aspect_ratio: "3:4"
```

### Example 5: Engine Config Override

Customize TTS voice and image generation model:

```yaml
# ~/.automedia/overrides/rules/engine-config.yaml
engines:
  tts:
    default: edge-tts
    voice: zh-CN-YunxiNeural
    rate: +5%
  image:
    default: comfyui
    model: sdxl-turbo
    steps: 4
```

## MCP Tool

Use the `list_overridable_templates` MCP tool to inspect all overridable
templates at runtime:

```python
# Via MCP
result = await client.call_tool("list_overridable_templates")
# Returns: {"templates": [...], "count": N, "overrides_dir": "..."}
```

Each template entry contains:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Template stem name (e.g. `"content_writer"`) |
| `path` | `str` | Built-in file path (empty if not found) |
| `variables` | `list[str]` | Known Jinja2 template variables |
| `purpose` | `str` | Human-readable description |
| `overridden` | `bool` | Whether a global override file exists |
| `override_path` | `str` | Path to the global override file (empty if none) |
| `platform_overrides` | `dict[str, str]` | Platform-scoped overrides `{platform: path}` |

## Implementation Details

- **Prompt loader**: `automedia.prompts.load_prompt()` in
  `src/automedia/prompts/__init__.py`
- **Override loader**: `automedia.core.overrides.OverridesLoader` in
  `src/automedia/core/overrides.py`
- **Rule loading**: `OverridesLoader.load_rules(brand=None)`
- **Prompt loading**: `OverridesLoader.load_prompts(brand=None, platform=None)`
- **MCP tool**: `list_overridable_templates` in `src/automedia/mcp/tools.py`
- **Config merge**: 6-layer hierarchy in `src/automedia/core/config_loader.py`
