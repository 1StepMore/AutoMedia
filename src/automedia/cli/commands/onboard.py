"""``automedia onboard`` — comprehensive onboarding wizard.

Walks through ALL customizable AutoMedia settings:
1. LLM provider + API key
2. Brand profile (brand_name, CTA, languages, blocked words)
3. Pipeline mode + enabled tracks
4. Platform adapters (enable/disable)
5. HITL preset (automated / semi-automated)
6. Cron jobs (enable/disable, schedule)
7. Omni integration (optional)
8. Prompt customization (copy defaults to overrides dir)

Each step can be re-run individually with ``--step <name>``.
All config files are plain YAML — agents can read/write them directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import typer
import yaml

from automedia.cli.output import OutputMode, get_output_mode, output_error, output_text
from automedia.core.config_loader import load_config

_USER_CFG_DIR = Path.home() / ".automedia"
_MANIFESTS_DIR = Path(__file__).resolve().parent.parent.parent / "manifests"
_PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent / "pipelines"
_CRON_DIR = Path(__file__).resolve().parent.parent.parent / "cron"

app = typer.Typer(name="onboard", help="Comprehensive onboarding wizard.")

_STEPS = [
    "llm",
    "brand",
    "pipeline",
    "platforms",
    "hitl",
    "cron",
    "omni",
    "prompts",
    "all",
]


def _print_header(title: str) -> None:
    typer.echo("")
    typer.echo("=" * 50)
    typer.echo(f"  {title}")
    typer.echo("=" * 50)


def _print_success(path: str) -> None:
    typer.secho(f"  ✅ Written: {path}", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# Step 1: LLM
# ---------------------------------------------------------------------------


def _step_llm() -> None:
    _print_header("Step 1/8: LLM Provider")

    cfg_path = _USER_CFG_DIR / "model_config.yaml"
    existing: dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}

    llm = existing.get("llm", {}).get("text_generation", {})

    provider = typer.prompt("LLM provider", default=llm.get("provider", "openai"))
    model = typer.prompt("Model", default=llm.get("model", "gpt-4o-mini"))
    api_key = typer.prompt(
        "API key (leave blank to use env AUTOMEDIA_LLM_API_KEY)", default="", hide_input=True
    )
    base_url = typer.prompt("API base URL (optional)", default=llm.get("base_url", ""))
    temperature = typer.prompt("Temperature (0.0-2.0)", default=llm.get("temperature", 0.7))
    max_tokens = typer.prompt("Max tokens", default=llm.get("max_tokens", 2048))

    data: dict[str, Any] = {
        "llm": {
            "text_generation": {
                "provider": provider,
                "model": model,
                "temperature": float(temperature),
                "max_tokens": int(max_tokens),
            },
        },
    }
    if api_key:
        data["llm"]["text_generation"]["api_key"] = api_key
    if base_url:
        data["llm"]["text_generation"]["base_url"] = base_url

    _USER_CFG_DIR.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    os.chmod(cfg_path, 0o600)
    _print_success(str(cfg_path))
    typer.echo("  Tip: You can also set AUTOMEDIA_LLM_API_KEY env var instead.")


# ---------------------------------------------------------------------------
# Step 2: Brand Profile
# ---------------------------------------------------------------------------


def _step_brand() -> None:
    _print_header("Step 2/8: Brand Profile")

    brand_path = _USER_CFG_DIR / "brand-profile.yaml"
    existing: dict[str, Any] = {}
    if brand_path.exists():
        with open(brand_path, encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}

    brand_name = typer.prompt("Brand name", default=existing.get("brand_name", "MyBrand"))
    tone = typer.prompt(
        "Tone (professional/casual/humorous)", default=existing.get("tone", "professional")
    )
    cta_raw = typer.prompt(
        "CTA principles (comma-separated)",
        default=", ".join(
            existing.get("cta_principles", ["Include clear CTA", "Use action verbs"])
        ),
    )
    blocked_raw = typer.prompt(
        "Blocked words (comma-separated)", default=", ".join(existing.get("blocked_words", []))
    )

    data = {
        "brand_name": brand_name,
        "tone": tone,
        "cta_principles": [s.strip() for s in cta_raw.split(",") if s.strip()],
        "blocked_words": [s.strip() for s in blocked_raw.split(",") if s.strip()],
    }

    # Languages
    typer.echo("\n  Language configuration (optional). Press Enter to skip.")
    langs_raw = typer.prompt("Language codes (comma-separated, e.g. zh,en,ja)", default="zh")
    langs = [s.strip() for s in langs_raw.split(",") if s.strip()]
    if langs:
        lang_config: dict[str, dict] = {}
        for lang in langs:
            typer.echo(f"\n  Configuring language: {lang}")
            tts = typer.prompt(f"  TTS voice for {lang}", default=_default_tts(lang))
            whisper = typer.prompt(f"  Whisper language for {lang}", default=_default_whisper(lang))
            cta = typer.prompt(f"  CTA template for {lang} (optional)", default="")
            lang_config[lang] = {
                "tts_voice": tts,
                "whisper_lang": whisper,
            }
            if cta:
                lang_config[lang]["cta_template"] = cta
        data["languages"] = lang_config

    _USER_CFG_DIR.mkdir(parents=True, exist_ok=True)
    with open(brand_path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    _print_success(str(brand_path))


def _default_tts(lang: str) -> str:
    voices = {
        "zh": "zh-CN-YunxiNeural",
        "en": "en-US-JennyNeural",
        "ja": "ja-JP-NanamiNeural",
        "ko": "ko-KR-SunHiNeural",
    }
    return voices.get(lang, f"{lang}-Neural")


def _default_whisper(lang: str) -> str:
    whispers = {"zh": "zh", "en": "en", "ja": "ja", "ko": "ko"}
    return whispers.get(lang, lang)


# ---------------------------------------------------------------------------
# Step 3: Pipeline
# ---------------------------------------------------------------------------


def _step_pipeline() -> None:
    _print_header("Step 3/8: Pipeline Configuration")

    existing = load_config()
    pipeline = existing.get("pipeline", {})

    mode = typer.prompt("Default mode (auto / text_only / video_only / qa_only)", default="auto")
    text_enabled = typer.prompt(
        "Enable text track", default=pipeline.get("text", {}).get("enabled", True)
    )
    image_enabled = typer.prompt(
        "Enable image track", default=pipeline.get("image", {}).get("enabled", True)
    )
    video_enabled = typer.prompt(
        "Enable video track", default=pipeline.get("video", {}).get("enabled", True)
    )
    audio_enabled = typer.prompt(
        "Enable audio track", default=pipeline.get("audio", {}).get("enabled", True)
    )

    data = {
        "pipeline": {
            "mode": mode,
            "text": {"enabled": text_enabled},
            "image": {"enabled": image_enabled},
            "video": {"enabled": video_enabled},
            "audio": {"enabled": audio_enabled},
        },
    }

    cfg_path = _USER_CFG_DIR / "config.yaml"
    _USER_CFG_DIR.mkdir(parents=True, exist_ok=True)
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as fh:
            merged = yaml.safe_load(fh) or {}
        merged["pipeline"] = data["pipeline"]
        merged["mode"] = mode
        data = merged

    with open(cfg_path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    _print_success(str(cfg_path))


# ---------------------------------------------------------------------------
# Step 4: Platforms
# ---------------------------------------------------------------------------


def _step_platforms() -> None:
    _print_header("Step 4/8: Platform Adapters")

    cfg_path = _USER_CFG_DIR / "config.yaml"
    existing: dict[str, Any] = {}
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}

    platforms = existing.get("platforms", {})
    defaults = {
        "wechat": True,
        "zhihu": True,
        "xiaohongshu": True,
        "youtube": False,
        "tiktok": False,
        "twitter": False,
    }

    platform_config: dict[str, dict[str, bool]] = {}
    for name, default_enabled in defaults.items():
        current = platforms.get(name, {}).get("enabled", default_enabled)
        enabled = typer.prompt(f"  Enable {name}", default=current)
        platform_config[name] = {"enabled": enabled}

    existing["platforms"] = platform_config
    _USER_CFG_DIR.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as fh:
        yaml.dump(existing, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
    _print_success(str(cfg_path))
    typer.echo("  Tip: Add custom platform adapters via 'automedia adapter register'.")


# ---------------------------------------------------------------------------
# Step 5: HITL Preset
# ---------------------------------------------------------------------------


def _step_hitl() -> None:
    _print_header("Step 5/8: HITL (Human In The Loop)")

    typer.echo("  Choose how Decision Layer nodes execute:")
    typer.echo("  1 = automated — all nodes run as AI agent (fastest)")
    typer.echo("  2 = semi-automated — decision nodes need human approval (recommended)")
    choice = typer.prompt("Your choice", default=2)

    preset = "automated" if choice == 1 else "semi-automated"
    hitl_path = _USER_CFG_DIR / "hitl" / "active_preset.yaml"
    hitl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(hitl_path, "w", encoding="utf-8") as fh:
        yaml.dump({"preset": preset}, fh)
    _print_success(str(hitl_path))
    typer.echo(f"  Active preset: {preset}")
    typer.echo("  Change later via: automedia hitl preset --set <name>")


# ---------------------------------------------------------------------------
# Step 6: Cron
# ---------------------------------------------------------------------------


def _step_cron() -> None:
    _print_header("Step 6/8: Scheduled Jobs")

    jobs_path = _CRON_DIR / "jobs.yaml"
    if not jobs_path.exists():
        typer.echo("  No cron jobs template found. Skipping.")
        return

    with open(jobs_path, encoding="utf-8") as fh:
        jobs_data = yaml.safe_load(fh) or {}

    jobs = jobs_data.get("jobs", [])
    enabled_jobs: list[dict[str, Any]] = []
    for job in jobs:
        name = job.get("name", "unknown")
        typer.echo(f"\n  Job: {name} ({job.get('description', '')})")
        enable = typer.prompt("  Enable", default=True)
        if enable:
            schedule = typer.prompt("  Cron schedule", default=job.get("schedule", "0 8 * * *"))
            job["schedule"] = schedule
            enabled_jobs.append(job)

    override_path = _USER_CFG_DIR / "cron" / "overrides.yaml"
    override_path.parent.mkdir(parents=True, exist_ok=True)
    with open(override_path, "w", encoding="utf-8") as fh:
        yaml.dump({"jobs": enabled_jobs}, fh, default_flow_style=False)
    _print_success(str(override_path))


# ---------------------------------------------------------------------------
# Step 7: Omni Integration
# ---------------------------------------------------------------------------


def _step_omni() -> None:
    _print_header("Step 7/8: Omni Document Localization (optional)")

    enable = typer.prompt(
        "Enable Omni document processing (requires OPP/OL/ORF packages)", default=False
    )
    if not enable:
        typer.echo("  Omni disabled. Enable later via: automedia init --omni")
        return

    # Re-use existing omni init logic
    from automedia.cli.commands.init_cmd import _init_omni

    _init_omni()


# ---------------------------------------------------------------------------
# Step 8: Prompts (copy defaults to overrides)
# ---------------------------------------------------------------------------


def _step_prompts() -> None:
    _print_header("Step 8/8: Prompt Customization")

    prompts_dir = _USER_CFG_DIR / "overrides" / "prompts"
    rules_dir = _USER_CFG_DIR / "overrides" / "rules"

    if prompts_dir.exists() and any(prompts_dir.iterdir()):
        typer.echo(f"  Override prompts already exist at {prompts_dir}")
        overwrite = typer.prompt("  Overwrite with defaults?", default=False)
        if not overwrite:
            typer.echo("  Keeping existing custom prompts.")
            return

    copy = typer.prompt(
        "  Copy default prompts to overrides directory for customization?", default=True
    )
    if not copy:
        typer.echo("  Skipping. You can add .j2 files later to ~/.automedia/overrides/prompts/")
        return

    prompts_dir.mkdir(parents=True, exist_ok=True)
    rules_dir.mkdir(parents=True, exist_ok=True)

    # Create example prompt template
    example = prompts_dir / "content_writer.j2"
    if not example.exists():
        example.write_text(
            'Write a {{ tone }} article about "{{ topic }}" for {{ platform }}.\n'
            "Brand: {{ brand_name }}\n"
            "Length: approximately 800 words.\n"
            "Include a strong call-to-action at the end.\n",
            encoding="utf-8",
        )
        _print_success(str(example))

    # Create example rules file
    example_rules = rules_dir / "custom_gate.yaml"
    if not example_rules.exists():
        example_rules.write_text(
            "# Additional gate checks\n"
            "# These rules are merged into the existing gate logic.\n"
            "extra_checks:\n"
            "  brand_name_in_title: true\n",
            encoding="utf-8",
        )
        _print_success(str(example_rules))

    typer.echo("  📝 Edit .j2 files in ~/.automedia/overrides/prompts/ to customize LLM prompts.")
    typer.echo("  📝 Add .yaml files to ~/.automedia/overrides/rules/ to add gate rules.")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


@app.callback()
def main() -> None:
    """Comprehensive AutoMedia onboarding wizard."""


@app.command()
def start(
    step: str = typer.Option(
        "all",
        "--step",
        "-s",
        help="Run a specific step: llm, brand, pipeline, platforms, hitl, cron, omni, prompts, all",
    ),
) -> None:
    """Run the onboarding wizard for one or all steps."""
    steps = _STEPS if step == "all" else [step]

    if step not in _STEPS:
        output_error(f"Unknown step: {step!r}. Choose from: {', '.join(_STEPS)}")

    if get_output_mode() == OutputMode.JSON:
        output_error(
            "Interactive onboarding not supported in --json mode. "
            "Use 'automedia init --template minimal' for non-interactive setup."
        )

    typer.echo("")
    typer.echo("╔══════════════════════════════════════════════════╗")
    typer.echo("║     AutoMedia Onboarding Wizard                 ║")
    typer.echo("║     Press Enter to accept defaults               ║")
    typer.echo("╚══════════════════════════════════════════════════╝")

    if "llm" in steps:
        _step_llm()
    if "brand" in steps:
        _step_brand()
    if "pipeline" in steps:
        _step_pipeline()
    if "platforms" in steps:
        _step_platforms()
    if "hitl" in steps:
        _step_hitl()
    if "cron" in steps:
        _step_cron()
    if "omni" in steps:
        _step_omni()
    if "prompts" in steps:
        _step_prompts()

    if step == "all":
        typer.echo("")
        typer.echo("=" * 50)
        typer.secho("  ✅ Onboarding complete!", fg=typer.colors.GREEN)
        typer.echo("  All config files written to ~/.automedia/")
        typer.echo("  You can re-run any step: automedia onboard --step <name>")
        typer.echo("  Or edit YAML files directly — agents can read/write them.")
        typer.echo("=" * 50)


@app.command()
def status() -> None:
    """Show current onboarding status — which configs are set."""
    checks = [
        ("LLM config", _USER_CFG_DIR / "model_config.yaml"),
        ("Brand profile", _USER_CFG_DIR / "brand-profile.yaml"),
        ("Pipeline config", _USER_CFG_DIR / "config.yaml"),
        (
            "Platform config",
            _USER_CFG_DIR / "config.yaml"
            if (_USER_CFG_DIR / "config.yaml").exists()
            and "platforms" in (_USER_CFG_DIR / "config.yaml").read_text()
            else None,
        ),
        ("HITL preset", _USER_CFG_DIR / "hitl" / "active_preset.yaml"),
        ("Cron overrides", _USER_CFG_DIR / "cron" / "overrides.yaml"),
        ("Omni config", _USER_CFG_DIR / "omni_config.yaml"),
        ("Prompt overrides", _USER_CFG_DIR / "overrides" / "prompts"),
    ]

    items = []
    all_done = True
    for name, path in checks:
        configured = bool(path is not None and isinstance(path, Path) and path.exists())
        if not configured:
            all_done = False
        items.append({"name": name, "configured": configured})

    if output_text(None, data={"status": "ok", "all_configured": all_done, "items": items}):
        return

    typer.echo("\nOnboarding Status")
    typer.echo("=" * 50)

    for name, path in checks:
        if path is None:
            typer.echo(f"  ⬜ {name} — not configured")
            all_done = False
        elif isinstance(path, Path) and path.exists():
            typer.secho(f"  ✅ {name}", fg=typer.colors.GREEN)
        elif isinstance(path, Path):
            typer.echo(f"  ⬜ {name} — not configured")
            all_done = False
        else:
            typer.echo(f"  ⬜ {name} — not configured")
            all_done = False

    typer.echo("")
    if all_done:
        typer.secho("  All systems configured! 🎉", fg=typer.colors.GREEN)
    else:
        typer.echo("  Run: automedia onboard --step <name> to configure missing items")


@app.command(name="list")
def cmd_list() -> None:
    """List all configurable items and their current values."""
    config = load_config()

    # Brand
    brand_path = _USER_CFG_DIR / "brand-profile.yaml"
    brand: dict[str, Any] = {}
    if brand_path.exists():
        with open(brand_path, encoding="utf-8") as fh:
            brand = yaml.safe_load(fh) or {}

    # HITL
    hitl_path = _USER_CFG_DIR / "hitl" / "active_preset.yaml"
    hitl: dict[str, Any] = {}
    if hitl_path.exists():
        with open(hitl_path, encoding="utf-8") as fh:
            hitl = yaml.safe_load(fh) or {}

    platforms = config.get("platforms", {})
    enabled = [k for k, v in platforms.items() if isinstance(v, dict) and v.get("enabled")]

    if output_text(None, data={
            "status": "ok",
            "llm_provider": (
                config.get("llm", {}).get("text_generation", {}).get("provider", "not set")
            ),
            "llm_model": config.get("llm", {}).get("text_generation", {}).get("model", "not set"),
            "default_mode": config.get("mode", "auto"),
            "default_language": config.get("content", {}).get("default_language", "zh"),
            "brand_name": brand.get("brand_name", "not set"),
            "languages": [k for k in brand.get("languages", {})] or ["not configured"],
            "enabled_platforms": enabled or ["none"],
            "hitl_preset": hitl.get("preset", "not set"),
        },
    ):
        return

    typer.echo("\nCurrent Configuration")
    typer.echo("=" * 50)

    typer.echo(
        f"LLM provider: "
        f"{config.get('llm', {}).get('text_generation', {}).get('provider', 'not set')}"
    )
    typer.echo(
        f"LLM model: {config.get('llm', {}).get('text_generation', {}).get('model', 'not set')}"
    )
    typer.echo(f"Default mode: {config.get('mode', 'auto')}")
    typer.echo(f"Default language: {config.get('content', {}).get('default_language', 'zh')}")

    # Brand
    if brand_path.exists():
        typer.echo(f"Brand: {brand.get('brand_name', 'not set')}")
        typer.echo(
            f"Languages: {[k for k in brand.get('languages', {})] or ['not configured']}"
        )

    # Platform
    typer.echo(f"Enabled platforms: {enabled or ['none']}")

    # HITL
    if hitl_path.exists():
        typer.echo(f"HITL preset: {hitl.get('preset', 'not set')}")

    typer.echo("")
    typer.echo("Config files in ~/.automedia/:")
    for f in sorted(_USER_CFG_DIR.rglob("*")):
        if f.is_file() and ".pyc" not in str(f):
            typer.echo(f"  {f.relative_to(_USER_CFG_DIR)}")
