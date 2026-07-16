"""Three-layer credential loader: environment variable > keyring (optional) > local YAML fallback.

Public API
----------
- ``load_credential(key_name, *, provider=None)``
- ``resolve_api_key(provider_name, role='default')``

On import, this module automatically loads ``.env`` from ``~/.automedia/.env``
(default) or from the path specified by the ``AUTOMEDIA_DOTENV_PATH``
environment variable (override).
"""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

import yaml

from automedia.core.paths import get_user_config_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load .env on import — makes AUTOMEDIA_* vars available immediately
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv

    _dotenv_path = os.environ.get("AUTOMEDIA_DOTENV_PATH")
    _env_path = Path(_dotenv_path) if _dotenv_path else get_user_config_dir() / ".env"
    if _env_path.is_file():
        load_dotenv(_env_path, override=False)
except ImportError:
    from automedia.core._import_helpers import warn_missing_optional

    warn_missing_optional(
        "python-dotenv",
        install_command="pip install automedia-pipeline",
        feature=".env file will not be loaded",
    )

# ---------------------------------------------------------------------------
# Optional dependency: keyring
# ---------------------------------------------------------------------------

try:
    import keyring as _keyring
except ImportError:
    from automedia.core._import_helpers import warn_missing_optional

    warn_missing_optional("keyring", install_command="pip install keyring")
    _keyring = None  # type: ignore[assignment]  # _keyring was a module from `import keyring`; reassigning to None changes the type

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cred_dir() -> Path:
    """Return the ``~/.automedia`` directory (resolved lazily)."""
    return get_user_config_dir()


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
    except Exception:  # noqa: BLE001 — silent fallback is intentional
        logger.debug("Could not load credential from %s", filename)
        pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
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
        except Exception:  # noqa: BLE001 — silent fallback is intentional
            logger.debug("Keyring lookup failed for %s", key_name)
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


def load_credential_or_env(legacy_env_var: str, key_name: str) -> str | None:
    """Try the standard :func:`load_credential` chain first, then legacy env var.

    This helper supports gradual migration: platform adapters that historically
    read vendor-specific environment variables (e.g. ``WX_APPID``) can use it
    to retain backward compatibility while adopting the standard
    ``AUTOMEDIA_*`` credential chain.

    Priority order (highest first):

    1. :func:`load_credential` — checks ``AUTOMEDIA_<KEY>`` env var,
       ``AUTOMEDIA_<KEY>_KEY`` suffix, system keyring, and YAML files.
    2. Legacy environment variable (e.g. ``WX_APPID``, ``XHS_COOKIE``).

    Parameters
    ----------
    legacy_env_var:
        The legacy environment-variable name checked as fallback
        (e.g. ``"WX_APPID"``).
    key_name:
        The logical credential name passed to :func:`load_credential`
        (e.g. ``"wechat_appid"`` → ``AUTOMEDIA_WECHAT_APPID``).

    Returns
    -------
    str | None
        The credential value, or ``None`` if not found in any source.
    """
    value = load_credential(key_name)
    if value is not None:
        return value
    return os.environ.get(legacy_env_var)


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
    except Exception:  # noqa: BLE001 — silent fallback is intentional
        logger.debug("Could not read model_config.yaml for %s", provider_name)
        pass

    return load_credential(provider_name, provider=provider_name)


def load_credential_with_account_fallback(
    key_name: str,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> str | None:
    """Try PRD-4 account store first, then fall back to legacy credential chain.

    This is the bridging layer for gradual migration from flat env-var
    credentials to the PRD-4 encrypted account store.

    When *account_id* is provided and the account exists in the PRD-4
    store, returns the credential from the encrypted store.
    Otherwise falls back to :func:`load_credential` with a deprecation warning.

    Parameters
    ----------
    key_name:
        The credential key name (e.g. ``"wechat_appid"``, ``"zhihu_cookie"``).
    provider:
        Optional provider name for legacy keyring lookup.
    account_id:
        Optional PRD-4 account ID for encrypted store lookup.

    Returns
    -------
    str | None
        The credential value, or ``None`` if not found in any source.
    """
    if account_id:
        try:
            from automedia.accounts.store import AccountStore

            store = AccountStore()
            creds = store.load(account_id)
            if creds and key_name in creds:
                return creds[key_name]
        except Exception:
            logger.debug("PRD-4 account lookup failed for %s/%s", account_id, key_name)

    warnings.warn(
        f"Using legacy credential path for '{key_name}'. "
        "Migrate to PRD-4 account store: automedia account connect ...",
        DeprecationWarning,
        stacklevel=2,
    )
    return load_credential(key_name, provider=provider)
