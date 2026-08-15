"""Renders a URL in a sandboxed, throwaway headless-browser context to take
a screenshot. This is the only part of urlpeek that executes the page's
JavaScript — everything about the context is disposable and locked down:
no persistent storage, no permissions granted, downloads blocked, dialogs
auto-dismissed, and it never clicks or navigates anywhere on its own.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

DEFAULT_VIEWPORT = {"width": 1280, "height": 800}
DEFAULT_TIMEOUT_MS = 15000
USER_AGENT = "urlpeek/0.1 (safety preview tool; not a browser)"


def _find_chromium_executable() -> str | None:
    """Locate a pre-installed Chromium binary, bypassing Playwright's own
    revision auto-selection (which can point at a headless-shell build that
    wasn't downloaded when the package version and pre-installed browser
    cache drift apart)."""
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    for base in filter(None, [browsers_path, os.path.expanduser("~/.cache/ms-playwright")]):
        matches = sorted(glob.glob(os.path.join(base, "chromium-*", "chrome-linux", "chrome")))
        if matches:
            return matches[-1]
    return None


@dataclass
class RenderResult:
    screenshot_path: str | None = None
    final_url: str | None = None
    third_party_domains: set[str] = field(default_factory=set)
    downloads_blocked: bool = False
    error: str | None = None


def render_preview(
    url: str,
    output_path: str,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    full_page: bool = False,
) -> RenderResult:
    result = RenderResult()

    with sync_playwright() as pw:
        executable_path = _find_chromium_executable()
        launch_kwargs = {"headless": True}
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            viewport=DEFAULT_VIEWPORT,
            user_agent=USER_AGENT,
            ignore_https_errors=True,
            accept_downloads=False,
            permissions=[],
            java_script_enabled=True,
        )
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page.on("dialog", lambda dialog: dialog.dismiss())

        def _on_request(req):
            host = urlparse(req.url).hostname
            if host:
                result.third_party_domains.add(host)

        page.on("request", _on_request)

        try:
            page.goto(url, wait_until="load", timeout=timeout_ms)
            page.wait_for_timeout(500)  # let obviously-async content settle
            result.final_url = page.url
            page.screenshot(path=output_path, full_page=full_page)
            result.screenshot_path = output_path
        except Exception as exc:  # noqa: BLE001 - report, never crash the preview
            message = str(exc)
            if "download" in message.lower():
                result.downloads_blocked = True
            result.error = message
        finally:
            context.close()
            browser.close()

    return result
