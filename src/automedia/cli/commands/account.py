"""``automedia account`` — PRD-4 account management CLI commands."""

from __future__ import annotations

import builtins
import sys
import threading
import time
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

import typer
from rich.console import Console
from rich.table import Table

from automedia.accounts.models import AccountInfo
from automedia.accounts.registry import AccountRegistry

app = typer.Typer(help="Manage platform accounts for publishing.")
console = Console(width=200)

_registry: AccountRegistry | None = None


def _get_registry() -> AccountRegistry:
    """Lazily initialised AccountRegistry singleton."""
    global _registry  # intentional module-level lazy init
    if _registry is None:
        _registry = AccountRegistry()
    return _registry


# ---------------------------------------------------------------------------
# Interactive login capture (browser automation → encrypted cookie store)
# ---------------------------------------------------------------------------

#: Per-platform login entry point and the cookie whose appearance proves a
#: logged-in session. Platforms without an entry rely on the user pressing
#: Enter after logging in.
_LOGIN_TARGETS: dict[str, dict[str, str]] = {
    "xiaohongshu": {
        "url": "https://www.xiaohongshu.com",
        "session_cookie": "web_session",
    },
}

#: A plain, current desktop-Chrome UA. Stored alongside the cookies so the
#: publish engine can reuse the same identity the session was issued to.
_CAPTURE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _cookie_string(cookies: Sequence[dict[str, Any]]) -> str:
    """Serialize Playwright cookies into a ``name=value; …`` header string."""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name"))


class _EvaluablePage(Protocol):
    """Minimal shape of a Playwright Page used by the login check."""

    def evaluate(self, script: str) -> bool: ...


def _login_signal(platform: str, cookies: Sequence[dict[str, Any]]) -> bool:
    """Return True when the platform's session cookie has appeared.

    Weak signal only: some platforms (e.g. Xiaohongshu) hand a ``web_session``
    cookie to anonymous visitors too, so callers combine this with
    :func:`_login_confirmed` (the login UI being gone) when both are
    available.
    """
    marker = _LOGIN_TARGETS.get(platform, {}).get("session_cookie")
    if not marker:
        return False
    return any(c.get("name") == marker and c.get("value") for c in cookies)


def _login_confirmed(
    platform: str, page: _EvaluablePage, cookies: Sequence[dict[str, Any]]
) -> bool:
    """Strong login signal: session cookie present AND the login UI is gone.

    Falls back to the cookie-only signal when the page cannot be inspected.
    """
    if not _login_signal(platform, cookies):
        return False
    try:
        modal_gone = page.evaluate(
            """() => {
                const sel = ['.login-container', '.sign-container', '.login-modal'];
                return !sel.some((s) => document.querySelector(s));
            }"""
        )
    except Exception:
        return True
    return bool(modal_gone)


def _capture_browser_cookies(platform: str, url: str, timeout_s: int) -> dict[str, Any]:
    """Open a headed Chromium, wait for the user to log in, return a storage state.

    Returns Playwright's ``storage_state()`` (cookies **plus** localStorage
    origins — some platforms bind the session to localStorage, so a
    cookies-only replay shows the login modal again).

    Blocks until the strong login signal (see :func:`_login_confirmed`) or —
    for platforms without a known signal cookie — until the user presses
    Enter in the terminal. Raises ``TimeoutError`` if neither happens within
    *timeout_s*.
    """
    from playwright.sync_api import sync_playwright

    console.print(
        f"[bold]Opening a browser window — log in to {platform} inside it (QR or password).[/bold]"
    )
    console.print(f"  Waiting up to {timeout_s}s for a confirmed login…")

    enter_pressed = threading.Event()

    def _wait_for_enter() -> None:
        try:
            input()
            enter_pressed.set()
        except EOFError:
            pass

    signal_known = platform in _LOGIN_TARGETS
    if not signal_known:
        typer.echo(
            "  (No known session cookie for this platform — "
            "press Enter here after you finish logging in.)"
        )
        threading.Thread(target=_wait_for_enter, daemon=True).start()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(user_agent=_CAPTURE_UA)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")

        deadline = time.monotonic() + timeout_s
        state: dict[str, Any] = {}

        try:
            while time.monotonic() < deadline:
                cookies = context.cookies()
                if _login_confirmed(platform, page, cookies) or (
                    not signal_known and enter_pressed.is_set()
                ):
                    state = context.storage_state()
                    break
                page.wait_for_timeout(2000)
            else:
                raise TimeoutError(
                    f"Login not detected within {timeout_s}s — "
                    "no confirmed login (session cookie + login UI gone)"
                )
        finally:
            context.close()
            browser.close()

    if not state.get("cookies"):
        raise RuntimeError("Browser closed without capturing any session state")
    return state


@app.command("login-capture")
def login_capture(
    platform: str = typer.Argument(..., help="Platform name, e.g. xiaohongshu"),
    url: str = typer.Option(
        "", "--url", help="Login page URL (defaults to the platform's known entry point)"
    ),
    label: str = typer.Option("", "--label", help="Human-readable account label"),
    timeout: int = typer.Option(
        300, "--timeout", help="Max seconds to wait for the interactive login"
    ),
) -> None:
    """Capture a login session via a real browser into the encrypted account store.

    A headed Chromium window opens on this machine; log in inside it (QR scan
    or password). When the platform's session cookie appears, the cookies are
    stored (AES-256-GCM) and the browser closes automatically. Cookie values
    are never printed.
    """
    target = _LOGIN_TARGETS.get(platform, {})
    login_url = url or target.get("url", "")
    if not login_url:
        console.print(f"[red]No known login URL for {platform!r} — pass one with --url.[/red]")
        raise typer.Exit(1)

    try:
        state = _capture_browser_cookies(platform, login_url, timeout)
    except TimeoutError as exc:
        console.print(f"[red]Login capture failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ImportError as exc:
        console.print(
            "[red]playwright is not installed.[/red] Run:\n"
            "  pip install playwright\n"
            "  playwright install chromium\n"
            f"({exc})"
        )
        raise typer.Exit(1) from exc

    account_label = label or f"browser-{platform}-{datetime.now().strftime('%Y%m%d-%H%M')}"
    state_cookies = state.get("cookies", [])
    credentials: dict[str, Any] = {
        # Full Playwright storage state (cookies + localStorage origins) —
        # the replay-proof form. `cookies`/`cookie_string` stay for callers
        # that only need the header form.
        "storage_state": state,
        "cookies": state_cookies,
        "cookie_string": _cookie_string(state_cookies),
        "user_agent": _CAPTURE_UA,
        "login_url": login_url,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        meta = _get_registry().register(
            platform, credentials, label=account_label, auth_type="cookie"
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    console.print(
        f"[green]Login captured[/green]: account [bold]{meta['account_id']}[/bold] "
        f"({platform}, {len(state_cookies)} cookies, auth=cookie) — encrypted at rest."
    )
    console.print("  Cookie values are stored encrypted; nothing was printed.")


def _parse_cred_payload(cred: list[str], from_json: str) -> dict[str, str]:
    """Build the credential payload from --cred k=v pairs or a JSON file.

    Values are never echoed; only keys are shown on errors.
    """
    payload: dict[str, str] = {}
    if cred:
        for pair in cred:
            key, sep, value = pair.partition("=")
            if not sep or not key.strip():
                hint = key.strip() or "<empty>"
                raise ValueError(f"invalid --cred entry {hint}=… (expected key=value)")
            payload[key.strip()] = value
    if from_json:
        if payload:
            raise ValueError("use either --cred or --from-json, not both")
        import json

        try:
            with open(from_json, encoding="utf-8") as fh:
                loaded = json.load(fh)
        except OSError as exc:
            raise ValueError(f"cannot read {from_json}: {exc}") from exc
        if not isinstance(loaded, dict) or not all(isinstance(k, str) for k in loaded):
            raise ValueError("credential JSON must be an object with string keys")
        payload = {k: str(v) for k, v in loaded.items()}
    if not payload:
        raise ValueError("no credentials given — use --cred key=value or --from-json <file>")
    return payload


def _register_or_exit(
    platform: str, payload: dict[str, str], label: str, auth_type: str
) -> AccountInfo:
    try:
        return _get_registry().register(platform, payload, label=label, auth_type=auth_type)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command()
def connect(
    platform: str = typer.Argument(..., help="Platform name (wechat, zhihu, ...)"),
    auth_type: str = typer.Option("api_key", "--auth-type", help="Authentication type"),
    label: str = typer.Option("", "--label", help="Human-readable label"),
) -> None:
    """Register a new platform account."""
    console.print(f"[bold]Connecting {platform} account...[/bold]")
    console.print("Enter credentials as key=value pairs (one per line, empty line to finish):")

    credentials: dict[str, str] = {}
    while True:
        sys.stdout.write("  ")
        sys.stdout.flush()
        line = sys.stdin.readline()
        if not line or not line.strip():
            break
        if "=" in line:
            key, _, value = line.partition("=")
            credentials[key.strip()] = value.strip()

    if not credentials:
        console.print("[red]No credentials provided. Aborting.[/red]")
        raise typer.Exit(1)

    try:
        meta = _get_registry().register(platform, credentials, label=label, auth_type=auth_type)
        console.print(f"[green]Account registered: [bold]{meta['account_id']}[/bold]")
        console.print(f"  Platform: {meta['platform']}")
        console.print(f"  Label: {meta.get('label', '')}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e


@app.command("list")
def list_accounts(
    platform: str | None = typer.Option(None, "--platform", "-p", help="Filter by platform"),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
) -> None:
    """List registered accounts."""
    accounts = _get_registry().list(platform=platform, status=status)

    if not accounts:
        console.print("[yellow]No accounts found.[/yellow]")
        return

    table = Table(title="Platform Accounts")
    table.add_column("ID", style="cyan")
    table.add_column("Platform", style="green")
    table.add_column("Label", style="white")
    table.add_column("Auth Type", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Last Used", style="magenta")

    for acc in accounts:
        table.add_row(
            acc.get("account_id", ""),
            acc.get("platform", ""),
            acc.get("label", ""),
            acc.get("auth_type", ""),
            acc.get("status", ""),
            str(acc.get("last_used", "")),
        )

    console.print(table)


@app.command()
def health(
    account_id: str = typer.Argument(..., help="Account ID"),
) -> None:
    """Check account session health."""
    info = _get_registry().get(account_id)
    if not info:
        console.print(f"[red]Account not found: {account_id}[/red]")
        raise typer.Exit(1)

    console.print(f"Account: [bold]{account_id}[/bold]")
    console.print(f"Platform: {info.get('platform', '')}")
    console.print(f"Label: {info.get('label', '')}")
    console.print(f"Status: {info.get('status', '')}")
    console.print(f"Last Health Check: {info.get('last_health_check', 'Never')}")

    if info.get("status") == "active":
        console.print("[green]Account is active[/green]")
    else:
        console.print(f"[yellow]Account status: {info.get('status', 'unknown')}[/yellow]")


@app.command()
def disconnect(
    account_id: str = typer.Argument(..., help="Account ID to disconnect"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove a platform account."""
    info = _get_registry().get(account_id)
    if not info:
        console.print(f"[red]Account not found: {account_id}[/red]")
        raise typer.Exit(1)

    if not yes:
        console.print(
            f"About to disconnect: [bold]{account_id}[/bold] "
            f"({info.get('platform', '')} - {info.get('label', '')})"
        )
        confirm = typer.confirm("Are you sure?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            return

    _get_registry().delete(account_id)
    console.print(f"[green]Account disconnected: {account_id}[/green]")


@app.command()
def add(
    platform: str = typer.Argument(..., help="Platform name (wechat, zhihu, ...)"),
    cred: builtins.list[str] = typer.Option(
        [], "--cred", help="Credential as key=value (repeatable, non-interactive)"
    ),
    from_json: str = typer.Option(
        "", "--from-json", help="Credential payload as a JSON object file"
    ),
    auth_type: str = typer.Option("api_key", "--auth-type", help="Authentication type"),
    label: str = typer.Option("", "--label", help="Human-readable label"),
) -> None:
    """Register an account non-interactively (script/agent friendly)."""
    try:
        payload = _parse_cred_payload(list(cred), from_json)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    meta = _register_or_exit(platform, payload, label, auth_type)
    console.print(
        f"[green]Account registered:[/green] [bold]{meta['account_id']}[/bold] "
        f"({platform}, auth={auth_type}, keys: {', '.join(sorted(payload))})"
    )


@app.command()
def rotate(
    account_id: str = typer.Argument(..., help="Account ID to rotate credentials for"),
    cred: builtins.list[str] = typer.Option(
        [], "--cred", help="New credential as key=value (repeatable)"
    ),
    from_json: str = typer.Option("", "--from-json", help="New credential payload as a JSON file"),
) -> None:
    """Replace an account's credentials, keeping its identity and history."""
    try:
        payload = _parse_cred_payload(list(cred), from_json)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    meta = _get_registry().rotate_credentials(account_id, payload)
    if meta is None:
        console.print(f"[red]Account not found: {account_id}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]Credentials rotated[/green]: [bold]{account_id}[/bold] "
        f"(new fingerprint {str(meta.get('fingerprint', ''))[:12]}…; "
        "identity/label/history preserved)"
    )


@app.command()
def remove(
    account_id: str = typer.Argument(..., help="Account ID to remove"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Remove a platform account (alias of ``disconnect``)."""
    info = _get_registry().get(account_id)
    if not info:
        console.print(f"[red]Account not found: {account_id}[/red]")
        raise typer.Exit(1)
    if not yes:
        confirm = typer.confirm(f"Remove account {account_id} ({info.get('platform', '')})?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            return
    _get_registry().delete(account_id)
    console.print(f"[green]Account removed: {account_id}[/green]")
