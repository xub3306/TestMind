"""TestMind MCP tool registry.

Registers all MCP tools with the server using the ``list_tools`` / ``call_tool``
pattern from the mcp-python-sdk.  Each tool module exports ``TOOLS``,
``HANDLERS``, or ``TOOL_NAME`` / ``TOOL_DEF`` / ``handle`` for spec tools.
Audit-logging is handled inside each tool handler directly.
"""

from __future__ import annotations

from typing import Any

from mcp import types
from mcp.server import Server

# Spec tools
from testmind.tools.discover_spec import TOOL_DEF as _discover_spec_def
from testmind.tools.discover_spec import TOOL_NAME as _discover_spec_name
from testmind.tools.discover_spec import handle as _discover_spec_handle
from testmind.tools.fetch_url import TOOL_DEF as _fetch_url_def
from testmind.tools.fetch_url import TOOL_NAME as _fetch_url_name
from testmind.tools.fetch_url import handle as _fetch_url_handle
from testmind.tools.parse_spec import TOOL_DEF as _parse_spec_def
from testmind.tools.parse_spec import TOOL_NAME as _parse_spec_name
from testmind.tools.parse_spec import handle as _parse_spec_handle
from testmind.tools.save_spec import TOOL_DEF as _save_spec_def
from testmind.tools.save_spec import TOOL_NAME as _save_spec_name
from testmind.tools.save_spec import handle as _save_spec_handle
from testmind.tools.save_requirements import TOOL_DEF as _save_req_def
from testmind.tools.save_requirements import TOOL_NAME as _save_req_name
from testmind.tools.save_requirements import handle as _save_req_handle

# API tools
from testmind.tools.validate_case import TOOL_DEF as _validate_case_def
from testmind.tools.validate_case import TOOL_NAME as _validate_case_name
from testmind.tools.validate_case import handle as _validate_case_handle
from testmind.tools.save_case import TOOL_DEF as _save_case_def
from testmind.tools.save_case import TOOL_NAME as _save_case_name
from testmind.tools.save_case import handle as _save_case_handle
from testmind.tools.run_cases import TOOL_DEF as _run_cases_def
from testmind.tools.run_cases import TOOL_NAME as _run_cases_name
from testmind.tools.run_cases import handle as _run_cases_handle
from testmind.tools.get_results import TOOL_DEF as _get_results_def
from testmind.tools.get_results import TOOL_NAME as _get_results_name
from testmind.tools.get_results import handle as _get_results_handle
from testmind.tools.list_cases import TOOL_DEF as _list_cases_def
from testmind.tools.list_cases import TOOL_NAME as _list_cases_name
from testmind.tools.list_cases import handle as _list_cases_handle
from testmind.tools.project_tools import TOOLS as _project_tools
from testmind.tools.project_tools import HANDLERS as _project_handlers

# ---------------------------------------------------------------------------
# All tools:  (name, definition, handler)
# ---------------------------------------------------------------------------

_ALL_TOOLS: list[tuple[str, types.Tool, Any]] = [
    (_discover_spec_name, _discover_spec_def, _discover_spec_handle),
    (_fetch_url_name, _fetch_url_def, _fetch_url_handle),
    (_parse_spec_name, _parse_spec_def, _parse_spec_handle),
    (_save_spec_name, _save_spec_def, _save_spec_handle),
    (_save_req_name, _save_req_def, _save_req_handle),
    (_validate_case_name, _validate_case_def, _validate_case_handle),
    (_save_case_name, _save_case_def, _save_case_handle),
    (_run_cases_name, _run_cases_def, _run_cases_handle),
    (_get_results_name, _get_results_def, _get_results_handle),
    (_list_cases_name, _list_cases_def, _list_cases_handle),
]
# project_tools has multiple tools — fold them in
for _pname, _pdef in _project_tools:
    _ALL_TOOLS.append((_pname, _pdef, _project_handlers[_pname]))

# Web UI tools (optional — registered when Playwright is installed).
try:
    from testmind.tools.web_tools import TOOLS as _web_tools, HANDLERS as _web_handlers

    for _wname, _wdef in _web_tools:
        _ALL_TOOLS.append((_wname, _wdef, _web_handlers[_wname]))
except ImportError:
    pass  # Playwright not installed — web tools unavailable.


def register_all(server: Server, config) -> None:
    """Register every TestMind tool with *server*.

    Uses the mcp-python-sdk ``list_tools`` / ``call_tool`` pattern.
    Audit-logging is handled inside each tool handler directly.
    """
    tool_defs = [defn for _, defn, _ in _ALL_TOOLS]
    handler_map: dict[str, Any] = {name: h for name, _, h in _ALL_TOOLS}

    @server.list_tools()  # type: ignore[misc]
    async def list_all_tools() -> list[types.Tool]:
        return tool_defs

    @server.call_tool()  # type: ignore[misc]
    async def call_all_tools(name: str, arguments: dict) -> dict:
        handler = handler_map.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return await handler(arguments, config)