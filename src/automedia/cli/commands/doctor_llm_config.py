"""Advisory LLM/fallback configuration diagnostics for ``automedia doctor``.

Split out of ``doctor.py`` so the command module stays focused on dependency
probing and install handling, and so the fallback-completeness rules — which
must mirror ``llm_client``'s runtime resolution exactly — are reviewable on
their own.
"""

from __future__ import annotations

import re

import yaml

from automedia.core.credential_loader import resolve_api_key
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

# Shell-style variable placeholder (``${VAR}``). The credential loader does not
# expand these, so a literal one in ``api_key`` is a runtime 401 waiting to happen.
_ENV_PLACEHOLDER_RE = re.compile(r"\$\{[^}]+\}")


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


def _fallback_entry_warning(index: int, entry: object) -> str | None:
    """Return an advisory warning for one ``fallback`` *entry*, or ``None`` if usable.

    The judgement mirrors the runtime in ``llm_client._iter_provider_specs`` and
    ``_build_client``:

    * an entry without a ``provider`` is skipped entirely, so it never joins the
      chain;
    * ``base_url`` is inherited from the primary block when the entry omits it,
      so it is never required per entry;
    * an absent ``api_key`` is resolved by the runtime through
      :func:`resolve_api_key` (env var ``AUTOMEDIA_<PROVIDER>``, the
      ``providers:`` block in ``model_config.yaml``, or the credential store).

    The key check defers to :func:`resolve_api_key` instead of reading the raw
    YAML literal because the runtime does the same — a literal-only check would
    re-introduce the false alarm for keys kept in ``~/.automedia/.env`` or the
    credential store.  Do not "simplify" this back to a literal read.

    *index* is the 1-based position used in the message for the operator.
    """
    if not isinstance(entry, dict):
        return f"fallback entry {index} is not a mapping and will be skipped at runtime."

    provider = entry.get("provider")
    if not provider:
        return (
            f"fallback entry {index} has no provider and will be skipped at runtime; "
            "the fallback chain entry is dead."
        )

    api_key = entry.get("api_key")
    if isinstance(api_key, str) and _ENV_PLACEHOLDER_RE.search(api_key):
        return (
            f"fallback entry {index} api_key is an unexpanded variable placeholder; "
            "the credential loader does not expand ${VAR} syntax. Set the key "
            f"directly, in model_config.yaml providers.{provider}.api_key, or via "
            f"AUTOMEDIA_{str(provider).upper()}."
        )

    if not api_key and resolve_api_key(str(provider)) is None:
        return (
            f"fallback entry {index} has no usable api_key resolved from the "
            f"environment, model_config.yaml providers.{provider}.api_key, or the "
            "credential store."
        )

    return None


def collect_llm_warnings() -> tuple[str | None, list[str]]:
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
            entry_warning = _fallback_entry_warning(i, entry)
            if entry_warning is not None:
                warnings.append(entry_warning)

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
