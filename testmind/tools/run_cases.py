"""MCP tool: run_cases — execute a set of test cases."""

from __future__ import annotations

import time

from mcp import types

from testmind.core.runner import Runner
from testmind.utils.logger import get_audit_logger


# Tool metadata for MCP registration
TOOL_NAME = "run_cases"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "Execute a set of test cases and return a run_id for tracking. "
        "Runs test cases filtered by target directory, tags, or suite name. "
        "Supports parallel execution, retry on failure, and fail-fast mode."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Optional case directory or file path to run.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of tags to filter cases.",
            },
            "env": {
                "type": "string",
                "description": 'Environment name (dev, staging, prod).',
            },
            "device": {
                "type": "string",
                "description": "Device name for mobile tests (V3).",
            },
            "suite": {
                "type": "string",
                "description": "Test suite name to run.",
            },
            "fail_fast": {
                "type": "integer",
                "description": "Stop after N consecutive failures (0 = disabled).",
            },
            "workers": {
                "type": "integer",
                "description": "Number of parallel workers.",
            },
            "retry": {
                "type": "integer",
                "description": "Retry failed cases N times.",
            },
        },
    },
)


async def handle(arguments: dict, config) -> dict:
    """Execute run_cases tool.

    This tool is zero-AI: the execution path is 100% deterministic with
    no LLM calls. It delegates to the core Runner engine.
    """
    audit = get_audit_logger()
    start = time.monotonic()

    try:
        runner = Runner(config)
        run_id = await runner.run_async(
            target=arguments.get("target"),
            tags=arguments.get("tags"),
            env=arguments.get("env"),
            device=arguments.get("device"),
            suite=arguments.get("suite"),
            fail_fast=arguments.get("fail_fast", 0),
            workers=arguments.get("workers", 1),
            retry=arguments.get("retry"),
        )
        result = {"run_id": run_id}
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("run_cases", arguments, result, duration_ms, "ok", "mcp")
        return result

    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("run_cases", arguments, str(e), duration_ms, "error", "mcp")
        raise