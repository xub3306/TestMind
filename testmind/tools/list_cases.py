"""MCP tool: list_cases — list test cases in the project."""

from __future__ import annotations

import time

from mcp import types

from testmind.core.runner import list_all_cases_data
from testmind.utils.logger import get_audit_logger


# Tool metadata for MCP registration
TOOL_NAME = "list_cases"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "List test cases in the project, optionally filtered by tags. "
        "Returns all test case IDs, names, priorities, and tags. "
        "Pending cases in .pending/ are excluded unless explicitly requested."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Optional project name.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of tags to filter cases.",
            },
        },
    },
)


async def handle(arguments: dict, config) -> dict:
    """Execute list_cases tool."""
    audit = get_audit_logger()
    start = time.monotonic()

    try:
        result = await list_all_cases_data(
            config,
            project=arguments.get("project"),
            tags=arguments.get("tags"),
        )
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("list_cases", arguments, result, duration_ms, "ok", "mcp")
        return result

    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("list_cases", arguments, str(e), duration_ms, "error", "mcp")
        raise