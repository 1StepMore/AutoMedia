"""Three-layer credential loader: environment variable > keyring (optional) > local YAML fallback.

Public API
----------
- ``load_credential(key_name, *, provider=None)``
- ``resolve_api_key(provider_name, role='default')``

On import, this module automatically loads ``.env`` from the current working
directory (if present) so that ``AUTOMEDIA_*`` variables are available for
lookup.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Load .env on import — makes AUTOMEDIA_* vars available immediately
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv

    _env_path = Path.cwd() / ".env"
    if _env_path.is_file():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Optional dependency: keyring
# ---------------------------------------------------------------------------

try:
    import keyring as _keyring
except ImportError:
    _keyring = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cred_dir() -> Path:
    """Return the ``~/.automedia`` directory (resolved lazily)."""
    return Path.home() / ".automedia"


def _env_var_name(key_name: str) -> str:
    """Return the primary environment-variable name for *key_name*."""
    return f"AUTOMEDIA_{key_name.upper()}"


def _load_yaml_cred(filename: str, key_name: str) -> str | None:
    """Look up *key_name* in ``~/.automedia/{filename}``.

    Returns ``None`` when the file does not exist, cannot be parsed, or
    does not contain the requested key (never raises).
    """
    path = _cred_dir() / filename
    try:
        if path.is_file():
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                value = data.get(key_name)
                if isinstance(value, str):
                    return value
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_credential(key_name: str, *, provider: str | None = None) -> str | None:
    """Load a credential by *key_name*.

    Sources, in priority order (highest first):

    1. Environment variable ``AUTOMEDIA_<KEY>`` (also tries
       ``AUTOMEDIA_<KEY>_KEY`` for convenience).
    2. System keyring via the ``keyring`` package (optional dependency —
       silently skipped when not installed or when it raises).
    3. ``~/.automedia/oscreds.yaml``
    4. ``~/.automedia/credentials.yaml`` (legacy fallback)

    Parameters
    ----------
    key_name:
        The logical credential name (e.g. ``"openai"``, ``"test_key"``).
        Case-insensitive for the environment-variable lookup.
    provider:
        Optional service name passed to the keyring backend. When *None*,
        ``"automedia"`` is used.

    Returns
    -------
    str | None
        The credential value, or ``None`` if not found (never raises).
    """
    # ------------------------------------------------------------------
    # Layer 1 — Environment variable
    # ------------------------------------------------------------------
    env_key = _env_var_name(key_name)
    value = os.environ.get(env_key)
    if value is not None:
        return value

    # Also check AUTOMEDIA_<KEY>_KEY (e.g. AUTOMEDIA_OPENAI_KEY)
    value = os.environ.get(f"{env_key}_KEY")
    if value is not None:
        return value

    # ------------------------------------------------------------------
    # Layer 2 — System keyring (optional)
    # ------------------------------------------------------------------
    if _keyring is not None:
        try:
            service = provider or "automedia"
            value = _keyring.get_password(service, key_name)
            if value is not None:
                return value
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Layer 3 — oscreds.yaml
    # ------------------------------------------------------------------
    value = _load_yaml_cred("oscreds.yaml", key_name)
    if value is not None:
        return value

    # ------------------------------------------------------------------
    # Layer 4 — credentials.yaml (legacy fallback)
    # ------------------------------------------------------------------
    return _load_yaml_cred("credentials.yaml", key_name)


def resolve_api_key(provider_name: str, role: str = "default") -> str | None:
    """Resolve an API key for a named provider.

    Priority
    --------
    1. Environment variable ``AUTOMEDIA_{PROVIDER_NAME}``
    2. ``~/.automedia/model_config.yaml`` → ``providers.{provider_name}.api_key``
    3. :func:`load_credential(provider_name)``

    Parameters
    ----------
    provider_name:
        The provider name (e.g. ``"openai"``, ``"anthropic"``).
    role:
        Unused placeholder for future provider-role selection.

    Returns
    -------
    str | None
        The resolved API key, or ``None`` if not found (never raises).
    """
    # Highest priority: environment variable (e.g. AUTOMEDIA_OPENAI)
    env_value = os.environ.get(_env_var_name(provider_name))
    if env_value:
        return env_value

    config_path = _cred_dir() / "model_config.yaml"
    try:
        if config_path.is_file():
            with open(config_path, encoding="utf-8") as fh:
                config = yaml.safe_load(fh)
            if isinstance(config, dict):
                providers = config.get("providers")
                if isinstance(providers, dict):
                    prov_cfg = providers.get(provider_name)
                    if isinstance(prov_cfg, dict):
                        api_key = prov_cfg.get("api_key")
                        if isinstance(api_key, str):
                            return api_key
    except Exception:
        pass

    return load_credential(provider_name, provider=provider_name)
