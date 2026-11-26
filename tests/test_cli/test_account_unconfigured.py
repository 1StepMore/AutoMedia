"""`automedia account <cmd>` on a machine with no master key configured (#706).

A brand-new install has no AUTOMEDIA_MASTER_KEY. Every read-only subcommand used
to die with a full Python traceback, which tells a newcomer nothing and reads like
a crash of the whole CLI. What they should see is one line saying the store is not
configured yet and what to set.

Hermetic: no network, config dir redirected to a temp dir, master key removed from
the environment and from the dotenv overlay.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from automedia.cli.app import app

runner = CliRunner()


@pytest.fixture()
def unconfigured(monkeypatch, tmp_path):
    """Fresh config dir + no master key anywhere (env or .env overlay)."""
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.delenv("AUTOMEDIA_MASTER_KEY", raising=False)
    monkeypatch.setattr(
        "automedia.accounts.store.env_lookup",
        lambda name, *a, **kw: None if name == "AUTOMEDIA_MASTER_KEY" else "",
    )
    return tmp_path


@pytest.mark.parametrize("command", [["account", "list"], ["account", "health", "acc_x"]])
def test_read_commands_explain_the_missing_key_instead_of_crashing(unconfigured, command):
    result = runner.invoke(app, command)

    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output, result.output
    assert "AUTOMEDIA_MASTER_KEY" in result.output, result.output
    # Points somewhere actionable rather than at "contact support".
    assert "account-management" in result.output, result.output


def test_list_still_works_once_a_master_key_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOMEDIA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("AUTOMEDIA_MASTER_KEY", "unit-test-master-key")

    result = runner.invoke(app, ["account", "list"])

    assert result.exit_code == 0, result.output
    assert "No accounts found" in result.output, result.output
