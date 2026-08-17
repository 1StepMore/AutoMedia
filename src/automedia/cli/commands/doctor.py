"""``automedia doctor`` — dependency and environment health check."""

from __future__ import annotations

import platform
import subprocess
from typing import Any

import typer
import yaml

from automedia.cli.output import OutputMode, get_output_mode, output_json
from automedia.core.doctor import Doctor
from automedia.core.paths import get_user_config_dir

# Official API hosts per provider, matched case-insensitively against the
# configured ``base_url`` host. Used by the model-vs-endpoint heuristic.
_OFFICIAL_HOSTS: dict[str, str] = {
    "deepseek": "api.deepseek.com",
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
    "openrouter": "openrouter.ai",
}

_NO_FALLBACK_MSG = (
    "No LLM fallback chain configured. If the primary provider fails, calls fail "
    "immediately. Re-run `automedia onboard --step llm` to add a backup provider, "
    "or edit model_config.yaml."
)


def _is_official_model(provider: str, model: str) -> bool:
    """Return ``True`` when *model* is a known official family for *provider*."""
    p = provider.lower()
    m = model.lower()
    if p == "deepseek":
        return m.startswith("deepseek-chat")
    if p == "openai":
        return m.startswith("gpt-4o") or m.startswith("gpt-4.1") or m.startswith("gpt-5")
    if p == "anthropic":
        return m.startswith("claude-")
    return False


def _collect_llm_warnings() -> tuple[str | None, list[str]]:
    """Collect advisory warnings about the LLM/fallback configuration.

    Returns ``(config_path, warnings)`` where *config_path* is ``None`` when no
    ``model_config.yaml`` exists. Warnings are advisory only — they never affect
    the doctor exit code.
    """
    config_path = get_user_config_dir() / "model_config.yaml"
    if not config_path.is_file():
        return (None, [])

    path_str = str(config_path)
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError:
        return (path_str, ["model_config.yaml is not valid YAML"])

    if not isinstance(data, dict):
        return (path_str, ["model_config.yaml is not valid YAML"])

    warnings: list[str] = []
    tg = data.get("llm", {})
    if not isinstance(tg, dict):
        tg = {}
    tg = tg.get("text_generation", {})
    if not isinstance(tg, dict):
        tg = {}

    fallback = tg.get("fallback")
    if not isinstance(fallback, list) or not fallback:
        warnings.append(_NO_FALLBACK_MSG)
    else:
        for i, entry in enumerate(fallback, start=1):
            if not isinstance(entry, dict) or not (
                entry.get("provider") and entry.get("api_key") and entry.get("base_url")
            ):
                warnings.append(
                    f"fallback entry {i} is incomplete (missing provider, api_key, or base_url)."
                )

    provider = tg.get("provider")
    model = tg.get("model")
    base_url = tg.get("base_url")
    if provider and model and base_url:
        official_host = _OFFICIAL_HOSTS.get(str(provider).lower())
        if (
            official_host
            and _is_official_model(str(provider), str(model))
            and official_host not in str(base_url).lower()
        ):
            warnings.append(
                f"Primary model {model!r} may not match base_url {base_url!r} "
                f"for provider {provider!r}."
            )

    return (path_str, warnings)


def _is_piped_script(instruction: str) -> bool:
    """Check if an install instruction is a piped shell script (``curl | bash``)."""
    return "curl" in instruction and "| bash" in instruction


def _handle_fix_install(results: list[dict[str, Any]]) -> bool:
    """Interactive fix: show missing deps, prompt user, install, re-check.

    Returns ``True`` if all dependencies are satisfied after the fix.
    """
    missing_installable: list[tuple[str, str]] = []
    missing_unavailable: list[str] = []

    for dep in results:
        if dep["installed"]:
            continue
        name: str = dep["name"]
        instruction = Doctor.get_install_instructions(name)
        if instruction and not instruction.startswith("See "):
            missing_installable.append((name, instruction))
        else:
            missing_unavailable.append(name)

    if missing_unavailable:
        typer.echo("")
        typer.secho("No automated install available:", fg=typer.colors.YELLOW, bold=True)
        for name in missing_unavailable:
            typer.echo(f"  {name}")

    if not missing_installable:
        return all(dep["installed"] for dep in results)

    typer.echo("")
    typer.secho("Dependencies to install:", fg=typer.colors.CYAN, bold=True)
    for name, instruction in missing_installable:
        typer.secho(f"  {name}:", fg=typer.colors.YELLOW, bold=True)
        typer.echo(f"    {instruction}")
        if _is_piped_script(instruction):
            typer.secho(
                "    ⚠  Uses a piped shell script (curl | bash)."
                " Review before running with --fix.",
                fg=typer.colors.YELLOW,
            )

    if not typer.confirm("\nInstall missing dependencies?", default=False):
        typer.echo("Skipping installation.")
        return all(dep["installed"] for dep in results)

    for name, instruction in missing_installable:
        typer.secho(f"Installing {name}...", fg=typer.colors.CYAN)
        try:
            subprocess.run(instruction, shell=True, check=False, timeout=120)  # noqa: S603,S602 — instructions are hardcoded constants
        except Exception as exc:
            typer.secho(f"  ✗ Failed to install {name}: {exc}", fg=typer.colors.RED)

    typer.echo("")
    typer.secho("Re-checking dependencies...", fg=typer.colors.CYAN, bold=True)
    d = Doctor()
    new_results = d.check_dependencies()
    new_all_ok = all(dep["installed"] for dep in new_results)

    typer.echo("-" * 60)
    for dep in new_results:
        icon = "✓" if dep["installed"] else "✗"
        version = dep.get("version") or "—"
        colour = typer.colors.GREEN if dep["installed"] else typer.colors.RED
        typer.secho(
            f"{icon} {dep['name']:<14} {'yes' if dep['installed'] else 'no':<12} {version}",
            fg=colour,
        )
    typer.echo("-" * 60)

    if new_all_ok:
        typer.secho("All dependencies satisfied.", fg=typer.colors.GREEN)
    else:
        typer.secho(
            "Some dependencies are still missing.", fg=typer.colors.YELLOW, err=True
        )

    return new_all_ok


def doctor_cmd(
    install_missing: bool = typer.Option(
        False,
        "--install-missing",
        help="Print OS-appropriate install commands for missing dependencies.",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Attempt to install missing dependencies (interactive prompt).",
    ),
) -> None:
    """Run a dependency status check and print a formatted table."""
    d = Doctor()
    results = d.check_dependencies()

    if get_output_mode() == OutputMode.JSON:
        all_ok = all(dep["installed"] for dep in results)
        config_path, llm_warnings = _collect_llm_warnings()
        payload: dict[str, Any] = {
            "status": "ok" if all_ok else "error",
            "dependencies": results,
            "llm": {
                "model_config": config_path,
                "warnings": llm_warnings,
            },
        }
        if install_missing:
            missing_instructions = {}
            for dep in results:
                if not dep["installed"]:
                    instruction = Doctor.get_install_instructions(dep["name"])
                    if instruction:
                        missing_instructions[dep["name"]] = instruction
            if missing_instructions:
                payload["install_instructions"] = missing_instructions
        output_json(payload)
        if not all_ok:
            raise typer.Exit(code=1)
        return

    typer.echo("Dependency Check:")
    typer.echo("-" * 60)
    typer.echo(f"{'Tool':<16} {'Installed':<12} {'Version'}")
    typer.echo("-" * 60)

    all_ok = True
    for dep in results:
        icon = "✓" if dep["installed"] else "✗"
        version = dep.get("version") or "—"
        colour = typer.colors.GREEN if dep["installed"] else typer.colors.RED
        typer.secho(
            f"{icon} {dep['name']:<14} {'yes' if dep['installed'] else 'no':<12} {version}",
            fg=colour,
        )
        if dep["name"] == "chrome" and dep.get("installed") and dep.get("headless_ok") is False:
            msg = dep.get("headless_message") or "unknown error"
            typer.secho(
                f"  ⚠ Chrome binary found but headless check failed: {msg}",
                fg=typer.colors.YELLOW,
            )
            hd_instructions = Doctor.get_headless_chrome_instructions()
            if hd_instructions:
                typer.secho(f"    {hd_instructions}", fg=typer.colors.YELLOW)
        if not dep["installed"]:
            all_ok = False

    typer.echo("-" * 60)

    config_path, llm_warnings = _collect_llm_warnings()
    if llm_warnings:
        if config_path is not None:
            typer.echo("LLM Configuration:")
        for warning in llm_warnings:
            typer.secho(f"  ⚠ {warning}", fg=typer.colors.YELLOW)

    if all_ok:
        typer.secho("All dependencies satisfied.", fg=typer.colors.GREEN)
    else:
        typer.secho("Some dependencies are missing.", fg=typer.colors.YELLOW, err=True)

    if install_missing and not all_ok:
        os_name = platform.system()
        typer.echo("")
        typer.secho(f"Install instructions ({os_name}):", fg=typer.colors.CYAN, bold=True)
        typer.echo("-" * 60)
        for dep in results:
            if not dep["installed"]:
                instruction = Doctor.get_install_instructions(dep["name"])
                if instruction:
                    typer.secho(f"  {dep['name']}:", fg=typer.colors.YELLOW, bold=True)
                    typer.echo(f"    {instruction}")
                else:
                    typer.secho(f"  {dep['name']}:", fg=typer.colors.YELLOW, bold=True)
                    typer.echo("    No automatic install instruction available.")
        typer.echo("-" * 60)

    if fix and not all_ok:
        all_ok = _handle_fix_install(results)

    if not all_ok:
        raise typer.Exit(code=1)
