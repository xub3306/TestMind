"""Unit tests for the parse_spec MCP tool.

Exercises ``testmind.tools.parse_spec.handle`` against local OpenAPI 3.0
spec files.  No network is involved.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from testmind.tools import parse_spec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_openapi3(specs_dir: Path) -> Path:
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Demo API", "version": "1.0.0"},
        "paths": {
            "/users": {
                "get": {
                    "summary": "List users",
                    "parameters": [
                        {"name": "page", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "ok"}},
                },
                "post": {
                    "summary": "Create user",
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "object"}}},
                        "required": True,
                    },
                    "responses": {"201": {"description": "created"}},
                },
            },
        },
    }
    f = specs_dir / "openapi.json"
    f.write_text(json.dumps(spec), encoding="utf-8")
    return f


def _write_swagger2(specs_dir: Path) -> Path:
    spec = {
        "swagger": "2.0",
        "info": {"title": "Old API", "version": "1.0"},
        "paths": {"/items": {"get": {"responses": {"200": {"description": "ok"}}}}},
    }
    f = specs_dir / "swagger.json"
    f.write_text(json.dumps(spec), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParseSpecToolDef:
    """Verify the MCP tool metadata."""

    def test_tool_name(self):
        assert parse_spec.TOOL_NAME == "parse_spec"

    def test_tool_def_has_required_fields(self):
        td = parse_spec.TOOL_DEF
        assert td.name == "parse_spec"
        assert td.description
        assert "spec_path" in td.inputSchema["properties"]
        assert td.inputSchema["required"] == ["spec_path"]


class TestParseSpecHandle:
    """Exercise handle() against local spec files."""

    def test_parse_openapi3(self, tmp_path: Path):
        specs_dir = tmp_path / "testmind" / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        spec_file = _write_openapi3(specs_dir)

        result = asyncio.run(
            parse_spec.handle({"spec_path": str(spec_file)}, config=None)
        )
        assert result["format"] == "openapi_3.0"
        assert result["endpoints_count"] == 2
        methods = {ep["method"] for ep in result["endpoints"]}
        assert methods == {"GET", "POST"}
        # api-spec.json is generated alongside the input.
        api_spec = spec_file.parent / "api-spec.json"
        assert api_spec.is_file()
        data = json.loads(api_spec.read_text(encoding="utf-8"))
        assert data["format"] == "testmind-spec-1.0"

    def test_parse_swagger2(self, tmp_path: Path):
        specs_dir = tmp_path / "testmind" / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        spec_file = _write_swagger2(specs_dir)

        result = asyncio.run(
            parse_spec.handle({"spec_path": str(spec_file)}, config=None)
        )
        assert result["format"] == "swagger_2.0"
        assert result["endpoints_count"] == 1

    def test_parse_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            asyncio.run(
                parse_spec.handle({"spec_path": "no/such/file.json"}, config=None)
            )

    def test_missing_spec_path_arg_raises(self):
        with pytest.raises(KeyError):
            asyncio.run(parse_spec.handle({}, config=None))
