"""MCP tool: discover_spec — probe common API spec paths on a base URL."""

from __future__ import annotations

from mcp import types

from testmind.core.spec_fetcher import SpecFetcher

# Tool metadata for MCP registration
TOOL_NAME = "discover_spec"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "Discover API specification URLs from a base URL by probing common paths. "
        "Tries well-known paths such as /v3/api-docs, /swagger.json, /openapi.json, "
        "and returns all discovered Spec URLs with their formats. "
        "Set extended=true to also probe less common but still well-known locations "
        "(e.g. /swagger-resources, /.well-known/openapi, /api-docs/default)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "base_url": {
                "type": "string",
                "description": 'The root URL of the API to scan (e.g. "https://api.example.com").',
            },
            "project_name": {
                "type": "string",
                "description": "Optional project name to resolve spec directory.",
            },
            "extended": {
                "type": "boolean",
                "description": (
                    "When true, probe the extended path list in addition to "
                    "the MVP paths. Use when the fast probe finds nothing."
                ),
                "default": False,
            },
        },
        "required": ["base_url"],
    },
)


async def handle(arguments: dict, config) -> dict:
    """Execute discover_spec tool."""
    base_url = arguments["base_url"]
    extended = arguments.get("extended", False)
    fetcher = SpecFetcher(config)
    result = await fetcher.discover_async(base_url, extended=extended)
    return result.to_dict()