"""MCP tools: init_project and get_config — project initialization and configuration."""

from __future__ import annotations

import time

from mcp import types

from testmind.config.settings import load_project_config
from testmind.core.project_init import init_project_async
from testmind.utils.logger import get_audit_logger


# Tool metadata for MCP registration
INIT_PROJECT_TOOL_NAME = "init_project"
GET_CONFIG_TOOL_NAME = "get_config"

INIT_PROJECT_TOOL_DEF = types.Tool(
    name=INIT_PROJECT_TOOL_NAME,
    description=(
        "Initialize a new TestMind project with directory structure and config. "
        "Creates the project directory, testmind/ subdirectories (specs, requirements, "
        "cases, suites, hooks, results, logs, envs), project.json, environment configs, "
        "and optional agent configurations (Claude Code / OpenCode)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Project name (used as directory name).",
            },
            "base_url": {
                "type": "string",
                "description": "Base URL of the target API.",
                "default": "http://localhost",
            },
            "auth_type": {
                "type": "string",
                "description": 'Authentication type: "none", "bearer", "basic", "api_key".',
                "default": "none",
            },
            "agents": {
                "type": "string",
                'description': 'Comma-separated agent names to configure: "claude", "opencode".',
                "default": "",
            },
            "envs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of environment names (default: [\"dev\"]).",
            },
        },
        "required": ["name"],
    },
)

GET_CONFIG_TOOL_DEF = types.Tool(
    name=GET_CONFIG_TOOL_NAME,
    description=(
        "Get project configuration, optionally merged with environment config. "
        "Returns the project settings from project.json. When an environment name "
        "is provided, also includes the environment-specific base_url and variables."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Optional project name or path.",
            },
            "env": {
                "type": "string",
                "description": 'Optional environment name (e.g. "dev", "staging", "prod").',
            },
        },
    },
)

TOOLS = [
    (INIT_PROJECT_TOOL_NAME, INIT_PROJECT_TOOL_DEF),
    (GET_CONFIG_TOOL_NAME, GET_CONFIG_TOOL_DEF),
]


async def handle_init_project(arguments: dict, config) -> dict:
    """Execute init_project tool."""
    audit = get_audit_logger()
    start = time.monotonic()

    try:
        result = await init_project_async(
            name=arguments["name"],
            base_url=arguments.get("base_url", "http://localhost"),
            auth_type=arguments.get("auth_type", "none"),
            agents=arguments.get("agents", "").split(",") if arguments.get("agents") else [],
            envs=arguments.get("envs") or ["dev"],
        )
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("init_project", arguments, result, duration_ms, "ok", "mcp")
        return result

    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("init_project", arguments, str(e), duration_ms, "error", "mcp")
        raise


async def handle_get_config(arguments: dict, config) -> dict:
    """Execute get_config tool.

    Uses ``model_dump()`` with ``exclude`` to strip the ``PrivateAttr``
    ``_project_dir`` before returning configuration data.
    """
    audit = get_audit_logger()
    start = time.monotonic()

    try:
        project = arguments.get("project")
        env = arguments.get("env")
        cfg = load_project_config(project or ".")
        env_config = cfg.get_env_config(env) if env else None

        # model_dump() on a Pydantic model with PrivateAttr will NOT
        # include private fields by default, so this is safe.
        result = cfg.model_dump()
        if env_config:
            result["env"] = env_config.model_dump()

        duration_ms = (time.monotonic() - start) * 1000
        audit.log("get_config", arguments, result, duration_ms, "ok", "mcp")
        return result

    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("get_config", arguments, str(e), duration_ms, "error", "mcp")
        raise


HANDLERS = {
    INIT_PROJECT_TOOL_NAME: handle_init_project,
    GET_CONFIG_TOOL_NAME: handle_get_config,
}