---
title: Omni Triad Integration
description: OPP (extraction), OL (localization), ORF (format conversion) — the three companion tools of Omni Triad.
---

# Omni Triad Integration

## Overview

Omni Triad is a set of three companion tools that work alongside the
AutoMedia production pipeline as a **side-channel adapter**.  Omni is
**not embedded** in the main pipeline — it runs before (OPP document
extraction) and after (OL translation + ORF format re-flow) the core
gate chain, leaving the 20-gate production sequence unchanged.

| Tool | Package | Role |
|------|---------|------|
| **OPP** (Omni Pre-Processor) | `omni-pre-processor` | Document extraction — DOCX/PPTX/PDF → Markdown + XLIFF + skeleton |
| **OL** (Omni Localizer) | `omni-localizer` | Multi-language translation — Markdown/XLIFF → translated output |
| **ORF** (Omni Re-Formatter) | `omni-re-formatter` | Format backfill — translated XLIFF → DOCX/PPTX |

## MCP-CLI Naming Equivalences

The three Omni tools use **different names** in the MCP and CLI interfaces
even though they call the same underlying implementation:

| Function | CLI Command | MCP Tool |
|----------|-------------|----------|
| Document extraction | `automedia omni extract` | `extract_brief` |
| Content translation | `automedia omni translate` | `localize_content` |
| Format conversion | `automedia omni convert` | `format_output` |

These pairs are **semantically equivalent**.  The CLI and MCP interfaces
share the same Omni adapter layer (:class:`~automedia.omni.OPPAdapter`,
:class:`~automedia.omni.OLAdapter`, :class:`~automedia.omni.ORFAdapter`).

## Installation

```bash
# Minimal OPP-only environment
pip install automedia-pipeline[omni-core]

# Full Omni suite (includes ML dependencies for OL)
pip install automedia-pipeline[omni]

# Development
pip install -e ".[dev,omni]"
```

The optional dependency groups are:

| Extra | Includes |
|-------|----------|
| `[omni-core]` | `lxml`, `python-docx`, `python-pptx`, `openpyxl`, `pandas` |
| `[omni-pdf]` | `pymupdf` |
| `[omni-ml]` | `sentence-transformers`, `torch` |
| `[omni]` | All of the above + `omni-pre-processor`, `omni-localizer`, `omni-re-formatter` |

### Explicit Dependency Requirements

The `[omni]` extra installs three version-pinned packages, each wrapping a
different external tool:

| Python Import | PyPI Package | Version Constraint | Purpose |
|---------------|-------------|--------------------|---------|
| `opp` | `omni-pre-processor` | `>=0.9,<1.0` | Document extraction (OPP) |
| `ol_mcp` | `omni-localizer` | `>=0.7,<1.0` | Multi-language translation (OL) |
| `orf` | `omni-re-formatter` | `>=0.4,<1.0` | Format conversion (ORF) |

These constraints are defined in `pyproject.toml` under
`[project.optional-dependencies] omni` and are enforced at install time by
`pip`.

### Verification Script

A verification script is available to confirm all three packages are
installed and importable:

```bash
python scripts/verify-omni-packages.py
```

This script imports each package and exercises its basic API. Exit code
0 means all packages are functional; exit code 1 indicates missing or
broken packages.

### Graceful Degradation

All three adapters handle missing packages gracefully.  If an Omni package
is not installed (e.g. `pip install automedia-pipeline` without
`[omni]`), the corresponding adapter methods return empty results with
descriptive warnings instead of raising ``ImportError``:

- **OPPAdapter.extract()** → `ExtractionResult(md_content="", warnings=[...])`
- **OLAdapter.translate()** → `TranslationResult(translated_md="", warnings=[...])`
- **ORFAdapter.convert()** → `{"status": "error", "errors": [...], ...}`

This preserves the main pipeline: missing Omni packages never crash
production runs. Gate logs contain ``WARNING`` messages pointing users
to `pip install automedia-pipeline[omni]`.

## Three Integration Modes

The integration mode is set in `~/.automedia/omni_config.yaml`:

```yaml
integration_mode: proxy   # "proxy" | "parallel" | "sdk"
```

### 1. Proxy Mode (default)

AutoMedia's built-in MCP server internally instantiates the Omni adapters
and exposes three simplified tools. No additional servers needed.

```bash
# The three Omni MCP tools are always available on the AutoMedia MCP server:
#   extract_brief  — extract document content via OPP
#   localize_content — translate Markdown via OL
#   format_output   — convert Markdown to target format via ORF
```

Best for: single-user desktop, zero-config setup.

### 2. Parallel Mode

`automedia omni start-all` launches four independent MCP server processes:

| Server | Transport | Purpose |
|--------|-----------|---------|
| AutoMedia MCP | stdio | Core production pipeline |
| OPP MCP | stdio | Document extraction |
| OL MCP | stdio | Translation |
| ORF MCP | stdio | Format re-flow |

```bash
automedia omni start-all
# Each server can be connected independently by host agents.
# Stop gracefully with Ctrl+C or automedia omni stop-all.
```

Best for: multi-server setups, remote agent orchestration.

### 3. SDK Mode

Import adapters directly in Python scripts:

```python
from automedia.omni import OPPAdapter, OLAdapter, ORFAdapter

# OPP: extract document
adapter = OPPAdapter()
result = adapter.extract("brief.docx")
print(result.md_content)

# OL: translate
ol = OLAdapter()
translated = ol.translate(result.md_content, source_lang="zh", target_lang="en")

# ORF: backfill
orf = ORFAdapter()
output = orf.apply_md(translated.translated_md, "docx")
```

Best for: CI/CD pipelines, batch processing, custom automation.

## Configuration Files

### `~/.automedia/omni_config.yaml`

```yaml
integration_mode: proxy
opp:
  max_auto_extract_mb: 50
  supported_formats:
    - .docx
    - .pptx
    - .pdf
ol:
  config_path: ~/.automedia/omni/ol_config.yaml
orf:
  output_dir: ~/omni_outputs
```

### `~/.automedia/omni_allowlist.yaml`

Controls which directories Omni can read from and write to:

```yaml
allowed_paths:
  - ~/Documents/briefs
  - ~/projects/automedia
write_paths:
  - ~/Documents/outputs
```

File operations outside these paths raise `PermissionError`.

### `~/.automedia/omni/ol_config.yaml`

OL has an independent LLM pool configuration — it does **not** share
AutoMedia's `model_config.yaml`. Configure three LLM roles:

```yaml
llm_pool:
  translation:
    provider: openai
    model: gpt-4o-mini
    priority: 1
  judging:
    provider: openai
    model: gpt-4o-mini
    priority: 2
  restoration:
    provider: openai
    model: gpt-4o-mini
    priority: 3
```

Set API keys via environment variables:

| Variable | Purpose | Required |
|----------|---------|----------|
| `OL_TRANSLATION_API_KEY` | Translation LLM | Yes |
| `OL_JUDGING_API_KEY` | Judging LLM | No (falls back to translation) |
| `OL_RESTORATION_API_KEY` | Restoration LLM | No (falls back to translation) |

## Usage Guide

### Initialise Omni Configuration

```bash
automedia init --omni
```

Generates three template files: `omni_config.yaml`, `omni_allowlist.yaml`,
`ol_config.yaml`.

### Attach a Brief Manually (OPP fallback)

When OPP auto-extraction fails, inject a Markdown brief directly:

```bash
automedia pool attach-brief --topic 42 --md-file /path/to/brief.md
```

The content is stored in the topic's `research_data` field and used when
the pipeline runs.

### Localise a Project

Translate all Markdown drafts in a project to target languages:

```bash
automedia omni localize --project /path/to/project --target-langs en,ja
```

Output lands in `05_publish/en/`, `05_publish/ja/`.

### Convert Format

```bash
automedia omni format-output --input article.md --target-format docx
```

Produces a DOCX file with the converted content.

### Batch Ingest Documents

Extract all supported documents from a directory:

```bash
automedia omni ingest --dir /path/to/briefs/ --output-dir /path/to/output/
```

Extracted Markdown files are written to the output directory.

## Multi-Language Support

The pipeline can be configured per language via `brand-profile.yaml`:

```yaml
brand_name: MyBrand
languages:
  zh:
    tts_voice: zh-CN-YunxiNeural
    whisper_lang: zh
    cta_template: 立即体验 {brand}！
    blocked_words:
      - 竞品A
    date_format: YYYY-MM-DD
  en:
    tts_voice: en-US-JennyNeural
    whisper_lang: en
    cta_template: "Check out {brand} today!"
    blocked_words:
      - competitor
    date_format: MM/DD/YYYY
```

The pipeline's `run_full_pipeline()` accepts a `default_lang` parameter.
If not set, `zh` is used. The resolved configuration is injected into
`gate_context["lang_config"]` for downstream gates.

## Troubleshooting

### OPP Extraction Fails

**Symptoms**: `ExtractionResult` with empty `md_content`, error in
`manifest["error"]`.

**Root causes**: File corruption, unsupported format variant, OPP package
not installed.

**Resolution**:
1. Verify `pip list | grep omni-pre-processor` is installed.
2. Use `automedia pool attach-brief` to inject the brief content manually.
3. The pipeline will continue without OPP content — gate logs will contain
   a warning.

### OL Translation Fails

**Symptoms**: All LLM API calls fail → translated_md is empty.

**Root causes**: API key misconfigured, network unreachable, rate-limited.

**Resolution**:
1. Check `OL_TRANSLATION_API_KEY` environment variable is set.
2. Verify network connectivity to the LLM provider.
3. The original Markdown content is preserved as a degraded delivery.

### ORF Backfill Produces Broken Layout

**Symptoms**: Output DOCX has missing images, misaligned text.

**Root causes**: OPP skeleton extraction incomplete, XLIFF segment
mismatch, ORF version incompatibility.

**Resolution**:
1. Verify OPP produced a complete `skeleton.zip`.
2. Check `manifest.json` for image position metadata.
3. ORF has built-in layout overflow detection — check warnings.

### Path Allowlist Violation

**Symptoms**: `PermissionError` when calling any Omni adapter method.

**Resolution**: Edit `~/.automedia/omni_allowlist.yaml` to add the required
directory to `allowed_paths` or `write_paths`.

## OL Independent Configuration

OL (Omni Localizer) uses its own LLM configuration, separate from
AutoMedia's `model_config.yaml`. The configuration lives at
`~/.automedia/omni/ol_config.yaml` and defines an `llm_pool` with three
roles:

1. **translation** (priority 1): Primary LLM for translation.
2. **judging** (priority 2): Evaluates translation quality.
3. **restoration** (priority 3): Restores content from skeleton.

Each role can use a different provider/model. If a higher-priority LLM is
unavailable, OL falls back to the next priority.

OL does **not** use the AutoMedia `model_config.yaml` because translation
workloads have different requirements (lower latency tolerance, different
prompting strategy).

## Artifact Mapping

| Stage | Source | Destination |
|-------|--------|-------------|
| OPP | Document file | `research_data/{name}/{name}.md`, `.xlf`, `_manifest.json`, `.skeleton.zip` |
| OL | Markdown content | `05_publish/{lang}/{name}.md`, `.xlf` |
| ORF | XLIFF + skeleton | `05_publish/{lang}/deliverables/{name}.{format}` |

## Troubleshooting Checklist

```
□ pip install automedia-pipeline[omni] succeeded
□ automedia init --omni ran and created config files
□ ~/.automedia/omni_allowlist.yaml has correct paths
□ OL_TRANSLATION_API_KEY is set (if using OL)
□ automedia doctor shows no errors
□ Test: automedia omni ingest --dir /tmp/test --output-dir /tmp/out
□ Test: automedia pool attach-brief --topic 1 --md-file /tmp/test.md
```

## ASCII Architecture

```
                      ┌──────────────────────────────────────────────┐
                      │           AutoMedia Main Pipeline            │
                      │  (Omni is a side-channel, not embedded)      │
                      │                                              │
                      │  Topic → Research → 4-Modal Parallel → Gate  │
                      │    Chain → Publish                           │
                      │         |                      |              │
                      │    (OPP bypass A)         (OL+ORF bypass B)  │
                      └─────────┼──────────────────────┼─────────────┘
                                │                      │
                     ┌──────────▼──────────┐  ┌────────▼─────────────┐
                     │  Omni Adapter Layer  │  │  Omni Adapter Layer  │
                     │  (automedia/omni/)   │  │  (automedia/omni/)   │
                     │                     │  │                      │
                     │  OPPAdapter         │  │  OLAdapter           │
                     │  OLAdapter          │  │  ORFAdapter          │
                     │  ORFAdapter         │  │                      │
                     └─────────────────────┘  └──────────────────────┘
```