"""MCP tool: fetch_url — download any URL content to local project storage."""

from __future__ import annotations

from mcp import types

from testmind.core.spec_fetcher import SpecFetcher

# Tool metadata for MCP registration
TOOL_NAME = "fetch_url"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "Download any URL content to local project storage. "
        "Fetches content from the given URL, detects format (JSON/YAML/HTML/Markdown), "
        "and saves it to the project's specs/ directory."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to download.",
            },
            "project_name": {
                "type": "string",
                "description": "Optional project name to resolve save directory.",
            },
            "save_path": {
                "type": "string",
                "description": "Optional custom file path (relative to specs dir or absolute).",
            },
        },
        "required": ["url"],
    },
)


async def handle(arguments: dict, config) -> dict:
    """Execute fetch_url tool."""
    url = arguments["url"]
    project_name = arguments.get("project_name")
    save_path = arguments.get("save_path")
    fetcher = SpecFetcher(config)
    result = await fetcher.fetch_async(url, project_name, save_path)
    return result.to_dict()