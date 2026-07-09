"""Parallel MCP server launcher — runs multiple MCP servers simultaneously.

Launches the main AutoMedia MCP server alongside adapter MCP servers
(OPP, OL, ORF) in parallel, each with independent stdio transport.

.. note::

   **Architectural debt (Issue 12, deferred):**  All four server definitions
   currently point to the same module (``automedia.mcp.server``).  In a future
   refactoring each adapter (OPP, OL, ORF) should ideally have its own
   dedicated server module so that the parallel deployment actually provides
   independent server instances.  For now the same process is started on
   different ports, which offers only a thin separation layer.

Usage::

    from automedia.mcp.parallel import start_parallel_servers

    # Launch all 4 servers
    servers = start_parallel_servers()          # reads mode from config
    servers = start_parallel_servers(mode="all")  # explicit override

    # Later, shut down gracefully
    stop_parallel_servers(servers)
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
from typing import Any

from automedia.omni.config import load_omni_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server definitions
# ---------------------------------------------------------------------------

# NOTE: All four servers currently point to the same module.
# See module-level docstring "Architectural debt (Issue 12)".
_SERVER_DEFS: dict[str, dict[str, Any]] = {
    "OPP": {
        "module": "automedia.mcp.server",
        "port": 8101,
        "description": "OPP adapter MCP server",
    },
    "OL": {
        "module": "automedia.mcp.server",
        "port": 8102,
        "description": "OL adapter MCP server",
    },
    "ORF": {
        "module": "automedia.mcp.server",
        "port": 8103,
        "description": "ORF adapter MCP server",
    },
    "AutoMedia": {
        "module": "automedia.mcp.server",
        "port": 8100,
        "description": "Main AutoMedia MCP server",
    },
}

# Subset launched per mode
_SUBSET_MODES: dict[str, list[str]] = {
    "all": ["AutoMedia", "OPP", "OL", "ORF"],
    "proxy": ["AutoMedia", "OPP", "OL", "ORF"],
    "parallel": ["AutoMedia", "OPP", "OL", "ORF"],
    "sdk": ["AutoMedia"],
}

# Track children globally for signal handlers
_children: dict[str, subprocess.Popen[bytes]] = {}


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------


def _terminate_all_children() -> None:
    """Terminate all tracked child processes gracefully."""
    for name, proc in list(_children.items()):
        if proc.poll() is None:
            logger.info("Terminating [%s] PID %d", name, proc.pid)
            try:
                proc.terminate()
            except OSError:
                pass
    # Wait briefly for graceful shutdown, then force-kill survivors
    for name, proc in list(_children.items()):
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Force-killing [%s] PID %d", name, proc.pid)
            try:
                proc.kill()
            except OSError:
                pass
    _children.clear()


def _signal_handler(signum: int, frame: Any) -> None:
    """Signal handler that terminates all children and exits."""
    logger.info("Received signal %d — shutting down all servers", signum)
    _terminate_all_children()
    raise SystemExit(0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_parallel_servers(mode: str | None = None) -> dict[str, subprocess.Popen[bytes]]:
    """Launch MCP server processes in parallel.

    Parameters
    ----------
    mode:
        Which servers to launch.  ``"all"`` launches every server.
        ``"parallel"`` and ``"proxy"`` launch all four.
        ``"sdk"`` launches only the main AutoMedia server.
        When ``None`` (default), the mode is resolved from
        ``omni_config.yaml`` ``integration_mode``, falling back to
        ``"all"`` if the config is unavailable.

    Returns
    -------
    dict[str, subprocess.Popen[bytes]]
        Mapping of server name → ``Popen`` handle.
    """
    global _children
    _children.clear()

    # Resolve mode from config when not explicitly provided
    if mode is None:
        _config = load_omni_config()
        mode = _config.integration_mode if _config.integration_mode != "sdk" else "all"

    # Determine which servers to launch
    names = _SUBSET_MODES.get(mode, _SUBSET_MODES["all"])

    # Register signal handlers for graceful shutdown
    _install_signal_handlers()

    for name in names:
        defn = _SERVER_DEFS[name]
        cmd = [
            sys.executable,
            "-m",
            defn["module"],
        ]
        logger.info("Starting [%s] — %s (port %d)", name, defn["description"], defn["port"])

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _children[name] = proc
        logger.info("[%s] started (PID: %d)", name, proc.pid)

    return dict(_children)


def stop_parallel_servers(servers: dict[str, subprocess.Popen[bytes]]) -> None:
    """Terminate all running server processes.

    Parameters
    ----------
    servers:
        Mapping returned by :func:`start_parallel_servers`.
    """
    for name, proc in servers.items():
        if proc.poll() is None:
            logger.info("Stopping [%s] PID %d", name, proc.pid)
            try:
                proc.terminate()
            except OSError:
                pass
    for name, proc in servers.items():
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Force-killing [%s] PID %d", name, proc.pid)
            try:
                proc.kill()
            except OSError:
                pass


def get_server_commands(mode: str | None = None) -> dict[str, list[str]]:
    """Return the commands that would be launched for a given mode.

    Useful for dry-run / debugging without actually spawning processes.

    Parameters
    ----------
    mode:
        Server selection mode (same semantics as
        :func:`start_parallel_servers`).  ``None`` resolves from config.

    Returns
    -------
    dict[str, list[str]]
        Mapping of server name → command list.
    """
    if mode is None:
        _config = load_omni_config()
        mode = _config.integration_mode if _config.integration_mode != "sdk" else "all"
    names = _SUBSET_MODES.get(mode, _SUBSET_MODES["all"])
    return {
        name: [sys.executable, "-m", _SERVER_DEFS[name]["module"]]
        for name in names
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_signal_handlers_installed = False


def _install_signal_handlers() -> None:
    """Install signal handlers once (idempotent)."""
    global _signal_handlers_installed
    if _signal_handlers_installed:
        return
    _signal_handlers_installed = True

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
