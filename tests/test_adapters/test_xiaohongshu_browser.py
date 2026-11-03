"""Tests for the Xiaohongshu browser publish flow (#353).

Playwright is faked end to end — the E2E against the real creator page runs
out-of-band (single attempt, stops before the publish confirmation).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from automedia.adapters.platforms import xiaohongshu_browser as xb
from automedia.adapters.platforms.xiaohongshu_browser import (
    BrowserPublishError,
    load_session,
    prepare_xiaohongshu_note,
)


class _FakeLocator:
    def __init__(self, page: _FakePage, selector: str) -> None:
        self._page = page
        self._selector = selector
        # playwright locators expose `.first` — the code under test uses it
        self.first = self

    def wait_for(self, state: str, timeout: int) -> None:
        if self._selector in self._page.missing_selectors:
            raise TimeoutError(f"not visible: {self._selector}")
        self._page.filled.setdefault(self._selector, 0)
        self._page.filled[self._selector] += 1

    def fill(self, value: str) -> None:
        self._page.typed.append((self._selector, value))

    def click(self) -> None:
        self._page.clicked.append(self._selector)

    def type(self, value: str, delay: int) -> None:
        self._page.typed.append((self._selector, value))

    def set_input_files(self, files: str | list[str]) -> None:
        self._page.uploads.extend([files] if isinstance(files, str) else files)

    def dispatch_event(self, event: str) -> None:
        self._page.dispatched.append((self._selector, event))


class _FakePage:
    def __init__(
        self, url: str, missing_selectors: set[str] | None = None, login_modal: bool = False
    ) -> None:
        self.url = url
        self.login_modal = login_modal
        self.missing_selectors = missing_selectors or set()
        self.filled: dict[str, int] = {}
        self.clicked: list[str] = []
        self.dispatched: list[tuple[str, str]] = []
        self.typed: list[tuple[str, str]] = []
        self.uploads: list[str] = []
        self.screenshots: list[str] = []

    def locator(self, selector: str, has_text: str | None = None) -> _FakeLocator:
        return _FakeLocator(self, selector)

    def evaluate(self, script: str) -> bool:
        return self.login_modal

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.goto_url = url

    def wait_for_timeout(self, ms: int) -> None:
        return None

    def screenshot(self, path: str, full_page: bool) -> None:
        with open(path, "wb") as fh:
            fh.write(b"png")
        self.screenshots.append(path)

    def close(self) -> None:
        return None


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.closed = False

    def new_page(self) -> _FakePage:
        return self._page

    def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, context: _FakeContext) -> None:
        self._context = context
        self.closed = False

    def new_context(self, **_: Any) -> _FakeContext:
        return self._context

    def close(self) -> None:
        self.closed = True


def _patch_playwright(page: _FakePage):
    context = _FakeContext(page)
    browser = _FakeBrowser(context)

    class _PW:
        def __init__(self) -> None:
            self.launched_headless: bool | None = None

        @property
        def chromium(self):
            return self

        def launch(self, headless: bool) -> _FakeBrowser:
            self.launched_headless = headless
            return browser

    pw = _PW()

    class _Sync:
        def __call__(self) -> _PW:
            return self

        def __enter__(self) -> _PW:
            return pw

        def __exit__(self, *a: Any) -> None:
            return None

    return patch("playwright.sync_api.sync_playwright", _Sync())


@pytest.fixture()
def _session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        xb,
        "load_session",
        lambda account_id=None: {"storage_state": {"cookies": []}, "user_agent": "UA/1"},
    )


class TestLoadSession:
    def test_no_accounts_gives_capture_hint(self) -> None:
        registry = MagicMock()
        registry.list.return_value = []
        with (
            patch("automedia.accounts.registry.AccountRegistry", return_value=registry),
            pytest.raises(BrowserPublishError, match="login-capture"),
        ):
            load_session()

    def test_account_without_storage_state_hinted(self) -> None:
        registry = MagicMock()
        registry.list.return_value = [{"account_id": "acc_x", "platform": "xiaohongshu"}]
        registry.get_credentials.return_value = {"cookie_string": "a=1"}
        with (
            patch("automedia.accounts.registry.AccountRegistry", return_value=registry),
            pytest.raises(BrowserPublishError, match="storage_state"),
        ):
            load_session()


class TestPrepareNote:
    def test_fills_form_and_stops_before_publish(self, tmp_path: Any, _session: None) -> None:
        page = _FakePage("https://creator.xiaohongshu.com/publish/publish?source=official")
        shot = str(tmp_path / "shot.png")
        img = tmp_path / "cover.png"
        img.write_bytes(b"png")

        with _patch_playwright(page):
            result = prepare_xiaohongshu_note("标题", "正文内容", [str(img)], shot, headless=True)

        assert result["status"] == "ready_for_confirmation", result["reason"]
        assert "NOT clicked" in result["reason"]
        assert result["screenshot"] == shot
        assert page.uploads == [str(img)]
        # the 图文 tab was switched via a dispatched click event
        assert ("div.creator-tab", "click") in page.dispatched
        # title + body were typed; the publish button was NEVER clicked
        assert any("标题" in v for _, v in page.typed)
        assert any("正文内容" in v for _, v in page.typed)
        assert not any("publish" in sel.lower() for sel in page.clicked)

    def test_session_expiry_is_structured_error(self, tmp_path: Any, _session: None) -> None:
        page = _FakePage("https://creator.xiaohongshu.com/login?redirect=1", login_modal=True)
        with _patch_playwright(page):
            result = prepare_xiaohongshu_note("t", "b", [], str(tmp_path / "shot.png"))
        assert result["status"] == "error"
        assert "session expired" in result["reason"]
        assert "login-capture" in result["reason"]

    def test_missing_selectors_report_manual_takeover(self, tmp_path: Any, _session: None) -> None:
        page = _FakePage(
            "https://creator.xiaohongshu.com/publish/publish?source=official",
            missing_selectors={
                "#title-textinput input",
                "input[placeholder*='标题']",
                ".titleInput input",
                "#c-title input",
                "#post-textarea .ql-editor",
                ".ql-editor[contenteditable='true']",
                "div[contenteditable='true'].ql-editor",
                "input[type='file']",
                ".upload-input input[type='file']",
            },
        )
        with _patch_playwright(page):
            result = prepare_xiaohongshu_note("t", "b", [], str(tmp_path / "shot.png"))
        assert result["status"] == "error"
        assert "manual takeover" in result["reason"]

    def test_no_session_returns_error_without_playwright(self, tmp_path: Any) -> None:
        registry = MagicMock()
        registry.list.return_value = []
        with (
            patch("automedia.accounts.registry.AccountRegistry", return_value=registry),
            patch("playwright.sync_api.sync_playwright") as should_not_launch,
        ):
            result = prepare_xiaohongshu_note("t", "b", [], str(tmp_path / "shot.png"))
        assert result["status"] == "error"
        assert "login-capture" in result["reason"]
        should_not_launch.assert_not_called()
