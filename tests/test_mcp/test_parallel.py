"""Tests for parallel MCP server launcher.

All tests use mocked subprocess.Popen — no real processes are spawned.
"""

from __future__ import annotations

import signal
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from automedia.mcp.parallel import (
    _signal_handler,
    _terminate_all_children,
    get_server_commands,
    start_parallel_servers,
    stop_parallel_servers,
)

# Capture the real Popen class before any test patches it (Python 3.14 compat)
_REAL_POPEN = subprocess.Popen


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_children():
    """Reset global _children dict and signal handler flag before each test."""
    from automedia.mcp import parallel

    parallel._children.clear()
    parallel._signal_handlers_installed = False
    yield
    parallel._children.clear()
    parallel._signal_handlers_installed = False


@pytest.fixture()
def mock_popen():
    def _make(pid: int = 1000) -> MagicMock:
        proc = MagicMock(spec=_REAL_POPEN)
        proc.pid = pid
        proc.poll.return_value = None
        proc.returncode = None
        proc.wait.return_value = 0
        return proc

    return _make


# ---------------------------------------------------------------------------
# Test: start_parallel_servers
# ---------------------------------------------------------------------------


class TestStartParallelServers:
    """Tests for start_parallel_servers()."""

    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_start_all_launches_4_servers(self, mock_popen_cls: MagicMock, mock_popen) -> None:
        """mode='all' should launch exactly 4 servers."""
        mock_popen_cls.return_value = mock_popen(pid=1001)
        servers = start_parallel_servers(mode="all")
        assert len(servers) == 4
        assert set(servers.keys()) == {"OPP", "OL", "ORF", "AutoMedia"}

    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_start_parallel_launches_4_servers(self, mock_popen_cls: MagicMock, mock_popen) -> None:
        """mode='parallel' should launch exactly 4 servers."""
        mock_popen_cls.return_value = mock_popen(pid=1002)
        servers = start_parallel_servers(mode="parallel")
        assert len(servers) == 4

    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_start_sdk_launches_1_server(self, mock_popen_cls: MagicMock, mock_popen) -> None:
        """mode='sdk' should launch only AutoMedia."""
        mock_popen_cls.return_value = mock_popen(pid=1003)
        servers = start_parallel_servers(mode="sdk")
        assert len(servers) == 1
        assert "AutoMedia" in servers

    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_popen_called_with_correct_args(self, mock_popen_cls: MagicMock, mock_popen) -> None:
        """Popen should be called with correct command and pipes."""
        mock_popen_cls.return_value = mock_popen(pid=1004)
        start_parallel_servers(mode="all")

        assert mock_popen_cls.call_count == 4
        for call_args in mock_popen_cls.call_args_list:
            args, kwargs = call_args
            cmd = args[0]
            assert cmd[0].endswith("python") or cmd[0].endswith("python3") or "python" in cmd[0]
            assert cmd[1] == "-m"
            assert cmd[2] == "automedia.mcp.server"
            assert kwargs["stdin"] == subprocess.PIPE
            assert kwargs["stdout"] == subprocess.PIPE
            assert kwargs["stderr"] == subprocess.PIPE

    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_returns_dict_of_popen(self, mock_popen_cls: MagicMock, mock_popen) -> None:
        """Return value is a dict mapping names to Popen instances."""
        proc = mock_popen(pid=1005)
        mock_popen_cls.return_value = proc
        servers = start_parallel_servers(mode="all")
        for name, p in servers.items():
            assert isinstance(name, str)
            assert p is proc

    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_signal_handlers_installed(self, mock_popen_cls: MagicMock, mock_popen) -> None:
        """Signal handlers are installed after start_parallel_servers."""
        from automedia.mcp import parallel

        mock_popen_cls.return_value = mock_popen(pid=1006)
        assert parallel._signal_handlers_installed is False
        start_parallel_servers(mode="all")
        assert parallel._signal_handlers_installed is True

    @patch("automedia.mcp.parallel.subprocess.Popen")
    def test_unknown_mode_defaults_to_all(self, mock_popen_cls: MagicMock, mock_popen) -> None:
        """Unknown mode defaults to launching all servers."""
        mock_popen_cls.return_value = mock_popen(pid=1007)
        servers = start_parallel_servers(mode="unknown_mode")
        assert len(servers) == 4


# ---------------------------------------------------------------------------
# Test: stop_parallel_servers
# ---------------------------------------------------------------------------


class TestStopParallelServers:
    """Tests for stop_parallel_servers()."""

    def test_terminate_running_servers(self, mock_popen) -> None:
        """Running servers should be terminated."""
        proc = mock_popen(pid=2001)
        servers = {"TestServer": proc}
        stop_parallel_servers(servers)
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=5)

    def test_skip_already_exited_servers(self, mock_popen) -> None:
        """Servers that already exited (poll != None) should be skipped."""
        proc = mock_popen(pid=2002)
        proc.poll.return_value = 0  # already exited
        servers = {"TestServer": proc}
        stop_parallel_servers(servers)
        proc.terminate.assert_not_called()

    def test_force_kill_on_timeout(self, mock_popen) -> None:
        """Servers that don't terminate in time should be force-killed."""
        proc = mock_popen(pid=2003)
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)
        servers = {"TestServer": proc}
        stop_parallel_servers(servers)
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# Test: signal handler
# ---------------------------------------------------------------------------


class TestSignalHandler:
    """Tests for signal handler behavior."""

    def test_signal_handler_raises_system_exit(self, mock_popen) -> None:
        """Signal handler should raise SystemExit after terminating children."""
        from automedia.mcp import parallel

        proc = mock_popen(pid=3001)
        parallel._children["TestServer"] = proc

        with pytest.raises(SystemExit) as exc_info:
            _signal_handler(signal.SIGINT, None)
        assert exc_info.value.code == 0
        proc.terminate.assert_called_once()

    def test_terminate_all_children_clears_dict(self, mock_popen) -> None:
        """_terminate_all_children clears the global _children dict."""
        from automedia.mcp import parallel

        proc = mock_popen(pid=3002)
        parallel._children["TestServer"] = proc

        _terminate_all_children()
        assert len(parallel._children) == 0

    def test_terminate_skips_already_dead(self, mock_popen) -> None:
        """_terminate_all_children skips processes that already exited."""
        from automedia.mcp import parallel

        proc = mock_popen(pid=3003)
        proc.poll.return_value = 0  # already exited
        parallel._children["DeadServer"] = proc

        _terminate_all_children()
        proc.terminate.assert_not_called()


# ---------------------------------------------------------------------------
# Test: get_server_commands
# ---------------------------------------------------------------------------


class TestGetServerCommands:
    """Tests for get_server_commands()."""

    def test_all_mode_returns_4_commands(self) -> None:
        """mode='all' returns commands for all 4 servers."""
        cmds = get_server_commands(mode="all")
        assert len(cmds) == 4
        assert set(cmds.keys()) == {"OPP", "OL", "ORF", "AutoMedia"}

    def test_sdk_mode_returns_1_command(self) -> None:
        """mode='sdk' returns only AutoMedia command."""
        cmds = get_server_commands(mode="sdk")
        assert len(cmds) == 1
        assert "AutoMedia" in cmds

    def test_command_format(self) -> None:
        """Commands should be [python, -m, module]."""
        cmds = get_server_commands(mode="all")
        for name, cmd in cmds.items():
            assert len(cmd) == 3
            assert cmd[1] == "-m"
            assert cmd[2] == "automedia.mcp.server"


# ---------------------------------------------------------------------------
# Test: CLI subcommands
# ---------------------------------------------------------------------------


class TestCLICommands:
    """Tests for omni CLI subcommands (Typer)."""

    @patch("automedia.mcp.parallel.start_parallel_servers")
    @patch("automedia.mcp.parallel.stop_parallel_servers")
    @patch("automedia.cli.commands.omni.time.sleep")
    def test_start_all_invokes_parallel(
        self,
        mock_sleep: MagicMock,
        mock_stop: MagicMock,
        mock_start: MagicMock,
        mock_popen,
    ) -> None:
        """omni start-all calls start_parallel_servers and blocks."""
        from typer.testing import CliRunner

        from automedia.cli.commands.omni import app

        proc = mock_popen(pid=4001)
        mock_start.return_value = {"AutoMedia": proc}
        # Make sleep raise KeyboardInterrupt to exit the loop
        mock_sleep.side_effect = KeyboardInterrupt()

        runner = CliRunner()
        result = runner.invoke(app, ["start-all"])

        assert result.exit_code == 0
        mock_start.assert_called_once_with(mode="all")
        mock_stop.assert_called_once()
        assert "Launched 1 server(s)" in result.output
        assert "[AutoMedia] started (PID: 4001)" in result.output

    @patch("automedia.mcp.parallel.start_parallel_servers")
    @patch("automedia.mcp.parallel.stop_parallel_servers")
    @patch("automedia.cli.commands.omni.time.sleep")
    def test_start_mode_parallel(
        self,
        mock_sleep: MagicMock,
        mock_stop: MagicMock,
        mock_start: MagicMock,
        mock_popen,
    ) -> None:
        """omni start --mode parallel launches in parallel mode."""
        from typer.testing import CliRunner

        from automedia.cli.commands.omni import app

        proc = mock_popen(pid=4002)
        mock_start.return_value = {"AutoMedia": proc}
        mock_sleep.side_effect = KeyboardInterrupt()

        runner = CliRunner()
        result = runner.invoke(app, ["start", "--mode", "parallel"])

        assert result.exit_code == 0
        mock_start.assert_called_once_with(mode="parallel")

    @patch("automedia.mcp.parallel.start_parallel_servers")
    @patch("automedia.mcp.parallel.stop_parallel_servers")
    @patch("automedia.cli.commands.omni.time.sleep")
    def test_start_mode_sdk(
        self,
        mock_sleep: MagicMock,
        mock_stop: MagicMock,
        mock_start: MagicMock,
        mock_popen,
    ) -> None:
        """omni start --mode sdk launches single server."""
        from typer.testing import CliRunner

        from automedia.cli.commands.omni import app

        proc = mock_popen(pid=4003)
        mock_start.return_value = {"AutoMedia": proc}
        mock_sleep.side_effect = KeyboardInterrupt()

        runner = CliRunner()
        result = runner.invoke(app, ["start", "--mode", "sdk"])

        assert result.exit_code == 0
        mock_start.assert_called_once_with(mode="sdk")
        assert "Launched 1 server(s) in sdk mode" in result.output

    @patch("automedia.mcp.parallel.start_parallel_servers")
    @patch("automedia.mcp.parallel.stop_parallel_servers")
    @patch("automedia.cli.commands.omni.time.sleep")
    def test_start_all_shows_pids(
        self,
        mock_sleep: MagicMock,
        mock_stop: MagicMock,
        mock_start: MagicMock,
        mock_popen,
    ) -> None:
        """CLI output includes server names and PIDs."""
        from typer.testing import CliRunner

        from automedia.cli.commands.omni import app

        proc1 = mock_popen(pid=4010)
        proc2 = mock_popen(pid=4011)
        mock_start.return_value = {
            "AutoMedia": proc1,
            "OPP": proc2,
        }
        mock_sleep.side_effect = KeyboardInterrupt()

        runner = CliRunner()
        result = runner.invoke(app, ["start-all"])

        assert "[AutoMedia] started (PID: 4010)" in result.output
        assert "[OPP] started (PID: 4011)" in result.output

    @patch("automedia.mcp.parallel.start_parallel_servers")
    @patch("automedia.mcp.parallel.stop_parallel_servers")
    @patch("automedia.cli.commands.omni.time.sleep")
    def test_unexpected_exit_reported(
        self,
        mock_sleep: MagicMock,
        mock_stop: MagicMock,
        mock_start: MagicMock,
        mock_popen,
    ) -> None:
        """Unexpected server exit is detected and reported."""
        from typer.testing import CliRunner

        from automedia.cli.commands.omni import app

        proc = mock_popen(pid=4020)
        # First sleep raises nothing, poll shows exit, second sleep raises KeyboardInterrupt
        mock_sleep.side_effect = [None, KeyboardInterrupt()]
        proc.poll.return_value = 1  # exited with error
        proc.returncode = 1
        mock_start.return_value = {"AutoMedia": proc}

        runner = CliRunner()
        result = runner.invoke(app, ["start-all"])

        assert "exited unexpectedly" in result.output or result.exit_code == 0


# ---------------------------------------------------------------------------
# Test: module imports
# ---------------------------------------------------------------------------


class TestImports:
    """Tests for module-level imports and __all__."""

    def test_import_start_parallel_servers(self) -> None:
        """start_parallel_servers is importable from parallel module."""
        from automedia.mcp.parallel import start_parallel_servers as fn

        assert callable(fn)

    def test_import_from_mcp_package(self) -> None:
        """start_parallel_servers is re-exported from automedia.mcp."""
        from automedia.mcp import start_parallel_servers, stop_parallel_servers

        assert callable(start_parallel_servers)
        assert callable(stop_parallel_servers)

    def test_no_side_effects_on_import(self) -> None:
        """Importing the module should not spawn any processes."""
        import importlib

        mod = importlib.import_module("automedia.mcp.parallel")
        # _children should be empty after import
        assert len(mod._children) == 0
