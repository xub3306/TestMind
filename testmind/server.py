"""TestMind MCP Server entry point."""

import asyncio
import os
import time
from typing import Any

from mcp.server import Server

from testmind.config.settings import load_project_config
from testmind.utils.logger import get_audit_logger

server = Server("testmind")

_audit = get_audit_logger()


def start_server(project_path: str = ".") -> None:
    """Start the MCP Server."""
    config = load_project_config(project_path)
    from testmind.tools import register_all

    register_all(server, config)
    asyncio.run(server.run())


# ---- Tool implementations (registered by tools/__init__.py) ----

async def discover_spec(base_url: str, project_name: str | None = None) -> dict:
    """Discover API specification URLs from a base URL.

    Tries common paths (/v3/api-docs, /swagger.json, etc.),
    returns all found Spec URLs.
    """
    from testmind.core.spec_fetcher import SpecFetcher

    start = time.monotonic()
    config = load_project_config()
    fetcher = SpecFetcher(config)
    result = await fetcher.discover_async(base_url)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("discover_spec", {"base_url": base_url, "project_name": project_name}, result.to_dict(), duration_ms, "ok")
    return result.to_dict()


async def fetch_url(url: str, project_name: str | None = None, save_path: str | None = None) -> dict:
    """Download any URL content to local storage.

    Supports JSON/YAML/HTML/Markdown formats,
    saves to the project's specs/ directory.
    """
    from testmind.core.spec_fetcher import SpecFetcher

    start = time.monotonic()
    config = load_project_config()
    fetcher = SpecFetcher(config)
    result = await fetcher.fetch_async(url, project_name, save_path)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("fetch_url", {"url": url}, result.to_dict(), duration_ms, "ok")
    return result.to_dict()


async def parse_spec(spec_path: str, project_name: str | None = None) -> dict:
    """Parse a standard OpenAPI/Swagger spec into structured data.

    Parses a local Spec file, extracts all endpoint information,
    and generates a standardized api-spec.json.
    """
    from testmind.core.spec_parser import SpecParser

    start = time.monotonic()
    config = load_project_config()
    parser = SpecParser(config)
    result = await parser.parse_async(spec_path, project_name)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("parse_spec", {"spec_path": spec_path}, result.to_dict(), duration_ms, "ok")
    return result.to_dict()


async def save_spec(endpoints: list[dict], source_info: dict, project_name: str | None = None) -> dict:
    """Save endpoint data extracted by Claude Code from non-standard documents.

    When the input is not standard OpenAPI/Swagger format (e.g., Markdown,
    HTML pages), Claude Code extracts endpoint data and calls this tool
    to save it as a standardized api-spec.json.
    """
    from testmind.core.spec_parser import SpecSaver

    start = time.monotonic()
    config = load_project_config()
    saver = SpecSaver(config)
    result = await saver.save_async(endpoints, source_info, project_name)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("save_spec", {"endpoints_count": len(endpoints)}, result.to_dict(), duration_ms, "ok")
    return result.to_dict()


async def save_requirements(requirements_data: dict, source_info: dict, project_name: str | None = None) -> dict:
    """Save requirements data extracted by Claude Code in standardized format.

    Saves business requirements extracted from user documents or app exploration
    as business-requirements.json for subsequent case generation.
    """
    from testmind.core.requirements_saver import RequirementsSaver

    start = time.monotonic()
    config = load_project_config()
    saver = RequirementsSaver(config)
    result = await saver.save_async(requirements_data, source_info, project_name)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("save_requirements", {"project_name": project_name}, result.to_dict(), duration_ms, "ok")
    return result.to_dict()


async def validate_case(case_json: dict) -> dict:
    """Validate test case format.

    Checks whether the test case JSON conforms to the expected schema.
    Returns validation result with any field errors.
    """
    from testmind.core.runner import validate_single_case

    start = time.monotonic()
    result = validate_single_case(case_json)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("validate_case", {"case_id": case_json.get("id", "")}, result.to_dict(), duration_ms, "ok")
    return result.to_dict()


async def save_case(case_json: dict, project: str | None = None) -> dict:
    """Save a test case to the project.

    Checks for duplicates. If an identical ID exists, saves to .pending/
    for review. If a duplicate fingerprint exists, returns a warning.
    """
    from testmind.core.runner import save_case_to_project

    start = time.monotonic()
    config = load_project_config()
    result = await save_case_to_project(config, case_json, project)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("save_case", {"case_id": case_json.get("id", "")}, result, duration_ms, "ok")
    return result


async def run_cases(target: str | None = None, tags: list[str] | None = None,
                    env: str | None = None, device: str | None = None) -> dict:
    """Execute a set of test cases.

    Returns a run_id for tracking results.
    """
    from testmind.core.runner import Runner

    start = time.monotonic()
    config = load_project_config()
    runner = Runner(config)
    run_id = await runner.run_async(target=target, tags=tags, env=env, device=device)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("run_cases", {"target": target, "tags": tags, "env": env}, {"run_id": run_id}, duration_ms, "ok")
    return {"run_id": run_id}


async def get_results(run_id: str | None = None, status_filter: str | None = None) -> dict:
    """Get execution results.

    Query test results by run_id and/or status filter.
    """
    from testmind.core.runner import get_results_data

    start = time.monotonic()
    config = load_project_config()
    result = await get_results_data(config, run_id=run_id, status_filter=status_filter)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("get_results", {"run_id": run_id, "status_filter": status_filter}, result, duration_ms, "ok")
    return result


async def list_cases(project: str | None = None, tags: list[str] | None = None) -> dict:
    """List test cases in the project.

    Optionally filter by tags.
    """
    from testmind.core.runner import list_all_cases_data

    start = time.monotonic()
    config = load_project_config()
    result = await list_all_cases_data(config, project=project, tags=tags)
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("list_cases", {"tags": tags}, result, duration_ms, "ok")
    return result


async def init_project(name: str, base_url: str = "", auth_type: str = "none",
                        agents: str = "", envs: list[str] | None = None) -> dict:
    """Initialize a new TestMind project.

    Creates project directory structure, config files, and agent configurations.
    """
    from testmind.core.project_init import init_project_async

    start = time.monotonic()
    result = await init_project_async(
        name=name, base_url=base_url, auth_type=auth_type,
        agents=agents, envs=envs or ["dev"],
    )
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("init_project", {"name": name}, result, duration_ms, "ok")
    return result


async def get_config(project: str | None = None, env: str | None = None) -> dict:
    """Get project configuration.

    Returns merged project + environment configuration.
    """
    start = time.monotonic()
    config = load_project_config(project)
    env_config = config.get_env_config(env) if env else None
    result = config.model_dump()
    if env_config:
        result["env"] = env_config.to_dict()
    duration_ms = (time.monotonic() - start) * 1000
    _audit.log("get_config", {"project": project, "env": env}, {"name": config.name}, duration_ms, "ok")
    return result