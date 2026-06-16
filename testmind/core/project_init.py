"""TestMind project initialization.

Creates project directory structure, configuration files, and agent
configurations using Jinja2 templates from the ``templates/`` directory.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from testmind.config.settings import AuthConfig, ProjectConfig

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


def _get_jinja_env() -> Environment:
    """Create a Jinja2 environment pointing at the templates directory."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(default=False),
        keep_trailing_newline=True,
    )


def init_project(
    name: str,
    project_type: str = "api",
    base_url: str = "http://localhost",
    auth_type: str = "none",
    agents: list[str] | None = None,
    envs: list[str] | None = None,
) -> dict[str, Any]:
    """Synchronous wrapper for :func:`init_project_async`."""
    return asyncio.run(
        init_project_async(name, project_type, base_url, auth_type, agents, envs)
    )


async def init_project_async(
    name: str,
    project_type: str = "api",
    base_url: str = "http://localhost",
    auth_type: str = "none",
    agents: list[str] | None = None,
    envs: list[str] | None = None,
) -> dict[str, Any]:
    """Initialize a new TestMind project directory structure.

    Uses Jinja2 templates for generating configuration files rather than
    hard-coded string concatenation.
    """
    project_dir = Path(name)
    tm_dir = project_dir / "testmind"
    envs_list = envs or ["dev", "staging", "prod"]
    agents = agents or []

    dirs_to_create = [
        tm_dir,
        tm_dir / "envs",
        tm_dir / "specs",
        tm_dir / "requirements",
        tm_dir / "cases",
        tm_dir / "suites",
        tm_dir / "hooks",
        tm_dir / "results",
        tm_dir / "logs",
    ]

    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    for gitkeep_dir in [
        tm_dir / "specs",
        tm_dir / "requirements",
        tm_dir / "cases",
        tm_dir / "suites",
        tm_dir / "hooks",
        tm_dir / "results",
        tm_dir / "logs",
    ]:
        (gitkeep_dir / ".gitkeep").touch()

    # Render project.json using Jinja2 template
    env = _get_jinja_env()
    project_content = env.get_template("project.json.j2").render(
        project_name=name,
        project_type=project_type,
        base_url=base_url,
        auth_type=auth_type,
        default_env=envs_list[0] if envs_list else "dev",
    )
    (tm_dir / "project.json").write_text(project_content, encoding="utf-8")

    # Render environment config files using Jinja2 template
    for env_name in envs_list:
        env_base_url = _derive_env_url(base_url, env_name)
        env_content = env.get_template("env.json.j2").render(
            project_name=name,
            env_name=env_name,
            env_base_url=env_base_url,
            base_url=base_url,
            auth_type=auth_type,
        )
        (tm_dir / "envs" / f"{env_name}.json").write_text(env_content, encoding="utf-8")

    agent_results: dict[str, Any] = {}
    for agent in agents:
        if agent == "claude":
            agent_results["claude"] = _init_claude_config(project_dir, name, base_url, auth_type)
        elif agent == "opencode":
            agent_results["opencode"] = _init_opencode_config(project_dir, name, base_url, auth_type)

    return {
        "project_dir": str(project_dir),
        "project_name": name,
        "project_type": project_type,
        "envs": envs_list,
        "agents": agents,
        "agent_results": agent_results,
    }


def _derive_env_url(base_url: str, env_name: str) -> str:
    """Derive environment-specific base URL from the project base URL."""
    env_prefixes = {
        "dev": "dev-",
        "staging": "staging-",
        "prod": "",
    }
    prefix = env_prefixes.get(env_name, "")
    if not prefix:
        return base_url

    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(base_url)
    new_netloc = f"{prefix}{parsed.netloc}"
    return urlunparse(parsed._replace(netloc=new_netloc))


def _init_claude_config(project_dir: Path, project_name: str, base_url: str = "", auth_type: str = "none") -> dict[str, Any]:
    """Set up Claude Code integration using Jinja2 templates."""
    env = _get_jinja_env()
    claude_dir = project_dir / ".claude"
    skills_dir = claude_dir / "skills"
    claude_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    settings = {
        "mcpServers": {
            "testmind": {
                "command": "testmind",
                "args": ["serve", "--project", project_name],
            }
        }
    }
    (claude_dir / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    skill_names = [
        "testmind",
        "requirement-analyst",
        "case-generator",
        "case-runner",
        "result-analyst",
        "app-explorer",
    ]

    for skill_name in skill_names:
        template_name = f"claude/skills/{skill_name}.md.j2"
        template = env.get_template(template_name)
        content = template.render(
            project_name=project_name,
            base_url=base_url,
            auth_type=auth_type,
        )
        filename = f"{skill_name}.md" if skill_name != "testmind" else "testmind.md"
        (skills_dir / filename).write_text(content, encoding="utf-8")

    return {
        "settings_path": str(claude_dir / "settings.json"),
        "skills_dir": str(skills_dir),
    }


def _init_opencode_config(project_dir: Path, project_name: str, base_url: str = "", auth_type: str = "none") -> dict[str, Any]:
    """Set up OpenCode integration using Jinja2 templates."""
    env = _get_jinja_env()
    opencode_dir = project_dir / ".opencode"
    opencode_dir.mkdir(parents=True, exist_ok=True)

    config_content = env.get_template("opencode/opencode.jsonc.j2").render(
        project_name=project_name,
    )
    (opencode_dir / "opencode.jsonc").write_text(config_content, encoding="utf-8")

    skills_dir = opencode_dir / "skill"
    skill_names = [
        "testmind",
        "requirement-analyst",
        "case-generator",
        "case-runner",
        "result-analyst",
        "app-explorer",
    ]

    for skill_name in skill_names:
        skill_dir = skills_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        template_name = f"opencode/skills/{skill_name}/SKILL.md.j2"
        template = env.get_template(template_name)
        content = template.render(
            project_name=project_name,
            base_url=base_url,
            auth_type=auth_type,
        )
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    return {
        "config_path": str(opencode_dir / "opencode.jsonc"),
        "skills_dir": str(skills_dir),
    }