"""Unit tests for the save_requirements MCP tool.

Exercises ``testmind.tools.save_requirements.handle`` which persists
business requirements as both JSON and a derived Markdown file.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from testmind.tools import save_requirements


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_requirements_data() -> dict:
    return {
        "project": "demo",
        "modules": [
            {
                "id": "MOD-USER",
                "name": "User Module",
                "description": "User management flows",
                "flows": [
                    {
                        "id": "FLOW-LOGIN-001",
                        "name": "User login",
                        "description": "Standard login flow",
                        "steps": [
                            {"screen": "login", "action": "input credentials", "input": {"username": "alice"}},
                            {"screen": "home", "action": "view dashboard"},
                        ],
                        "preconditions": ["User account exists"],
                        "postconditions": ["Session token issued"],
                    },
                ],
            },
        ],
        "business_rules": [
            {"id": "BR-001", "description": "Passwords must be hashed", "applies_to": ["user", "auth"]},
        ],
    }


def _make_project(tmp_path: Path) -> Path:
    tm_dir = tmp_path / "testmind"
    (tm_dir / "requirements").mkdir(parents=True, exist_ok=True)
    (tm_dir / "project.json").write_text(
        json.dumps({"name": "demo", "base_url": "http://localhost"}),
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSaveRequirementsToolDef:
    """Verify the MCP tool metadata."""

    def test_tool_name(self):
        assert save_requirements.TOOL_NAME == "save_requirements"

    def test_tool_def_has_required_fields(self):
        td = save_requirements.TOOL_DEF
        assert td.name == "save_requirements"
        assert td.description
        assert "requirements_data" in td.inputSchema["properties"]
        assert "source_info" in td.inputSchema["properties"]
        assert set(td.inputSchema["required"]) == {"requirements_data", "source_info"}


class TestSaveRequirementsHandle:
    """Exercise handle() to persist requirements as JSON + Markdown."""

    def test_save_generates_json_and_markdown(self, tmp_path: Path):
        project_dir = _make_project(tmp_path)

        result = asyncio.run(
            save_requirements.handle(
                {
                    "requirements_data": _make_requirements_data(),
                    "source_info": {"type": "manual"},
                    "project_name": str(project_dir),
                },
                config=None,
            )
        )
        req_path = Path(result["requirements_path"])
        md_path = Path(result["markdown_path"])
        assert req_path.is_file()
        assert md_path.is_file()
        assert result["modules_count"] == 1
        assert result["flows_count"] == 1

        # JSON is valid and uses the standardised format tag.
        data = json.loads(req_path.read_text(encoding="utf-8"))
        assert data["format"] == "testmind-requirements-1.0"
        assert data["project"] == "demo"
        assert data["modules"][0]["id"] == "MOD-USER"
        assert data["business_rules"][0]["id"] == "BR-001"

        # Markdown is non-empty and references the project name.
        md = md_path.read_text(encoding="utf-8")
        assert "demo" in md
        assert "MOD-USER" in md
        assert "FLOW-LOGIN-001" in md

    def test_save_with_emulator_source(self, tmp_path: Path):
        project_dir = _make_project(tmp_path)
        source = {
            "type": "emulator_android",
            "device": "redroid_11",
            "platform": "android",
            "app_package": "com.example.app",
        }
        result = asyncio.run(
            save_requirements.handle(
                {
                    "requirements_data": {"project": "app", "modules": []},
                    "source_info": source,
                    "project_name": str(project_dir),
                },
                config=None,
            )
        )
        data = json.loads(Path(result["requirements_path"]).read_text(encoding="utf-8"))
        assert data["source"]["type"] == "emulator_android"
        assert data["source"]["device"] == "redroid_11"
        assert data["source"]["platform"] == "android"

    def test_save_without_project_raises(self):
        with pytest.raises(FileNotFoundError):
            asyncio.run(
                save_requirements.handle(
                    {
                        "requirements_data": {"project": "x", "modules": []},
                        "source_info": {"type": "manual"},
                        "project_name": "/no/such/dir",
                    },
                    config=None,
                )
            )

    def test_missing_required_args_raise(self):
        with pytest.raises(KeyError):
            asyncio.run(
                save_requirements.handle({"source_info": {"type": "x"}}, config=None)
            )
        with pytest.raises(KeyError):
            asyncio.run(
                save_requirements.handle({"requirements_data": {}}, config=None)
            )
