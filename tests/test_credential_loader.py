"""Tests for automedia.core.credential_loader — three-layer credential loader."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import yaml

import automedia.core.credential_loader as cl
from automedia.core.credential_loader import (
    load_credential,
    resolve_api_key,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_home(monkeypatch, tmp_path: Path, subdir: str = ".automedia") -> Path:
    """Point ``Path.home()`` to *tmp_path/home* and create ``~/.automedia``.

    Returns the ``.automedia`` directory.
    """
    home = tmp_path / "home"
    cred_dir = home / subdir
    cred_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    return cred_dir


def _mock_keyring(monkeypatch, get_password=None):
    """Replace the module-level ``keyring`` reference.

    When *get_password* is ``None``, keyring is disabled (import-failure
    simulation). Otherwise it is set to a callable.

    Returns the callable so tests can inspect it.
    """
    import automedia.core.credential_loader as cl

    if get_password is None:
        monkeypatch.setattr(cl, "_keyring", None)
        return None
    else:

        class FakeKeyring:
            @staticmethod
            def get_password(service, username):
                return get_password(service, username)

        monkeypatch.setattr(cl, "_keyring", FakeKeyring)
        return FakeKeyring.get_password


# ---------------------------------------------------------------------------
# load_credential
# ---------------------------------------------------------------------------


class TestLoadCredential:
    """Unit tests for ``load_credential`` — three-layer (env > keyring > YAML)."""

    # -- Layer 1a: Primary env var AUTOMEDIA_<KEY> ---------------------------

    def test_env_var_primary_is_checked_first(self, monkeypatch):
        """Primary env var ``AUTOMEDIA_<KEY>`` is checked first and returned."""
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "sk-primary")
        assert load_credential("openai") == "sk-primary"

    def test_env_var_primary_uppercase_insensitive(self, monkeypatch):
        """Key name is uppercased for the env var lookup."""
        monkeypatch.setenv("AUTOMEDIA_MIXED_CASE", "val")
        assert load_credential("Mixed_Case") == "val"

    # -- Layer 1b: Suffix env var AUTOMEDIA_<KEY>_KEY -----------------------

    def test_env_var_suffix_fallback(self, monkeypatch):
        """Suffix env var ``AUTOMEDIA_<KEY>_KEY`` is checked as fallback."""
        monkeypatch.setenv("AUTOMEDIA_OPENAI_KEY", "sk-suffix")
        assert load_credential("openai") == "sk-suffix"

    def test_env_var_primary_overrides_suffix(self, monkeypatch):
        """Primary env var takes precedence over the ``_KEY`` suffix."""
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "sk-primary")
        monkeypatch.setenv("AUTOMEDIA_OPENAI_KEY", "sk-suffix")
        assert load_credential("openai") == "sk-primary"

    def test_env_var_with_underscores_in_key(self, monkeypatch):
        """Key names containing underscores map correctly."""
        monkeypatch.setenv("AUTOMEDIA_TEST_KEY", "sk-test-val")
        assert load_credential("test_key") == "sk-test-val"

    def test_env_var_not_found_returns_none(self):
        """No matching env var → None (no exception)."""
        assert load_credential("nonexistent_cred") is None

    # -- Layer 2: System keyring (optional) ---------------------------------

    def test_keyring_used_when_available(self, monkeypatch):
        """When keyring is importable and has the credential, it is returned."""
        _mock_keyring(
            monkeypatch,
            lambda service, username: "ring-secret" if username == "mykey" else None,
        )
        monkeypatch.setenv("AUTOMEDIA_NOPE", "")  # ensure env is empty
        assert load_credential("mykey") == "ring-secret"

    def test_keyring_skipped_when_not_installed(self, monkeypatch):
        """When _keyring is None (import failed), keyring is skipped."""
        _mock_keyring(monkeypatch, get_password=None)
        # No env var set, no YAML files exist → None
        assert load_credential("mykey") is None

    def test_keyring_exception_is_silent(self, monkeypatch):
        """A keyring that raises is silently skipped."""
        _mock_keyring(
            monkeypatch,
            lambda service, username: (_ for _ in ()).throw(RuntimeError("broken")),
        )
        assert load_credential("mykey") is None

    def test_keyring_passes_provider_as_service(self, monkeypatch):
        """When ``provider=`` is passed, keyring uses that as the service name."""
        recorded = []

        def track(service, username):
            recorded.append((service, username))
            return None

        _mock_keyring(monkeypatch, track)
        load_credential("key1", provider="myprovider")
        assert ("myprovider", "key1") in recorded

    def test_keyring_default_service(self, monkeypatch):
        """When provider is None, keyring service defaults to 'automedia'."""
        recorded = []

        def track(service, username):
            recorded.append((service, username))
            return None

        _mock_keyring(monkeypatch, track)
        load_credential("key1")
        assert ("automedia", "key1") in recorded

    # -- Layer 3: oscreds.yaml ---------------------------------------------

    def test_oscreds_yaml_returns_value(self, monkeypatch, tmp_path):
        """oscreds.yaml is consulted and returns the credential value."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        (cred_dir / "oscreds.yaml").write_text("mykey: sk-from-oscreds\n")
        assert load_credential("mykey") == "sk-from-oscreds"

    def test_oscreds_yaml_missing_is_silent(self, monkeypatch, tmp_path):
        """Missing oscreds.yaml returns None (no crash)."""
        _mock_home(monkeypatch, tmp_path)
        assert load_credential("mykey") is None

    def test_oscreds_yaml_not_a_dict(self, monkeypatch, tmp_path):
        """YAML file that is a list (not dict) is treated as absent."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        (cred_dir / "oscreds.yaml").write_text("- item1\n- item2\n")
        assert load_credential("mykey") is None

    def test_oscreds_yaml_non_string_value(self, monkeypatch, tmp_path):
        """Non-string values are treated as absent (e.g. integer)."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        (cred_dir / "oscreds.yaml").write_text("mykey: 42\n")
        assert load_credential("mykey") is None

    def test_oscreds_yaml_key_not_present(self, monkeypatch, tmp_path):
        """Requesting a key that does not exist in the YAML returns None."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        (cred_dir / "oscreds.yaml").write_text("other_key: val\n")
        assert load_credential("mykey") is None

    def test_oscreds_yaml_broken_yaml(self, monkeypatch, tmp_path):
        """Malformed YAML is silently skipped (returns None)."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        (cred_dir / "oscreds.yaml").write_text(": broken yaml [[\n")
        assert load_credential("mykey") is None

    # -- Layer 4: credentials.yaml (legacy fallback) -----------------------

    def test_credentials_yaml_fallback(self, monkeypatch, tmp_path):
        """credentials.yaml is consulted when oscreds.yaml has no match."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        (cred_dir / "credentials.yaml").write_text("mykey: sk-legacy\n")
        assert load_credential("mykey") == "sk-legacy"

    def test_oscreds_takes_precedence_over_credentials(self, monkeypatch, tmp_path):
        """oscreds.yaml is checked before credentials.yaml."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        (cred_dir / "oscreds.yaml").write_text("mykey: sk-oscreds\n")
        (cred_dir / "credentials.yaml").write_text("mykey: sk-credentials\n")
        assert load_credential("mykey") == "sk-oscreds"

    def test_both_yamls_missing(self, monkeypatch, tmp_path):
        """Neither YAML file exists → None (no crash)."""
        _mock_home(monkeypatch, tmp_path)
        assert load_credential("mykey") is None

    # -- Full priority chain ------------------------------------------------

    def test_full_priority_chain(self, monkeypatch, tmp_path):
        """Env var > keyring > oscreds.yaml > credentials.yaml."""
        cred_dir = _mock_home(monkeypatch, tmp_path)

        _mock_keyring(
            monkeypatch,
            lambda service, username: "ring-value",
        )

        (cred_dir / "oscreds.yaml").write_text("mykey: oscreds-value\n")
        (cred_dir / "credentials.yaml").write_text("mykey: creds-value\n")

        # Without env var, keyring wins
        assert load_credential("mykey") == "ring-value"

        # With env var, env wins
        monkeypatch.setenv("AUTOMEDIA_MYKEY", "env-value")
        assert load_credential("mykey") == "env-value"

    def test_no_exceptions_ever(self, monkeypatch):
        """load_credential never raises; returns None on all failure paths."""
        _mock_keyring(monkeypatch, get_password=None)
        # Brute-force: corrupt env var? can't corrupt os.environ easily,
        # but all other paths should be safe.
        assert load_credential("some_key") is None

    def test_provider_param_no_effect_on_env_yaml(self, monkeypatch, tmp_path):
        """provider= only affects keyring service name, not env or YAML."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        (cred_dir / "oscreds.yaml").write_text("mykey: oscreds-val\n")

        _mock_keyring(monkeypatch, lambda s, u: None)
        assert load_credential("mykey", provider="custom") == "oscreds-val"


# ---------------------------------------------------------------------------
# resolve_api_key
# ---------------------------------------------------------------------------


class TestResolveApiKey:
    """Unit tests for ``resolve_api_key`` — model_config.yaml > load_credential."""

    def test_reads_from_model_config(self, monkeypatch, tmp_path):
        """Reads ``providers.{name}.api_key`` from model_config.yaml."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        config = {"providers": {"openai": {"api_key": "cfg-sk-openai"}}}
        (cred_dir / "model_config.yaml").write_text(yaml.dump(config))

        assert resolve_api_key("openai") == "cfg-sk-openai"

    def test_model_config_missing_falls_back(self, monkeypatch, tmp_path):
        """Missing model_config.yaml falls back to load_credential."""
        _mock_home(monkeypatch, tmp_path)
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "env-sk-openai")
        assert resolve_api_key("openai") == "env-sk-openai"

    def test_model_config_no_providers_key(self, monkeypatch, tmp_path):
        """model_config.yaml without ``providers`` key falls back gracefully."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        (cred_dir / "model_config.yaml").write_text("some_other_key: true\n")
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "env-sk")
        assert resolve_api_key("openai") == "env-sk"

    def test_model_config_provider_not_in_yaml(self, monkeypatch, tmp_path):
        """Requested provider missing from providers dict → fallback."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        config = {"providers": {"anthropic": {"api_key": "sk-anthropic"}}}
        (cred_dir / "model_config.yaml").write_text(yaml.dump(config))
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "env-sk")
        assert resolve_api_key("openai") == "env-sk"

    def test_model_config_api_key_not_string(self, monkeypatch, tmp_path):
        """Non-string api_key value is treated as absent."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        config = {"providers": {"openai": {"api_key": False}}}
        (cred_dir / "model_config.yaml").write_text(yaml.dump(config))
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "env-sk")
        assert resolve_api_key("openai") == "env-sk"

    def test_model_config_corrupt_yaml(self, monkeypatch, tmp_path):
        """Corrupt model_config.yaml falls back gracefully."""
        _mock_home(monkeypatch, tmp_path)
        cred_dir = tmp_path / "home" / ".automedia"
        (cred_dir / "model_config.yaml").write_text("::: not yaml\n")
        monkeypatch.setenv("AUTOMEDIA_OPENAI", "env-sk")
        assert resolve_api_key("openai") == "env-sk"

    def test_both_missing_returns_none(self, monkeypatch, tmp_path):
        """When neither model_config.yaml nor load_credential has it → None."""
        _mock_home(monkeypatch, tmp_path)
        result = resolve_api_key("nonexistent")
        assert result is None

    def test_role_param_ignored(self, monkeypatch, tmp_path):
        """role= parameter is accepted but functionally unused (placeholder)."""
        cred_dir = _mock_home(monkeypatch, tmp_path)
        config = {"providers": {"x": {"api_key": "sk-x"}}}
        (cred_dir / "model_config.yaml").write_text(yaml.dump(config))
        assert resolve_api_key("x", role="worker") == "sk-x"

    def test_no_exceptions_ever(self, monkeypatch, tmp_path):
        """resolve_api_key never raises; returns None on all failure paths."""
        _mock_home(monkeypatch, tmp_path)
        assert resolve_api_key("nonexistent") is None


# ---------------------------------------------------------------------------
# .env loading security (no CWD auto-load)
# ---------------------------------------------------------------------------


class TestDotenvLoading:
    """Verify that .env is NOT auto-loaded from CWD.

    The module should load .env from ``~/.automedia/.env`` (default) or from
    the path specified by ``AUTOMEDIA_DOTENV_PATH`` (override).  A ``.env`` in
    the current working directory must never be auto-loaded — that is a
    security risk (malicious .env injection).
    """

    def test_cwd_dotenv_not_loaded(self, monkeypatch, tmp_path):
        """A .env file in CWD must NOT be auto-loaded at import time."""
        # Create a .env in a temp directory with a unique test key
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        (cwd_dir / ".env").write_text("SECURITY_TEST_CWD_VAR=injected\n")

        # Chdir to that directory; ensure no ~/.automedia/.env exists
        monkeypatch.chdir(cwd_dir)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty_home")

        # Reload the module to re-trigger import-time .env loading
        importlib.reload(cl)

        # The CWD .env must NOT have been loaded
        assert os.environ.get("SECURITY_TEST_CWD_VAR") is None

    def test_automedia_dotenv_loaded(self, monkeypatch, tmp_path):
        """~/.automedia/.env is loaded when it exists (default location)."""
        # Set up fake home with ~/.automedia/.env
        fake_home = tmp_path / "fake_home"
        automedia_dir = fake_home / ".automedia"
        automedia_dir.mkdir(parents=True)
        (automedia_dir / ".env").write_text("SECURITY_TEST_HOME_VAR=loaded_from_automedia\n")

        monkeypatch.setattr(Path, "home", lambda: fake_home)
        empty_cwd = tmp_path / "empty_cwd"
        empty_cwd.mkdir()
        monkeypatch.chdir(empty_cwd)
        monkeypatch.delenv("AUTOMEDIA_DOTENV_PATH", raising=False)

        importlib.reload(cl)

        assert os.environ.get("SECURITY_TEST_HOME_VAR") == "loaded_from_automedia"

    def test_dotenv_path_override(self, monkeypatch, tmp_path):
        """AUTOMEDIA_DOTENV_PATH overrides the default .env location."""
        # Create a .env at a custom non-standard path
        custom_path = tmp_path / "custom" / "my.env"
        custom_path.parent.mkdir(parents=True)
        custom_path.write_text("SECURITY_TEST_CUSTOM_VAR=from_custom_path\n")

        monkeypatch.setenv("AUTOMEDIA_DOTENV_PATH", str(custom_path))

        # Ensure ~/.automedia/.env does not exist to avoid ambiguity
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "empty_home")
        empty_cwd = tmp_path / "empty_cwd"
        empty_cwd.mkdir()
        monkeypatch.chdir(empty_cwd)

        importlib.reload(cl)

        assert os.environ.get("SECURITY_TEST_CUSTOM_VAR") == "from_custom_path"
