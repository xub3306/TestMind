"""Unit tests for the ``save_case`` MCP tool.

Covers tool metadata, the three save outcomes (``saved``,
``pending`` for duplicate IDs, ``fingerprint_conflict`` for a
fingerprint match under a different ID), missing-argument handling,
and the internal helper functions ``_extract_module`` and
``_resolve_cases_dir``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from testmind.config.settings import ProjectConfig
from testmind.tools import save_case as sc


# ---------------------------------------------------------------------------
# Tool metadata
# ---------------------------------------------------------------------------


class TestSaveCaseMetadata:
    """Verify TOOL_NAME / TOOL_DEF registration metadata."""

    def test_tool_name(self):
        assert sc.TOOL_NAME == "save_case"

    def test_tool_def_name_matches(self):
        assert sc.TOOL_DEF.name == "save_case"

    def test_tool_def_has_description(self):
        assert isinstance(sc.TOOL_DEF.description, str)
        assert len(sc.TOOL_DEF.description) > 0

    def test_tool_def_requires_case_json(self):
        schema = sc.TOOL_DEF.inputSchema
        assert schema["type"] == "object"
        assert "case_json" in schema["properties"]
        assert "case_json" in schema["required"]
        # ``project`` is optional
        assert "project" in schema["properties"]
        assert "project" not in schema.get("required", [])


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestExtractModule:
    """``_extract_module`` routes a case ID to its module subdirectory."""

    def test_standard_id(self):
        assert sc._extract_module("TC-API-USERS-001") == "users"

    def test_alphanumeric_module(self):
        assert sc._extract_module("TC-API-ORDERS2-042") == "orders2"

    def test_non_matching_id_returns_default(self):
        assert sc._extract_module("bad-id") == "default"

    def test_lowercase_returned(self):
        assert sc._extract_module("TC-API-PROFILE-007") == "profile"


class TestResolveCasesDir:
    """``_resolve_cases_dir`` prefers ``config.project_dir`` when set."""

    def test_with_project_dir(self, tmp_path):
        cfg = ProjectConfig(name="t", base_url="http://x")
        cfg.project_dir = tmp_path
        result = sc._resolve_cases_dir(cfg, None)
        assert result == tmp_path / "testmind" / "cases"

    def test_without_project_dir_falls_back_to_relative(self):
        result = sc._resolve_cases_dir(None, None)
        assert result == Path("testmind") / "cases"


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


class TestSaveCaseHandle:
    """Exercise ``save_case.handle`` save/duplicate/conflict paths."""

    def test_new_case_is_saved(self, project: ProjectConfig):
        result = asyncio.run(sc.handle({"case_json": _good_case()}, project))
        assert result["status"] == "saved"
        assert result["case_id"] == "TC-API-USERS-001"
        assert result["path"] is not None
        # File exists on disk under the module subdirectory.
        saved = Path(result["path"])
        assert saved.is_file()
        assert saved.parent.name == "users"
        # Round-trip: the file parses back to the same case id.
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert data["id"] == "TC-API-USERS-001"

    def test_duplicate_id_routed_to_pending(self, project: ProjectConfig):
        # First save succeeds.
        first = asyncio.run(sc.handle({"case_json": _good_case()}, project))
        assert first["status"] == "saved"

        # Saving the same case ID again (identical content -> same
        # fingerprint AND same id) must be routed to .pending/ for review.
        second = asyncio.run(sc.handle({"case_json": _good_case()}, project))
        assert second["status"] == "pending"
        assert second["case_id"] == "TC-API-USERS-001"
        assert Path(second["path"]).is_file()
        # The pending file lives under the .pending directory.
        assert ".pending" in Path(second["path"]).parts

    def test_same_fingerprint_different_id_is_conflict(self, project: ProjectConfig):
        # Seed a case.
        seed = asyncio.run(sc.handle({"case_json": _good_case()}, project))
        assert seed["status"] == "saved"

        # Same method + path + params (empty) => identical fingerprint,
        # but a different case ID => fingerprint_conflict (no file written).
        dup = _good_case(case_id="TC-API-USERS-099")
        result = asyncio.run(sc.handle({"case_json": dup}, project))
        assert result["status"] == "fingerprint_conflict"
        assert result["fingerprint_conflict"] is True
        assert result["case_id"] == "TC-API-USERS-099"
        # No file should have been created for the conflicting case.
        cases_dir = project.project_dir / "testmind" / "cases"
        assert not (cases_dir / "users" / "TC-API-USERS-099.json").exists()

    def test_missing_case_json_argument_raises(self, project: ProjectConfig):
        with pytest.raises(KeyError):
            asyncio.run(sc.handle({}, project))

    def test_invalid_case_json_raises(self, project: ProjectConfig):
        # ``TestCase.model_validate`` rejects a case missing required
        # fields; the handler re-raises the ValidationError.
        with pytest.raises(Exception):
            asyncio.run(sc.handle({"case_json": {"id": "bad"}}, project))
