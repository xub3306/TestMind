"""MCP tool: save_spec — persist Agent-extracted endpoint data as api-spec.json."""

from __future__ import annotations

from mcp import types

from testmind.core.spec_parser import SpecSaver

# Tool metadata for MCP registration
TOOL_NAME = "save_spec"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "Save endpoint data extracted by the Agent from non-standard documents. "
        "When input is not a standard OpenAPI/Swagger spec (e.g., Markdown, HTML), "
        "the Agent extracts endpoint data and calls this tool to persist it as a "
        "standardized api-spec.json."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "endpoints": {
                "type": "array",
                "description": (
                    "List of endpoint dicts with keys: path, method, summary, "
                    "parameters, request_body, responses, security."
                ),
                "items": {
                    "type": "object",
                    "required": ["path", "method"],
                    "properties": {
                        "path": {"type": "string"},
                        "method": {"type": "string"},
                        "summary": {"type": "string"},
                        "parameters": {"type": "array"},
                        "request_body": {"type": "object"},
                        "responses": {"type": "object"},
                        "security": {"type": "array"},
                    },
                },
            },
            "source_info": {
                "type": "object",
                "description": "Dict describing the source with keys: type, path, url.",
                "properties": {
                    "type": {"type": "string"},
                    "path": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
            "project_name": {
                "type": "string",
                "description": "Optional project name to resolve save directory.",
            },
        },
        "required": ["endpoints", "source_info"],
    },
)


async def handle(arguments: dict, config) -> dict:
    """Execute save_spec tool."""
    endpoints = arguments["endpoints"]
    source_info = arguments["source_info"]
    project_name = arguments.get("project_name")
    saver = SpecSaver(config)
    result = await saver.save_async(endpoints, source_info, project_name)
    return result.to_dict()