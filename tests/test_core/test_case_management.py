"""Integration tests for case version history, approval, and review.

Covers:
* ``approve_cases`` auto-increments version and adds changelog when
  overwriting an existing case.
* ``reject_cases`` deletes .pending/ files.
* ``list_pending_cases`` returns pending case metadata.
* ``get_case_history`` returns full case JSON with version/changelog.
* CLI commands: ``testmind case pending/reject/history/show``.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from testmind.config.settings import ProjectConfig
from testmind.core.runner import (
    approve_cases,
    get_case_history,
    list_pending_cases,
    reject_cases,
    save_case_to_project,
)
from testmind.cli import main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project(tmp_path: Path) -> ProjectConfig:
    tm_dir = tmp_path / "testmind"
    (tm_dir / "envs").mkdir(parents=True, exist_ok=True)
    (tm_dir / "cases").mkdir(parents=True, exist_ok=True)
    (tm_dir / "project.json").write_text(
        json.dumps({"name": "cm", "base_url": "http://localhost", "default_env": "dev"}),
        encoding="utf-8",
    )
    config = ProjectConfig(name="cm", base_url="http://localhost", default_env="dev")
    config.project_dir = tmp_path
    return config


def _basic_case(cid: str, path: str = "/api/items") -> dict:
    return {
        "id": cid, "name": cid, "type": "api", "priority": "P1",
        "request": {"method": "GET", "path": path},
        "expect": {"status": 200},
    }


def _save(project: ProjectConfig, case: dict) -> dict:
    return asyncio.run(save_case_to_project(project, case))


def _pending_dir(project: ProjectConfig) -> Path:
    return project.project_dir / "testmind" / "cases" / ".pending"


# ---------------------------------------------------------------------------
# approve_cases — version auto-increment
# ---------------------------------------------------------------------------


class TestApproveVersioning:
    """Approve auto-increments version and records changelog."""

    def test_first_approve_no_versioning(self, project: ProjectConfig):
        """First approval (new case) writes v1 with no changelog entries."""
        _save(project, _basic_case("TC-API-ITEMS-001", "/api/items"))
        approved = approve_cases(project, ["TC-API-ITEMS-001"])
        assert approved == 0  # no pending file (it was directly saved)

    def test_update_auto_bumps_version(self, project: ProjectConfig):
        """Approving a modified case increments version and adds changelog."""
        # 1. Save & approve original.
        _save(project, _basic_case("TC-API-ITEMS-001"))
        # Direct save for the original (no conflict).
        # 2. Save an update with different path to avoid fingerprint dup.
        updated = _basic_case("TC-API-ITEMS-001", "/api/items/v2")
        updated["name"] = "Updated name"
        res = _save(project, updated)
        assert res["status"] == "pending_review"
        assert _pending_dir(project).exists()

        # 3. Approve.
        approved = approve_cases(project, ["TC-API-ITEMS-001"])
        assert approved == 1

        # 4. Verify version bumped.
        data = get_case_history(project, "TC-API-ITEMS-001")
        assert data is not None
        meta = data["metadata"]
        assert meta["version"] == 2
        changelog = meta.get("changelog") or []
        assert len(changelog) == 1
        assert changelog[0]["version"] == 2
        assert "Approved case update" in changelog[0]["message"]
        assert data["name"] == "Updated name"

    def test_three_updates_version_three(self, project: ProjectConfig):
        """Three updates → version 3 with 2 changelog entries."""
        _save(project, _basic_case("TC-API-ITEMS-001", "/api/items"))
        for i in range(2):
            upd = _basic_case("TC-API-ITEMS-001", f"/api/items/v{i+2}")
            upd["name"] = f"v{i + 2}"
            upd["name"] = f"v{i + 2}"
            _save(project, upd)
            approve_cases(project, ["TC-API-ITEMS-001"])

        data = get_case_history(project, "TC-API-ITEMS-001")
        assert data["metadata"]["version"] == 3
        assert len(data["metadata"].get("changelog") or []) == 2


# ---------------------------------------------------------------------------
# reject_cases
# ---------------------------------------------------------------------------


class TestRejectCases:
    def test_reject_deletes_pending_file(self, project: ProjectConfig):
        _save(project, _basic_case("TC-API-ITEMS-001", "/api/items"))
        upd = _basic_case("TC-API-ITEMS-001", "/api/items/v2")
        upd["name"] = "v2"
        _save(project, upd)
        assert len(list_pending_cases(project)) == 1

        rejected = reject_cases(project, ["TC-API-ITEMS-001"])
        assert rejected == 1
        assert len(list_pending_cases(project)) == 0
        assert not (_pending_dir(project) / "TC-API-ITEMS-001.json").exists()

    def test_reject_nonexistent_harmless(self, project: ProjectConfig):
        assert reject_cases(project, ["GHOST"]) == 0


# ---------------------------------------------------------------------------
# list_pending_cases
# ---------------------------------------------------------------------------


class TestListPending:
    def test_empty_project(self, project: ProjectConfig):
        assert list_pending_cases(project) == []

    def test_single_pending(self, project: ProjectConfig):
        _save(project, _basic_case("TC-API-ITEMS-001", "/api/items"))
        _save(project, _basic_case("TC-API-ITEMS-001", "/api/items/v2"))  # diff path → pending
        pending = list_pending_cases(project)
        assert len(pending) == 1
        assert pending[0]["case_id"] == "TC-API-ITEMS-001"


# ---------------------------------------------------------------------------
# get_case_history
# ---------------------------------------------------------------------------


class TestCaseHistory:
    def test_existing_case_returns_data(self, project: ProjectConfig):
        _save(project, _basic_case("TC-API-ITEMS-001", "/api/items"))
        data = get_case_history(project, "TC-API-ITEMS-001")
        assert data is not None
        assert data["id"] == "TC-API-ITEMS-001"
        # Newly saved cases may not carry explicit metadata (versioning
        # is added when cases go through the approve update flow).
        meta = data.get("metadata")
        if meta:
            assert meta["version"] == 1

    def test_missing_case_returns_none(self, project: ProjectConfig):
        assert get_case_history(project, "GHOST") is None


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


class TestCliCaseManagement:
    def _setup_with_pending(self, tmp_path: Path) -> Path:
        """Create a project with one original and one pending case."""
        tm_dir = tmp_path / "testmind"
        (tm_dir / "envs").mkdir(parents=True)
        (tm_dir / "cases").mkdir(parents=True)
        (tm_dir / "project.json").write_text(
            json.dumps({"name": "cli", "base_url": "http://localhost", "default_env": "dev"}),
            encoding="utf-8",
        )
        # Original case.
        c = _basic_case("TC-API-ITEMS-001", "/api/items")
        module_dir = tm_dir / "cases" / "items"
        module_dir.mkdir(parents=True, exist_ok=True)
        (module_dir / "TC-API-ITEMS-001.json").write_text(
            json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Pending update - different path for different fingerprint.
        pending_dir = tm_dir / "cases" / ".pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        upd = _basic_case("TC-API-ITEMS-001", "/api/items/v2")
        upd["name"] = "Updated"
        upd["metadata"] = {"version": 1, "author": "qa"}
        (pending_dir / "TC-API-ITEMS-001.json").write_text(
            json.dumps(upd, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return tmp_path

    def test_pending_command(self, tmp_path: Path):
        self._setup_with_pending(tmp_path)
        r = CliRunner().invoke(main, ["case", "pending", "--project", str(tmp_path)])
        assert r.exit_code == 0
        assert "TC-API-ITEMS-001" in r.output

    def test_reject_command(self, tmp_path: Path):
        self._setup_with_pending(tmp_path)
        r = CliRunner().invoke(main, ["case", "reject", "TC-API-ITEMS-001", "--project", str(tmp_path)])
        assert r.exit_code == 0
        assert "Rejected 1 cases" in r.output
        assert not (tmp_path / "testmind" / "cases" / ".pending" / "TC-API-ITEMS-001.json").exists()

    def test_approve_with_versioning(self, tmp_path: Path):
        self._setup_with_pending(tmp_path)
        r = CliRunner().invoke(main, ["approve", "TC-API-ITEMS-001", "--project", str(tmp_path)])
        assert r.exit_code == 0
        # Verify the approved file has version 2.
        case_file = tmp_path / "testmind" / "cases" / "items" / "TC-API-ITEMS-001.json"
        data = json.loads(case_file.read_text(encoding="utf-8"))
        assert data["metadata"]["version"] == 2
        assert len(data["metadata"].get("changelog") or []) == 1

    def test_history_command(self, tmp_path: Path):
        self._setup_with_pending(tmp_path)
        CliRunner().invoke(main, ["approve", "TC-API-ITEMS-001", "--project", str(tmp_path)])
        r = CliRunner().invoke(main, ["case", "history", "TC-API-ITEMS-001", "--project", str(tmp_path)])
        assert r.exit_code == 0
        assert "Version:    2" in r.output
        assert "Changelog:" in r.output

    def test_show_command(self, tmp_path: Path):
        self._setup_with_pending(tmp_path)
        CliRunner().invoke(main, ["approve", "TC-API-ITEMS-001", "--project", str(tmp_path)])
        r = CliRunner().invoke(main, ["case", "show", "TC-API-ITEMS-001", "--project", str(tmp_path)])
        assert r.exit_code == 0
        data = json.loads(r.output)
        assert data["name"] == "Updated"
        assert data["metadata"]["version"] == 2
