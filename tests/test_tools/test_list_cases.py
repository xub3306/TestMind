"""Unit tests for the ``list_cases`` MCP tool.

Covers tool metadata, the empty-project case, listing after saving
cases, and tag-based filtering.  Cases are seeded via ``save_case.handle``
so the on-disk layout (module subdirectories) is exercised end-to-end.
"""

from __future__ import annotations

import asyncio

import pytest

from testmind.config.settings import ProjectConfig
from testmind.tools import list_cases as lc
from testmind.tools import save_case as sc


# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------


class TestListCasesMetadata:
    """Verify TOOL_NAME / TOOL_DEF registration metadata."""

    def test_tool_name(self):
        assert lc.TOOL_NAME == "list_cases"

    def test_tool_def_name_matches(self):
        assert lc.TOOL_DEF.name == "list_cases"

    def test_tool_def_has_description(self):
        assert isinstance(lc.TOOL_DEF.description, str)
        assert len(lc.TOOL_DEF.description) > 0

    def test_tool_def_input_schema_properties(self):
        schema = lc.TOOL_DEF.inputSchema
        assert schema["type"] == "object"
        assert "project" in schema["properties"]
        assert "tags" in schema["properties"]


# ---------------------------------------------------------------------------
# handle() behaviour
# ---------------------------------------------------------------------------


def _make_case(case_id: str, tags: list[str] | None = None) -> dict:
    return {
        "id": case_id,
        "name": f"case {case_id}",
        "type": "api",
        "priority": "P1",
        "tags": tags or [],
        "request": {"method": "GET", "path": f"/api/users/{case_id[-3:]}"},
        "expect": {"status": 200},
    }


class TestListCasesHandle:
    """Exercise ``list_cases.handle``."""

    def test_empty_project_returns_zero(self, project: ProjectConfig):
        result = asyncio.run(lc.handle({}, project))
        assert result["total"] == 0
        assert result["cases"] == []

    def test_lists_saved_cases(self, project: ProjectConfig):
        asyncio.run(sc.handle({"case_json": _make_case("TC-API-USERS-001")}, project))
        asyncio.run(sc.handle({"case_json": _make_case("TC-API-USERS-002")}, project))

        result = asyncio.run(lc.handle({}, project))
        assert result["total"] == 2
        ids = {c["id"] for c in result["cases"]}
        assert ids == {"TC-API-USERS-001", "TC-API-USERS-002"}
        # Each summary entry carries the documented fields.
        for entry in result["cases"]:
            assert "id" in entry
            assert "name" in entry
            assert "priority" in entry
            assert "tags" in entry

    def test_tag_filter_returns_only_matching(self, project: ProjectConfig):
        asyncio.run(
            sc.handle({"case_json": _make_case("TC-API-USERS-001", tags=["smoke"])},
                      project)
        )
        asyncio.run(
            sc.handle({"case_json": _make_case("TC-API-USERS-002",
                                                tags=["regression"])},
                      project)
        )

        result = asyncio.run(lc.handle({"tags": ["smoke"]}, project))
        assert result["total"] == 1
        assert result["cases"][0]["id"] == "TC-API-USERS-001"

    def test_pending_cases_excluded_from_listing(self, project: ProjectConfig):
        # Save once, then save the same ID again -> routed to .pending/.
        asyncio.run(sc.handle({"case_json": _make_case("TC-API-USERS-001")}, project))
        asyncio.run(sc.handle({"case_json": _make_case("TC-API-USERS-001")}, project))

        result = asyncio.run(lc.handle({}, project))
        # Only the one non-pending case should be listed.
        assert result["total"] == 1
        assert result["cases"][0]["id"] == "TC-API-USERS-001"
