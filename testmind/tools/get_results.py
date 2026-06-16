"""MCP tool: get_results — query test execution results."""

from __future__ import annotations

import time

from mcp import types

from testmind.core.runner import get_results_data
from testmind.utils.logger import get_audit_logger


# Tool metadata for MCP registration
TOOL_NAME = "get_results"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "Get test execution results. Retrieves case-level results including "
        "request/response snapshots, assertion details, and error information. "
        "Query by run_id and/or status filter."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "run_id": {
                "type": "string",
                "description": "Optional run ID to filter results.",
            },
            "status_filter": {
                "type": "string",
                "description": 'Optional status to filter: "pass", "fail", "error", "skipped".',
            },
        },
    },
)


async def handle(arguments: dict, config) -> dict:
    """Execute get_results tool."""
    audit = get_audit_logger()
    start = time.monotonic()

    try:
        result = await get_results_data(
            config,
            run_id=arguments.get("run_id"),
            status_filter=arguments.get("status_filter"),
        )
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("get_results", arguments, result, duration_ms, "ok", "mcp")
        return result

    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("get_results", arguments, str(e), duration_ms, "error", "mcp")
        raise