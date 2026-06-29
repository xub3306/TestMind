"""MCP tools for Web UI testing via Playwright.

Provides the Agent with browser control primitives so it can explore
and test web applications.  These tools are designed to be composed by
the Agent — they do NOT make testing decisions themselves (MCP tools
are execution-only per the project architecture).

Tools:
    browser_navigate   — go to a URL
    browser_click      — click an element by CSS selector
    browser_type       — type text into an input element
    browser_screenshot — capture the current page as a PNG
    browser_get_text   — retrieve text content of an element
    browser_close      — shut down the browser
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp import types
from testmind.utils.logger import get_audit_logger

# Tool metadata for MCP registration
TOOLS: list[tuple[str, types.Tool]] = []


def _register(name: str, description: str, input_schema: dict) -> types.Tool:
    tool = types.Tool(name=name, description=description, inputSchema=input_schema)
    TOOLS.append((name, tool))
    return tool


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_NAV = _register(
    "browser_navigate",
    "Navigate the browser to a URL. Returns the page title and current URL.",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to navigate to."},
        },
        "required": ["url"],
    },
)

_CLICK = _register(
    "browser_click",
    "Click an element on the page identified by a CSS selector. "
    "Returns the page title after the click.",
    {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector of the element to click."},
        },
        "required": ["selector"],
    },
)

_TYPE = _register(
    "browser_type",
    "Type text into an input element identified by a CSS selector.",
    {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector of the input element."},
            "text": {"type": "string", "description": "The text to type."},
        },
        "required": ["selector", "text"],
    },
)

_SHOT = _register(
    "browser_screenshot",
    "Take a screenshot of the current page and save it under "
    "testmind/screenshots/. Returns the file path.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Optional name for the screenshot file (without extension)."},
        },
    },
)

_TEXT = _register(
    "browser_get_text",
    "Get the visible text content of an element identified by a CSS selector.",
    {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector of the element."},
        },
        "required": ["selector"],
    },
)

_CLOSE = _register(
    "browser_close",
    "Close the browser and release all resources. Call this when Web UI testing is done.",
    {"type": "object", "properties": {}},
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_navigate(arguments: dict, config) -> dict:
    """Navigate to a URL."""
    audit = get_audit_logger()
    start = time.monotonic()
    url = arguments["url"]
    try:
        from testmind.core.web_driver import get_page
        page = get_page()
        page.goto(url, timeout=30000)
        result = {"url": page.url, "title": page.title()}
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_navigate", {"url": url}, result, duration_ms, "ok", "mcp")
        return result
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_navigate", {"url": url}, str(e), duration_ms, "error", "mcp")
        raise


async def handle_click(arguments: dict, config) -> dict:
    """Click an element."""
    audit = get_audit_logger()
    start = time.monotonic()
    selector = arguments["selector"]
    try:
        from testmind.core.web_driver import get_page
        page = get_page()
        page.click(selector, timeout=10000)
        result = {"selector": selector, "title": page.title(), "url": page.url}
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_click", {"selector": selector}, result, duration_ms, "ok", "mcp")
        return result
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_click", {"selector": selector}, str(e), duration_ms, "error", "mcp")
        raise


async def handle_type(arguments: dict, config) -> dict:
    """Type text into an element."""
    audit = get_audit_logger()
    start = time.monotonic()
    selector = arguments["selector"]
    text = arguments["text"]
    try:
        from testmind.core.web_driver import get_page
        page = get_page()
        page.fill(selector, text, timeout=10000)
        result = {"selector": selector, "typed": text}
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_type", {"selector": selector, "text": "***"}, result, duration_ms, "ok", "mcp")
        return result
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_type", {"selector": selector, "text": "***"}, str(e), duration_ms, "error", "mcp")
        raise


async def handle_screenshot(arguments: dict, config) -> dict:
    """Take a screenshot."""
    audit = get_audit_logger()
    start = time.monotonic()
    name = arguments.get("name", f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    try:
        from testmind.core.web_driver import get_page
        page = get_page()
        # Determine output path relative to project or cwd.
        if config and hasattr(config, "project_dir") and config.project_dir:
            shots_dir = config.project_dir / "testmind" / "screenshots"
        else:
            shots_dir = Path("testmind") / "screenshots"
        shots_dir.mkdir(parents=True, exist_ok=True)
        path = shots_dir / f"{name}.png"
        page.screenshot(path=str(path))
        result = {"path": str(path), "name": name}
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_screenshot", {"name": name}, result, duration_ms, "ok", "mcp")
        return result
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_screenshot", {"name": name}, str(e), duration_ms, "error", "mcp")
        raise


async def handle_get_text(arguments: dict, config) -> dict:
    """Get text of an element."""
    audit = get_audit_logger()
    start = time.monotonic()
    selector = arguments["selector"]
    try:
        from testmind.core.web_driver import get_page
        page = get_page()
        text = page.text_content(selector, timeout=10000)
        result = {"selector": selector, "text": text}
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_get_text", {"selector": selector}, result, duration_ms, "ok", "mcp")
        return result
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_get_text", {"selector": selector}, str(e), duration_ms, "error", "mcp")
        raise


async def handle_close(arguments: dict, config) -> dict:
    """Close the browser."""
    audit = get_audit_logger()
    start = time.monotonic()
    try:
        from testmind.core.web_driver import close_browser
        close_browser()
        result = {"closed": True}
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_close", {}, result, duration_ms, "ok", "mcp")
        return result
    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("browser_close", {}, str(e), duration_ms, "error", "mcp")
        raise


# Handler map for tool dispatch.
HANDLERS: dict[str, Any] = {
    "browser_navigate": handle_navigate,
    "browser_click": handle_click,
    "browser_type": handle_type,
    "browser_screenshot": handle_screenshot,
    "browser_get_text": handle_get_text,
    "browser_close": handle_close,
}
