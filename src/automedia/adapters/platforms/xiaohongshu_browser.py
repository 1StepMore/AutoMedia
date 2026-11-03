"""Browser-automation publish for Xiaohongshu — Hard-platform support (#353).

Xiaohongshu has no public publish API. This module drives the creator
publish page with Playwright, using the login session captured by
``automedia account login-capture xiaohongshu`` (Playwright storage_state in
the encrypted account store).

**Hard boundary (user-authorized):** the flow fills the form — title, body,
images — and stops immediately before the publish confirmation. It NEVER
clicks publish; the final state is a screenshot + a
``status="ready_for_confirmation"`` result for the human to take over.

Single-attempt semantics: session expiry, risk-control interstitials and
element timeouts return structured errors with a manual-takeover hint. No
blind retries (platform risk controls punish rapid automation).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol


class _EvaluablePage(Protocol):
    """Minimal page shape used by the login check."""

    def evaluate(self, script: str) -> bool: ...


class _Locator(Protocol):
    """Minimal locator shape used by selector probing."""

    def wait_for(self, state: str, timeout: int) -> None: ...

    def fill(self, value: str) -> None: ...

    def click(self) -> None: ...

    def type(self, value: str, delay: int) -> None: ...

    def set_input_files(self, files: list[str]) -> None: ...


class _LocatablePage(Protocol):
    """Minimal page shape used by selector probing."""

    def locator(self, selector: str) -> _Locator: ...


logger = logging.getLogger(__name__)

CREATOR_PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?source=official"

#: The publish button is intentionally NEVER clicked by automation.
#: Kept as a named constant so reviews/greps can verify the boundary.
_PUBLISH_BUTTON_SELECTORS: tuple[str, ...] = (
    ".publishBtn",
    "button.css-1q6pgqz",
    "text=发布",
)

_TITLE_SELECTORS: tuple[str, ...] = (
    "#title-textinput input",
    "input[placeholder*='标题']",
    ".titleInput input",
    "#c-title input",
)

_BODY_SELECTORS: tuple[str, ...] = (
    "#post-textarea .ql-editor",
    ".ql-editor[contenteditable='true']",
    "#editor .ql-editor",
    "div[contenteditable='true']",
)

_UPLOAD_SELECTORS: tuple[str, ...] = (
    "input[type='file']",
    ".upload-input input[type='file']",
)

_LOGIN_URL_MARKERS: tuple[str, ...] = ("login", "passport", "signin")

_TIMEOUT_MS_DEFAULT: int = 90_000


class BrowserPublishError(RuntimeError):
    """Structured browser-publish failure with a manual-takeover hint."""


def load_session(account_id: str | None = None) -> dict[str, Any]:
    """Load the captured browser session (storage_state + UA) from accounts.

    Raises
    ------
    BrowserPublishError
        When no xiaohongshu cookie session exists — the caller surfaces
        ``rerun automedia account login-capture xiaohongshu``.
    """
    from automedia.accounts.registry import AccountRegistry

    registry = AccountRegistry()
    accounts = registry.list(platform="xiaohongshu", status="active")
    target = None
    if account_id:
        target = next((a for a in accounts if a["account_id"] == account_id), None)
    else:
        target = accounts[0] if accounts else None
    if target is None:
        raise BrowserPublishError(
            "no active xiaohongshu browser session in the account store — "
            "rerun: automedia account login-capture xiaohongshu"
        )
    creds = registry.get_credentials(target["account_id"]) or {}
    storage_state = creds.get("storage_state")
    if not storage_state:
        raise BrowserPublishError(
            f"account {target['account_id']} has no storage_state — "
            "rerun: automedia account login-capture xiaohongshu"
        )
    return {"storage_state": storage_state, "user_agent": creds.get("user_agent") or None}


def _is_login_page(url: str, page: _EvaluablePage) -> bool:
    if any(marker in url.lower() for marker in _LOGIN_URL_MARKERS):
        return True
    probe = "'.login-container, .sign-container, #login-container'"
    try:
        return bool(page.evaluate(f"() => !!document.querySelector({probe})"))
    except Exception:
        return False


def _first_attached(
    page: _LocatablePage, selectors: tuple[str, ...], timeout_ms: int
) -> _Locator | None:
    """Return the first locator present in the DOM (not necessarily visible).

    File inputs are opacity-0 by design — "visible" never fires for them.
    """
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="attached", timeout=timeout_ms)
            return loc
        except Exception as exc:
            logger.debug("attached probe failed", selector=sel, error=str(exc))
            continue
    return None


def _first_visible(
    page: _LocatablePage, selectors: tuple[str, ...], timeout_ms: int
) -> _Locator | None:
    """Return the first locator that becomes visible, or None."""
    deadline_selectors = list(selectors)
    for sel in deadline_selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            return loc
        except Exception as exc:
            logger.debug("selector probe failed", selector=sel, error=str(exc))
            continue
    return None


def prepare_xiaohongshu_note(
    title: str,
    body: str,
    image_paths: list[str],
    screenshot_path: str,
    *,
    headless: bool = True,
    account_id: str | None = None,
    timeout_ms: int = _TIMEOUT_MS_DEFAULT,
) -> dict[str, Any]:
    """Fill the Xiaohongshu note form and stop before publishing.

    Returns a :class:`~automedia.adapters.base.PublishResult`-shaped dict
    with ``status="ready_for_confirmation"`` and the ``screenshot`` path.
    Raises nothing — failures come back as ``status="error"`` with a
    ``reason`` carrying the manual-takeover hint.
    """
    result: dict[str, Any] = {
        "platform": "xiaohongshu",
        "status": "error",
        "reason": "",
        "screenshot": "",
    }
    session: dict[str, Any] = {}
    try:
        session = load_session(account_id)
    except BrowserPublishError as exc:
        result["reason"] = str(exc)
        return result

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context(
                storage_state=session["storage_state"],
                **({"user_agent": session["user_agent"]} if session["user_agent"] else {}),
            )
            page = context.new_page()
            page.goto(CREATOR_PUBLISH_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(3000)

            if _is_login_page(page.url, page):
                context.close()
                browser.close()
                result["reason"] = (
                    "session expired — creator page redirected to login; "
                    "rerun: automedia account login-capture xiaohongshu"
                )
                return result

            # The creator page defaults to the 上传视频 tab — a note needs the
            # 上传图文 tab first (its upload input + title/body form).
            # the visible tab lives in the header strip (.creator-tab);
            # bare text matches hit hidden sidebar duplicates off-viewport
            tab = page.locator("div.creator-tab", has_text="上传图文").first
            try:
                # dispatch_event: the SPA ignores real pointer events here
                # (invisible overlay intercepts hit-testing); a native click
                # event on the element is what the Vue handler binds to
                tab.dispatch_event("click")
                page.wait_for_timeout(2500)
            except Exception as exc:
                logger.debug("note-tab click failed", error=str(exc))

            # File inputs are intentionally invisible (opacity-0) — wait for
            # ATTACHED, not visible, then hand the file straight over.
            upload_ok = False
            for img in image_paths:
                upload = _first_attached(page, _UPLOAD_SELECTORS, timeout_ms // 3)
                if upload is None:
                    break
                upload.set_input_files(os.path.abspath(img))
                upload_ok = True
                page.wait_for_timeout(3000)

            # The editor (title/body) only renders AFTER images are attached.
            if upload_ok:
                page.wait_for_timeout(3000)
                # dismiss the first-time editor onboarding dialog if present
                try:
                    page.locator("text=我知道了").first.click(timeout=3000)
                    page.wait_for_timeout(800)
                except Exception as exc:
                    logger.debug("onboarding dialog absent", error=str(exc))

            title_loc = _first_visible(page, _TITLE_SELECTORS, timeout_ms // 3)
            if title_loc is not None:
                title_loc.fill(title)
            else:
                result["reason"] = (
                    "title input not found — page structure changed; manual takeover required"
                )

            body_loc = _first_visible(page, _BODY_SELECTORS, timeout_ms // 3)
            if body_loc is not None:
                body_loc.click()
                body_loc.type(body, delay=10)
            elif not result["reason"]:
                result["reason"] = (
                    "body editor not found — page structure changed; manual takeover required"
                )

            os.makedirs(os.path.dirname(os.path.abspath(screenshot_path)), exist_ok=True)
            page.screenshot(path=screenshot_path, full_page=True)
            result["screenshot"] = os.path.abspath(screenshot_path)

            # HARD BOUNDARY: stop here. The publish button is never clicked —
            # a human reviews the screenshot and publishes manually.
            if not result["reason"]:
                result["status"] = "ready_for_confirmation"
                result["reason"] = (
                    "form filled — publish NOT clicked (human confirmation "
                    "required by policy); review the screenshot and publish manually"
                )

            context.close()
            browser.close()
    except Exception as exc:
        logger.warning("xiaohongshu browser publish failed", error=str(exc))
        result["status"] = "error"
        result["reason"] = (
            f"browser publish failed: {exc} — take over manually at {CREATOR_PUBLISH_URL}"
        )
    return result
