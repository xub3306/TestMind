"""Unit tests for the ``run_cases`` MCP tool.

``run_cases.handle`` delegates to ``Runner.run_async`` which issues real
``httpx`` requests, so these tests rely on the shared ``mock_api_server``
and ``project`` fixtures (defined in ``conftest.py``) to keep execution
offline and deterministic.

The flow exercised: save a case via ``save_case.handle`` -> run via
``run_cases.handle`` -> assert a non-empty ``run_id`` and that result
artifacts land on disk under ``testmind/results/{run_id}/``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from testmind.config.settings import ProjectConfig
from testmind.tools import run_cases as rc
from testmind.tools import save_case as sc


# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------


class TestRunCasesMetadata:
    """Verify TOOL_NAME / TOOL_DEF registration metadata."""

    def test_tool_name(self):
        assert rc.TOOL_NAME == "run_cases"

    def test_tool_def_name_matches(self):
        assert rc.TOOL_DEF.name == "run_cases"

    def test_tool_def_has_description(self):
        assert isinstance(rc.TOOL_DEF.description, str)
        assert len(rc.TOOL_DEF.description) > 0

    def test_tool_def_input_schema_properties(self):
        schema = rc.TOOL_DEF.inputSchema
        assert schema["type"] == "object"
        # The documented optional filters/controls must be present.
        for prop in ("target", "tags", "env", "device", "suite",
                     "fail_fast", "workers", "retry"):
            assert prop in schema["properties"], f"missing property {prop}"


# ---------------------------------------------------------------------------
# handle() behaviour
# ---------------------------------------------------------------------------


def _good_case(case_id: str = "TC-API-USERS-001") -> dict:
    return {
        "id": case_id,
        "name": "List users",
        "type": "api",
        "priority": "P1",
        "tags": ["smoke"],
        "request": {"method": "GET", "path": "/api/users"},
        "expect": {"status": 200},
    }


class TestRunCasesHandle:
    """Exercise ``run_cases.handle`` against the in-process mock server."""

    def test_run_returns_run_id_and_writes_results(self, project: ProjectConfig):
        # Seed a case so the runner has something to execute.
        save_res = asyncio.run(sc.handle({"case_json": _good_case()}, project))
        assert save_res["status"] == "saved"

        result = asyncio.run(rc.handle({"env": "dev"}, project))
        assert "run_id" in result
        run_id = result["run_id"]
        assert isinstance(run_id, str) and len(run_id) > 0

        # A results directory + summary.json must exist for this run.
        results_dir = project.project_dir / "testmind" / "results" / run_id
        assert results_dir.is_dir()
        summary_file = results_dir / "summary.json"
        assert summary_file.is_file()
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        assert summary["total"] >= 1

    def test_run_with_no_cases_still_returns_run_id(self, project: ProjectConfig):
        # No cases saved -- the runner should still produce a run_id and
        # an (empty) summary rather than raising.
        result = asyncio.run(rc.handle({"env": "dev"}, project))
        assert "run_id" in result
        run_id = result["run_id"]
        assert len(run_id) > 0
        summary_file = (project.project_dir / "testmind" / "results"
                        / run_id / "summary.json")
        assert summary_file.is_file()
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        assert summary["total"] == 0

    def test_run_filtered_by_tag(self, project: ProjectConfig):
        # One tagged case, one untagged case.
        tagged = _good_case("TC-API-USERS-001")
        untagged = {
            "id": "TC-API-USERS-002",
            "name": "Get user detail",
            "type": "api",
            "priority": "P2",
            "request": {"method": "GET", "path": "/api/users/1"},
            "expect": {"status": 200},
        }
        asyncio.run(sc.handle({"case_json": tagged}, project))
        asyncio.run(sc.handle({"case_json": untagged}, project))

        result = asyncio.run(rc.handle({"env": "dev", "tags": ["smoke"]}, project))
        run_id = result["run_id"]
        summary_file = (project.project_dir / "testmind" / "results"
                        / run_id / "summary.json")
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        # Only the smoke-tagged case should be executed.
        assert summary["total"] == 1
