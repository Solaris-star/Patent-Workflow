# -*- coding: utf-8 -*-
"""Minimal Playwright adapter for the public CNIPA search page.

The browser uses its ordinary defaults. If the site requests verification,
presents a captcha, or returns HTTP 403, the adapter stops immediately so the
batch caller can preserve partial results and choose another authorized source.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import Browser, BrowserContext, Error, Page, Playwright, sync_playwright

from cnipa_batch import ForbiddenError, SecurityStopError
from cnipa_epub_parse import EpubSearchHit, hits_to_jsonable, parse_search_result_html


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, TypeError, ValueError):
            pass


EPUB_BASE = "http://epub.cnipa.gov.cn/"


def _max_wait_sec() -> float:
    try:
        return max(0.0, min(float(os.environ.get("EPUB_WAF_MAX_WAIT_SEC", "180")), 300.0))
    except ValueError:
        return 180.0


def default_result_html_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return Path(__file__).resolve().parent / f"_last_result_{timestamp}.html"


def _raise_if_security_challenge(page: Page) -> None:
    try:
        text = page.locator("body").inner_text(timeout=1500).casefold()
    except Exception:
        text = ""
    if "403" in text or "forbidden" in text:
        raise ForbiddenError("CNIPA returned HTTP 403")
    markers = (
        "captcha", "security verification", "human verification", "verify you are",
        "验证码", "安全验证", "人机验证", "访问过于频繁", "访问频繁",
    )
    if any(marker in text for marker in markers):
        raise SecurityStopError("CNIPA requires security verification")


def wait_for_epub_home_ready(page: Page, *, max_wait_sec: float | None = None) -> None:
    limit = max_wait_sec if max_wait_sec is not None else _max_wait_sec()
    response = page.goto(EPUB_BASE, wait_until="load", timeout=120_000)
    if response is not None and response.status == 403:
        raise ForbiddenError("CNIPA returned HTTP 403")
    elapsed = 0.0
    step = 3.0
    while elapsed < limit:
        _raise_if_security_challenge(page)
        if page.query_selector("#searchStr"):
            return
        page.wait_for_timeout(int(step * 1000))
        elapsed += step
    _raise_if_security_challenge(page)
    raise TimeoutError("CNIPA search form did not become available before the wait limit")


def _wait_result_page_settled(page: Page) -> None:
    try:
        page.wait_for_load_state("load", timeout=30_000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=25_000)
    except Exception:
        pass
    page.wait_for_timeout(800)
    _raise_if_security_challenge(page)


def _safe_page_content(page: Page, *, max_attempts: int = 5) -> str:
    last_error: Exception | None = None
    for index in range(max_attempts):
        try:
            content = page.content()
            _raise_if_security_challenge(page)
            return content
        except Error as error:
            message = str(error).casefold()
            last_error = error
            if "navigating" not in message and "changing" not in message:
                raise
            try:
                page.wait_for_load_state("load", timeout=10_000)
            except Exception:
                pass
            page.wait_for_timeout(200 + 150 * index)
    if last_error:
        raise last_error
    raise RuntimeError("could not read CNIPA result page")


def submit_index_search(page: Page, keyword: str) -> None:
    page.fill("#searchStr", keyword)
    with page.expect_navigation(timeout=120_000, wait_until="load") as navigation:
        form = page.query_selector("#indexForm")
        if form:
            form.evaluate("el => el.submit()")
        else:
            page.evaluate(
                """() => {
                const form = document.getElementById('indexForm');
                if (form) form.submit();
            }"""
            )
    response = navigation.value
    if response is not None and response.status == 403:
        raise ForbiddenError("CNIPA returned HTTP 403")
    _wait_result_page_settled(page)


def fetch_epub_result_html(
    keyword: str,
    *,
    playwright_factory: Callable[[], Playwright] | None = None,
) -> str:
    factory = playwright_factory or sync_playwright
    with factory() as playwright:
        browser = _launch_browser(playwright)
        context = _new_context(browser)
        try:
            page = context.new_page()
            wait_for_epub_home_ready(page)
            submit_index_search(page, keyword)
            return _safe_page_content(page)
        finally:
            context.close()
            browser.close()


def search_epub_keyword(
    keyword: str,
    *,
    playwright_factory: Callable[[], Playwright] | None = None,
) -> tuple[str, list[EpubSearchHit]]:
    html = fetch_epub_result_html(keyword, playwright_factory=playwright_factory)
    return html, parse_search_result_html(html)


def search_epub_keyword_with_page(page: Page, keyword: str) -> tuple[str, list[EpubSearchHit]]:
    wait_for_epub_home_ready(page)
    submit_index_search(page, keyword)
    html = _safe_page_content(page)
    return html, parse_search_result_html(html)


def _launch_browser(playwright: Playwright) -> Browser:
    try:
        return playwright.chromium.launch()
    except Exception as error:
        message = str(error).casefold()
        if "executable" in message or "browser" in message or "chromium" in message:
            raise RuntimeError(
                "Chromium is unavailable. Install the optional Playwright browser runtime locally."
            ) from error
        raise


def _new_context(browser: Browser) -> BrowserContext:
    return browser.new_context()


def _dump_home_debug() -> None:
    output = Path(__file__).resolve().parent / "_last_home.html"
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        context = _new_context(browser)
        try:
            page = context.new_page()
            wait_for_epub_home_ready(page)
            output.write_text(page.content(), encoding="utf-8")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    _ensure_utf8_stdio()
    arguments = [value for value in sys.argv[1:] if value.strip()]
    if arguments and arguments[0] in ("--dump-home", "-d"):
        _dump_home_debug()
        raise SystemExit(0)
    keyword = arguments[0].strip() if arguments else "software patent search"
    try:
        html, hits = search_epub_keyword(keyword)
    except Exception as error:
        print("CNIPA_EPUB_ERROR:", type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
    output = Path(os.environ.get("EPUB_RESULT_HTML", "").strip() or default_result_html_path())
    output = output.expanduser().resolve()
    output.write_text(html, encoding="utf-8")
    print("EPUB_HITS_JSON:", json.dumps(hits_to_jsonable(hits), ensure_ascii=False), flush=True)
