"""MCP tool: parse_spec — parse an OpenAPI/Swagger spec into structured endpoint data."""

from __future__ import annotations

from mcp import types

from testmind.core.spec_parser import SpecParser

# Tool metadata for MCP registration
TOOL_NAME = "parse_spec"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "Parse a standard OpenAPI/Swagger spec file into structured endpoint data. "
        "Reads a local spec file, resolves $ref references, extracts all endpoints "
        "with their parameters, request bodies, responses, and security schemes, "
        "then generates a standardized api-spec.json."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "spec_path": {
                "type": "string",
                "description": "Path to the spec file (relative to project specs dir or absolute).",
            },
            "project_name": {
                "type": "string",
                "description": "Optional project name to resolve spec directory.",
            },
        },
        "required": ["spec_path"],
    },
)


async def handle(arguments: dict, config) -> dict:
    """Execute parse_spec tool."""
    spec_path = arguments["spec_path"]
    project_name = arguments.get("project_name")
    parser = SpecParser(config)
    result = await parser.parse_async(spec_path, project_name)
    return result.to_dict()