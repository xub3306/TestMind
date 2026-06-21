"""Unit tests for the ``validate_case`` MCP tool.

Verifies tool metadata, the happy-path validation, and rejection of
malformed case JSON (missing fields, bad ID format, bad request/expect
structure).  The handler is async and is driven via ``asyncio.run``.
"""

from __future__ import annotations

import asyncio

import pytest

from testmind.tools import validate_case as vc


# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------


class TestValidateCaseMetadata:
    """Verify TOOL_NAME / TOOL_DEF registration metadata."""

    def test_tool_name(self):
        assert vc.TOOL_NAME == "validate_case"

    def test_tool_def_name_matches(self):
        assert vc.TOOL_DEF.name == "validate_case"

    def test_tool_def_has_description(self):
        assert isinstance(vc.TOOL_DEF.description, str)
        assert len(vc.TOOL_DEF.description) > 0

    def test_tool_def_input_schema_requires_case_json(self):
        schema = vc.TOOL_DEF.inputSchema
        assert schema["type"] == "object"
        assert "case_json" in schema["properties"]
        assert "case_json" in schema["required"]


# ---------------------------------------------------------------------------
# handle() behaviour
# ---------------------------------------------------------------------------


def _good_case() -> dict:
    """A minimal, schema-valid test case dict."""
    return {
        "id": "TC-API-USERS-001",
        "name": "List users",
        "type": "api",
        "priority": "P1",
        "tags": ["smoke"],
        "request": {"method": "GET", "path": "/api/users"},
        "expect": {"status": 200},
    }


class TestValidateCaseHandle:
    """Exercise ``validate_case.handle`` against valid/invalid inputs."""

    def test_valid_case_returns_no_errors(self, tmp_path):
        result = asyncio.run(vc.handle({"case_json": _good_case()}, None))
        assert result["valid"] is True
        assert result["errors"] == []

    def test_missing_required_field_is_invalid(self, tmp_path):
        bad = _good_case()
        del bad["request"]
        result = asyncio.run(vc.handle({"case_json": bad}, None))
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_bad_id_format_is_invalid(self, tmp_path):
        bad = _good_case()
        bad["id"] = "bad-id"  # does not match ^TC-[A-Z]+-[A-Z0-9]+-\d+$
        result = asyncio.run(vc.handle({"case_json": bad}, None))
        assert result["valid"] is False
        assert any("id" in err for err in result["errors"])

    def test_missing_priority_is_invalid(self, tmp_path):
        bad = _good_case()
        del bad["priority"]
        result = asyncio.run(vc.handle({"case_json": bad}, None))
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_bad_request_method_is_invalid(self, tmp_path):
        bad = _good_case()
        bad["request"]["method"] = "FETCH"  # not in the method enum
        result = asyncio.run(vc.handle({"case_json": bad}, None))
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_missing_expect_status_is_invalid(self, tmp_path):
        bad = _good_case()
        del bad["expect"]["status"]
        result = asyncio.run(vc.handle({"case_json": bad}, None))
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_missing_case_json_argument_raises(self, tmp_path):
        # The handler indexes arguments["case_json"] directly; a missing
        # key surfaces as a KeyError (re-raised by the tool's try/except).
        with pytest.raises(KeyError):
            asyncio.run(vc.handle({}, None))
