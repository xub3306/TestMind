"""Tests for Web UI MCP tools (testmind.tools.web_tools).

All tests mock ``testmind.core.web_driver`` to avoid launching a real
browser.  The tool handler logic (audit logging, error handling, JSON
serialisation) is covered independently of Playwright.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from testmind.tools.web_tools import (
    TOOLS,
    HANDLERS,
    handle_navigate,
    handle_click,
    handle_type,
    handle_screenshot,
    handle_get_text,
    handle_close,
)
from testmind.config.settings import ProjectConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_page():
    """Return a MagicMock that looks like a Playwright Page."""
    page = MagicMock()
    page.url = "http://example.com/page"
    page.title.return_value = "Example Page"
    page.text_content.return_value = "Hello World"
    return page


@pytest.fixture()
def config(tmp_path):
    cfg = ProjectConfig(name="web_test", base_url="http://localhost", default_env="dev")
    cfg.project_dir = tmp_path
    return cfg


def _patch_get_page(mock_page):
    """Return a context manager that patches web_driver.get_page."""
    return patch("testmind.core.web_driver.get_page", return_value=mock_page)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


class TestWebToolDefinitions:
    """Verify the MCP tool metadata."""

    def test_six_tools_registered(self):
        names = {t[0] for t in TOOLS}
        assert names == {"browser_navigate", "browser_click", "browser_type",
                         "browser_screenshot", "browser_get_text", "browser_close"}

    def test_tools_have_description(self):
        for name, tool in TOOLS:
            assert tool.description, f"{name} has no description"

    def test_all_have_handlers(self):
        names = {t[0] for t in TOOLS}
        assert names == set(HANDLERS.keys())

    def test_navigate_requires_url(self):
        for name, tool in TOOLS:
            if name == "browser_navigate":
                assert "url" in tool.inputSchema.get("required", [])


# ---------------------------------------------------------------------------
# Handler tests (with mocked browser)
# ---------------------------------------------------------------------------


class TestNavigate:
    def test_returns_url_and_title(self, mock_page, config):
        with _patch_get_page(mock_page):
            result = asyncio.run(handle_navigate({"url": "http://example.com"}, config))
        assert result["url"] == "http://example.com/page"
        assert result["title"] == "Example Page"
        mock_page.goto.assert_called_once_with("http://example.com", timeout=30000)


class TestClick:
    def test_clicks_and_returns_state(self, mock_page, config):
        with _patch_get_page(mock_page):
            result = asyncio.run(handle_click({"selector": "#btn"}, config))
        assert result["selector"] == "#btn"
        mock_page.click.assert_called_once_with("#btn", timeout=10000)


class TestType:
    def test_fills_element(self, mock_page, config):
        with _patch_get_page(mock_page):
            result = asyncio.run(handle_type({"selector": "#input", "text": "hello"}, config))
        assert result["typed"] == "hello"
        mock_page.fill.assert_called_once_with("#input", "hello", timeout=10000)


class TestScreenshot:
    def test_saves_png(self, mock_page, config):
        with _patch_get_page(mock_page):
            result = asyncio.run(handle_screenshot({"name": "login"}, config))
        assert result["name"] == "login"
        path = Path(result["path"])
        assert path.suffix == ".png"
        assert "login" in path.stem
        mock_page.screenshot.assert_called_once()


class TestGetText:
    def test_returns_element_text(self, mock_page, config):
        mock_page.text_content.return_value = "Hello World"
        with _patch_get_page(mock_page):
            result = asyncio.run(handle_get_text({"selector": "h1"}, config))
        assert result["text"] == "Hello World"


class TestClose:
    def test_closes_browser(self, config):
        with patch("testmind.core.web_driver.close_browser") as mock_close:
            result = asyncio.run(handle_close({}, config))
        assert result["closed"] is True
        mock_close.assert_called_once()
