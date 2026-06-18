"""MCP tool: save_requirements — persist business requirements as JSON + Markdown."""

from __future__ import annotations

from mcp import types

from testmind.core.requirements_saver import RequirementsSaver

# Tool metadata for MCP registration
TOOL_NAME = "save_requirements"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "Save business requirements data in standardized format. "
        "Persists requirements as both business-requirements.json (machine-readable) "
        "and business-requirements.md (human-readable for review). "
        "The Markdown file is generated automatically alongside the JSON file, "
        "making it easy for stakeholders to review and approve requirements."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "requirements_data": {
                "type": "object",
                "description": (
                    "Dict with 'project', 'modules' list (each containing "
                    "'id', 'name', 'flows'), and optional 'business_rules'."
                ),
            },
            "source_info": {
                "type": "object",
                "description": (
                    "Dict describing the source with keys: type, device, "
                    "platform, app_package, path."
                ),
                "properties": {
                    "type": {"type": "string"},
                    "device": {"type": "string"},
                    "platform": {"type": "string"},
                    "app_package": {"type": "string"},
                    "path": {"type": "string"},
                },
            },
            "project_name": {
                "type": "string",
                "description": "Optional project name to resolve save directory.",
            },
        },
        "required": ["requirements_data", "source_info"],
    },
)


async def handle(arguments: dict, config) -> dict:
    """Execute save_requirements tool."""
    requirements_data = arguments["requirements_data"]
    source_info = arguments["source_info"]
    project_name = arguments.get("project_name")
    saver = RequirementsSaver(config)
    result = await saver.save_async(requirements_data, source_info, project_name)
    return result.to_dict()