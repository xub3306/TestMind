"""MCP tool: save_case — save a test case with deduplication logic."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from mcp import types

from testmind.models.testcase import TestCase
from testmind.utils.logger import get_audit_logger


# Tool metadata for MCP registration
TOOL_NAME = "save_case"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "Save a test case to the project with deduplication logic. "
        "Performs fingerprint-based dedup: computes SHA-256 from method+path+params. "
        "If a fingerprint match exists, returns a warning. If a case with the same "
        "ID already exists, saves to .pending/ for review. "
        "Cases are stored under cases/{module}/ using the module extracted "
        "from the case ID (e.g. TC-API-USERS-001 → users/)."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "case_json": {
                "type": "object",
                "description": "The test case dict conforming to TestCase schema.",
            },
            "project": {
                "type": "string",
                "description": "Optional project name.",
            },
        },
        "required": ["case_json"],
    },
)


class SaveCaseResult:
    """Container for save_case result data."""

    def __init__(
        self,
        status: str,
        case_id: str,
        path: str | None = None,
        fingerprint_conflict: bool = False,
        message: str = "",
    ) -> None:
        self.status = status
        self.case_id = case_id
        self.path = path
        self.fingerprint_conflict = fingerprint_conflict
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "case_id": self.case_id,
            "path": self.path,
            "fingerprint_conflict": self.fingerprint_conflict,
            "message": self.message,
        }


def _extract_module(case_id: str) -> str:
    """Extract module name from a case ID for directory routing.

    Case IDs follow the format TC-{TYPE}-{MODULE}-{SEQ}, e.g.
    TC-API-USERS-001 → 'users'.  Returns 'default' if the format
    doesn't match.
    """
    match = re.match(r"^TC-[A-Z]+-([A-Z0-9]+)-\d+$", case_id)
    if match:
        return match.group(1).lower()
    return "default"


def _resolve_cases_dir(config: Any, project_name: str | None) -> Path:
    if config and hasattr(config, "project_dir") and config.project_dir:
        return config.project_dir / "testmind" / "cases"
    return Path("testmind") / "cases"


def _find_existing_case(cases_dir: Path, case_id: str) -> Path | None:
    for case_file in cases_dir.rglob("*.json"):
        # Skip files in .pending directory
        if ".pending" in case_file.parts:
            continue
        try:
            data = json.loads(case_file.read_text(encoding="utf-8"))
            if data.get("id") == case_id:
                return case_file
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _find_fingerprint_match(cases_dir: Path, fingerprint: str) -> Path | None:
    for case_file in cases_dir.rglob("*.json"):
        if ".pending" in case_file.parts:
            continue
        try:
            data = json.loads(case_file.read_text(encoding="utf-8"))
            tc = TestCase.model_validate(data)
            if tc.compute_fingerprint() == fingerprint:
                return case_file
        except Exception:
            continue
    return None


async def handle(arguments: dict, config) -> dict:
    """Execute save_case tool.

    Cases are saved under cases/{module}/{case_id}.json where the module
    is extracted from the case ID (e.g. TC-API-USERS-001 → users/).
    Duplicate IDs are routed to .pending/ for review.
    """
    audit = get_audit_logger()
    start = time.monotonic()

    try:
        case_json = arguments["case_json"]
        project = arguments.get("project")
        tc = TestCase.model_validate(case_json)
        fingerprint = tc.compute_fingerprint()
        cases_dir = _resolve_cases_dir(config, project)
        cases_dir.mkdir(parents=True, exist_ok=True)

        fingerprint_match = _find_fingerprint_match(cases_dir, fingerprint)
        existing_case = _find_existing_case(cases_dir, tc.id)

        if fingerprint_match and not existing_case:
            result = SaveCaseResult(
                status="fingerprint_conflict",
                case_id=tc.id,
                fingerprint_conflict=True,
                message=f"Fingerprint matches existing case at {fingerprint_match}",
            ).to_dict()
            duration_ms = (time.monotonic() - start) * 1000
            audit.log("save_case", arguments, result, duration_ms, "ok", "mcp")
            return result

        # Determine module subdirectory from case ID
        module = _extract_module(tc.id)

        if existing_case:
            pending_dir = cases_dir / ".pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            target = pending_dir / f"{tc.id}.json"
            target.write_text(
                json.dumps(tc.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result = SaveCaseResult(
                status="pending",
                case_id=tc.id,
                path=str(target),
                fingerprint_conflict=fingerprint_match is not None,
                message=f"Case ID conflict with {existing_case}; saved to .pending/",
            ).to_dict()
            duration_ms = (time.monotonic() - start) * 1000
            audit.log("save_case", arguments, result, duration_ms, "ok", "mcp")
            return result

        module_dir = cases_dir / module
        module_dir.mkdir(parents=True, exist_ok=True)
        target = module_dir / f"{tc.id}.json"
        target.write_text(
            json.dumps(tc.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result = SaveCaseResult(
            status="saved",
            case_id=tc.id,
            path=str(target),
            fingerprint_conflict=False,
            message="Case saved successfully",
        ).to_dict()
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("save_case", arguments, result, duration_ms, "ok", "mcp")
        return result

    except Exception as e:
        duration_ms = (time.monotonic() - start) * 1000
        audit.log("save_case", arguments, str(e), duration_ms, "error", "mcp")
        raise