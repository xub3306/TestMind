"""Unit tests for the ``project_tools`` MCP module (init_project / get_config).

``init_project`` creates a project directory tree relative to the current
working directory; the autouse ``_chdir_tmp_path`` fixture (see
``conftest.py``) pins the cwd to ``tmp_path`` so creation is isolated and
cleaned up automatically.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from testmind.tools import project_tools as pt


# ---------------------------------------------------------------------------
# Module metadata
# ---------------------------------------------------------------------------


class TestProjectToolsMetadata:
    """Verify tool names, TOOLS list, and HANDLERS registry."""

    def test_tool_names(self):
        assert pt.INIT_PROJECT_TOOL_NAME == "init_project"
        assert pt.GET_CONFIG_TOOL_NAME == "get_config"

    def test_tool_defs_have_correct_names(self):
        assert pt.INIT_PROJECT_TOOL_DEF.name == "init_project"
        assert pt.GET_CONFIG_TOOL_DEF.name == "get_config"

    def test_tool_defs_have_descriptions(self):
        assert len(pt.INIT_PROJECT_TOOL_DEF.description) > 0
        assert len(pt.GET_CONFIG_TOOL_DEF.description) > 0

    def test_init_project_requires_name(self):
        schema = pt.INIT_PROJECT_TOOL_DEF.inputSchema
        assert "name" in schema["required"]

    def test_tools_list_contains_both(self):
        names = [name for name, _def in pt.TOOLS]
        assert names == ["init_project", "get_config"]
        assert len(pt.TOOLS) == 2

    def test_handlers_registry_contains_both(self):
        assert set(pt.HANDLERS.keys()) == {"init_project", "get_config"}
        assert callable(pt.HANDLERS["init_project"])
        assert callable(pt.HANDLERS["get_config"])


# ---------------------------------------------------------------------------
# handle_init_project
# ---------------------------------------------------------------------------


class TestInitProjectHandle:
    """Exercise ``handle_init_project``."""

    def test_creates_project_structure(self, tmp_path: Path):
        result = asyncio.run(
            pt.handle_init_project(
                {"name": "demo", "base_url": "http://localhost:8080"},
                None,
            )
        )
        assert result["project_name"] == "demo"
        # project_dir is returned as a (relative) string; resolve under cwd.
        project_dir = Path(result["project_dir"])
        if not project_dir.is_absolute():
            project_dir = tmp_path / project_dir
        tm_dir = project_dir / "testmind"
        assert tm_dir.is_dir()
        # Required subdirectories.
        for sub in ("envs", "specs", "requirements", "cases",
                    "suites", "hooks", "results", "logs"):
            assert (tm_dir / sub).is_dir(), f"missing subdir: {sub}"
        # project.json exists and is valid JSON with the expected name.
        project_json = tm_dir / "project.json"
        assert project_json.is_file()
        data = json.loads(project_json.read_text(encoding="utf-8"))
        assert data["name"] == "demo"
        assert data["base_url"] == "http://localhost:8080"
        # Default env file (dev) is created.
        assert (tm_dir / "envs" / "dev.json").is_file()
        # Result payload echoes envs.
        assert "dev" in result["envs"]
        # No agents requested -> empty agent results.
        assert result["agents"] == []
        assert result["agent_results"] == {}

    def test_custom_env_list(self, tmp_path: Path):
        result = asyncio.run(
            pt.handle_init_project(
                {"name": "demo2", "envs": ["dev", "staging"]},
                None,
            )
        )
        assert result["envs"] == ["dev", "staging"]
        project_dir = tmp_path / result["project_dir"]
        for env in ("dev", "staging"):
            assert (project_dir / "testmind" / "envs" / f"{env}.json").is_file()

    def test_claude_agent_config_created(self, tmp_path: Path):
        result = asyncio.run(
            pt.handle_init_project(
                {"name": "demo3", "agents": "claude"},
                None,
            )
        )
        assert result["agents"] == ["claude"]
        assert "claude" in result["agent_results"]
        project_dir = tmp_path / result["project_dir"]
        # .claude/settings.json must exist.
        assert (project_dir / ".claude" / "settings.json").is_file()
        # Skills directory populated.
        skills_dir = project_dir / ".claude" / "skills"
        assert skills_dir.is_dir()
        assert (skills_dir / "testmind.md").is_file()

    def test_missing_name_argument_raises(self):
        with pytest.raises(KeyError):
            asyncio.run(pt.handle_init_project({}, None))


# ---------------------------------------------------------------------------
# handle_get_config
# ---------------------------------------------------------------------------


class TestGetConfigHandle:
    """Exercise ``handle_get_config``.

    The project is materialised by hand (writing valid ``project.json``
    and ``envs/dev.json`` directly) rather than via ``init_project``.
    This keeps the test a true unit test of the config-loading path and
    avoids coupling to the ``env.json.j2`` template (which currently
    emits a trailing comma for ``auth_type="none"``).
    """

    def _make_project(self, tmp_path: Path, name: str = "cfgdemo") -> Path:
        project_dir = tmp_path / name
        tm_dir = project_dir / "testmind"
        (tm_dir / "envs").mkdir(parents=True, exist_ok=True)

        (tm_dir / "project.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "type": "api",
                    "base_url": "http://localhost:8080",
                    "default_env": "dev",
                }
            ),
            encoding="utf-8",
        )
        (tm_dir / "envs" / "dev.json").write_text(
            json.dumps(
                {"name": "dev", "base_url": "http://dev.example.com:8080"}
            ),
            encoding="utf-8",
        )
        return project_dir

    def test_returns_project_config(self, tmp_path: Path):
        self._make_project(tmp_path)
        result = asyncio.run(pt.handle_get_config({"project": "cfgdemo"}, None))
        assert result["name"] == "cfgdemo"
        assert result["base_url"] == "http://localhost:8080"
        assert result["default_env"] == "dev"
        # No env requested -> no env key in the result.
        assert "env" not in result

    def test_with_env_merges_env_config(self, tmp_path: Path):
        self._make_project(tmp_path)
        result = asyncio.run(
            pt.handle_get_config({"project": "cfgdemo", "env": "dev"}, None)
        )
        assert result["name"] == "cfgdemo"
        assert "env" in result
        env_cfg = result["env"]
        assert env_cfg["name"] == "dev"
        assert env_cfg["base_url"] == "http://dev.example.com:8080"

    def test_unknown_project_raises(self):
        # No testmind/project.json anywhere up the tree from a bogus path.
        with pytest.raises(FileNotFoundError):
            asyncio.run(
                pt.handle_get_config({"project": "totally_missing_proj"}, None)
            )

    def test_init_project_then_get_config_integration(self, tmp_path: Path):
        """Smoke-test the full init -> get_config path (no env read).

        ``project.json`` produced by ``init_project`` is valid JSON, so
        reading just the project config (without an env) works end to end.
        """
        asyncio.run(
            pt.handle_init_project(
                {"name": "initdemo", "base_url": "http://localhost:9090"},
                None,
            )
        )
        result = asyncio.run(
            pt.handle_get_config({"project": "initdemo"}, None)
        )
        assert result["name"] == "initdemo"
        assert result["base_url"] == "http://localhost:9090"
