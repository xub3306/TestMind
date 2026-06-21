"""Unit tests for the ``get_results`` MCP tool.

The handler queries result artifacts previously produced by a run.  These
tests first drive ``run_cases.handle`` to materialise results on disk,
then exercise ``get_results.handle`` for: a known run_id, an unknown
run_id (empty result set), and a status filter.
"""

from __future__ import annotations

import asyncio

import pytest

from testmind.config.settings import ProjectConfig
from testmind.tools import get_results as gr
from testmind.tools import run_cases as rc
from testmind.tools import save_case as sc


# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------


class TestGetResultsMetadata:
    """Verify TOOL_NAME / TOOL_DEF registration metadata."""

    def test_tool_name(self):
        assert gr.TOOL_NAME == "get_results"

    def test_tool_def_name_matches(self):
        assert gr.TOOL_DEF.name == "get_results"

    def test_tool_def_has_description(self):
        assert isinstance(gr.TOOL_DEF.description, str)
        assert len(gr.TOOL_DEF.description) > 0

    def test_tool_def_input_schema_properties(self):
        schema = gr.TOOL_DEF.inputSchema
        assert schema["type"] == "object"
        assert "run_id" in schema["properties"]
        assert "status_filter" in schema["properties"]


# ---------------------------------------------------------------------------
# handle() behaviour
# ---------------------------------------------------------------------------


def _good_case(case_id: str = "TC-API-USERS-001", status: int = 200) -> dict:
    return {
        "id": case_id,
        "name": "List users",
        "type": "api",
        "priority": "P1",
        "tags": ["smoke"],
        "request": {"method": "GET", "path": "/api/users"},
        "expect": {"status": status},
    }


class TestGetResultsHandle:
    """Exercise ``get_results.handle`` after a real run."""

    def _seed_and_run(self, project: ProjectConfig, case: dict) -> str:
        save_res = asyncio.run(sc.handle({"case_json": case}, project))
        assert save_res["status"] == "saved"
        run_res = asyncio.run(rc.handle({"env": "dev"}, project))
        return run_res["run_id"]

    def test_known_run_id_returns_results(self, project: ProjectConfig):
        run_id = self._seed_and_run(project, _good_case())
        result = asyncio.run(gr.handle({"run_id": run_id}, project))
        assert "results" in result
        assert "total" in result
        assert result["total"] >= 1
        assert isinstance(result["results"], list)
        # Each result carries its case_id and status.
        for item in result["results"]:
            assert "case_id" in item
            assert "status" in item

    def test_unknown_run_id_returns_empty(self, project: ProjectConfig):
        result = asyncio.run(
            gr.handle({"run_id": "20990101_000000_zzzz"}, project)
        )
        assert result["total"] == 0
        assert result["results"] == []

    def test_status_filter_pass(self, project: ProjectConfig):
        # A passing case (expects 200, mock returns 200).
        run_id = self._seed_and_run(project, _good_case(status=200))
        result = asyncio.run(
            gr.handle({"run_id": run_id, "status_filter": "pass"}, project)
        )
        assert result["total"] >= 1
        assert all(r["status"] == "pass" for r in result["results"])

    def test_status_filter_fail_yields_zero_when_all_pass(self, project: ProjectConfig):
        run_id = self._seed_and_run(project, _good_case(status=200))
        result = asyncio.run(
            gr.handle({"run_id": run_id, "status_filter": "fail"}, project)
        )
        assert result["total"] == 0
        assert result["results"] == []

    def test_failing_case_shows_up_under_fail_filter(self, project: ProjectConfig):
        # Expect 500 but the mock returns 200 -> the case fails.
        run_id = self._seed_and_run(project, _good_case(status=500))
        all_res = asyncio.run(gr.handle({"run_id": run_id}, project))
        assert all_res["total"] >= 1
        fail_res = asyncio.run(
            gr.handle({"run_id": run_id, "status_filter": "fail"}, project)
        )
        assert fail_res["total"] >= 1
        assert all(r["status"] == "fail" for r in fail_res["results"])
