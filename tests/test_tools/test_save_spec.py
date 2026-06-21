"""Unit tests for the save_spec MCP tool.

Exercises ``testmind.tools.save_spec.handle`` which persists Agent-
extracted endpoint data as a standardised ``api-spec.json``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from testmind.tools import save_spec


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSaveSpecToolDef:
    """Verify the MCP tool metadata."""

    def test_tool_name(self):
        assert save_spec.TOOL_NAME == "save_spec"

    def test_tool_def_has_required_fields(self):
        td = save_spec.TOOL_DEF
        assert td.name == "save_spec"
        assert td.description
        assert "endpoints" in td.inputSchema["properties"]
        assert "source_info" in td.inputSchema["properties"]
        assert set(td.inputSchema["required"]) == {"endpoints", "source_info"}


class TestSaveSpecHandle:
    """Exercise handle() to persist endpoint data."""

    def test_save_endpoints_generates_api_spec(self, tmp_path: Path):
        # Create a project on disk so SpecSaver can resolve the project dir.
        tm_dir = tmp_path / "testmind"
        (tm_dir / "specs").mkdir(parents=True, exist_ok=True)
        (tm_dir / "project.json").write_text(
            json.dumps({"name": "demo", "base_url": "http://localhost", "default_env": "dev"}),
            encoding="utf-8",
        )

        endpoints = [
            {"path": "/users", "method": "GET", "summary": "List users"},
            {"path": "/users", "method": "POST", "summary": "Create user"},
        ]
        source_info = {"type": "manual", "path": "notes.md"}

        result = asyncio.run(
            save_spec.handle(
                {
                    "endpoints": endpoints,
                    "source_info": source_info,
                    "project_name": str(tmp_path),
                },
                config=None,
            )
        )
        assert result["endpoints_count"] == 2
        api_spec = Path(result["api_spec_path"])
        assert api_spec.is_file()
        data = json.loads(api_spec.read_text(encoding="utf-8"))
        assert data["format"] == "testmind-spec-1.0"
        assert len(data["endpoints"]) == 2
        assert data["source"]["type"] == "manual"

    def test_save_empty_endpoints(self, tmp_path: Path):
        tm_dir = tmp_path / "testmind"
        (tm_dir / "specs").mkdir(parents=True, exist_ok=True)
        (tm_dir / "project.json").write_text(
            json.dumps({"name": "demo", "base_url": "http://localhost"}),
            encoding="utf-8",
        )

        result = asyncio.run(
            save_spec.handle(
                {
                    "endpoints": [],
                    "source_info": {"type": "manual"},
                    "project_name": str(tmp_path),
                },
                config=None,
            )
        )
        assert result["endpoints_count"] == 0

    def test_save_without_project_raises(self):
        """No project_name and no project.json nearby → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            asyncio.run(
                save_spec.handle(
                    {
                        "endpoints": [{"path": "/x", "method": "GET"}],
                        "source_info": {"type": "manual"},
                        "project_name": "/nonexistent/path",
                    },
                    config=None,
                )
            )

    def test_missing_required_args_raise(self):
        with pytest.raises(KeyError):
            asyncio.run(save_spec.handle({"source_info": {"type": "x"}}, config=None))
        with pytest.raises(KeyError):
            asyncio.run(save_spec.handle({"endpoints": []}, config=None))
