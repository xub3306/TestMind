"""Playwright browser lifecycle management for Web UI testing.

Provides a singleton-like browser manager that MCP tools can share.
The browser is launched lazily on first use and shut down explicitly
via ``close_browser()``.

Design:

* **Headless by default** — ``headless=True`` for CI/CD; override with
  ``TESTMIND_HEADLESS=0`` for local debugging.
* **Lazy launch** — MCP tools call ``get_browser()`` / ``get_page()``
  and the browser starts automatically.
* **Isolation** — uses a persistent context directory under the
  project's ``testmind/browser-data/`` so cookies/localStorage survive
  across calls during a session.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_PLAYWRIGHT = None
_BROWSER = None
_CONTEXT = None
_PAGE = None
_PROJECT_DIR: Path | None = None


def _is_headless() -> bool:
    return os.environ.get("TESTMIND_HEADLESS", "1") != "0"


def init_browser(project_dir: str | Path | None = None) -> None:
    """Pre-warm the browser (optional — tools call this implicitly)."""
    global _PROJECT_DIR
    if project_dir is not None:
        _PROJECT_DIR = Path(project_dir)
    get_page()


def get_page():
    """Return a Playwright Page, launching the browser if needed."""
    global _PLAYWRIGHT, _BROWSER, _CONTEXT, _PAGE
    if _PAGE is not None and not _PAGE.is_closed():
        return _PAGE

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright is required for Web UI testing. "
            "Install it with: pip install playwright && python -m playwright install chromium"
        )

    _PLAYWRIGHT = sync_playwright().start()
    _BROWSER = _PLAYWRIGHT.chromium.launch(headless=_is_headless())

    # Use persistent context if project_dir is set so state survives
    # across MCP tool calls during a session.
    if _PROJECT_DIR is not None:
        user_data = _PROJECT_DIR / "testmind" / "browser-data"
        user_data.mkdir(parents=True, exist_ok=True)
        _CONTEXT = _BROWSER.new_context(storage_state=str(user_data / "state.json"))
    else:
        _CONTEXT = _BROWSER.new_context()

    _PAGE = _CONTEXT.new_page()
    return _PAGE


def close_browser() -> None:
    """Shut down the browser and clean up resources."""
    global _PLAYWRIGHT, _BROWSER, _CONTEXT, _PAGE
    try:
        if _PAGE is not None:
            _PAGE.close()
    except Exception:
        pass
    try:
        if _CONTEXT is not None:
            _CONTEXT.close()
    except Exception:
        pass
    try:
        if _BROWSER is not None:
            _BROWSER.close()
    except Exception:
        pass
    try:
        if _PLAYWRIGHT is not None:
            _PLAYWRIGHT.stop()
    except Exception:
        pass
    _PAGE = None
    _CONTEXT = None
    _BROWSER = None
    _PLAYWRIGHT = None
