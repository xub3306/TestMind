"""MCP tool: validate_case — validate a test case JSON against schema and Pydantic model."""

from __future__ import annotations

import time
from typing import Any

from mcp import types

from testmind.config.schema import TESTCASE_SCHEMA, validate_json
from testmind.models.testcase import TestCase
from testmind.utils.logger import get_audit_logger


# Tool metadata for MCP registration
TOOL_NAME = "validate_case"

TOOL_DEF = types.Tool(
    name=TOOL_NAME,
    description=(
        "Validate a test case JSON against the TestMind schema. "
        "Performs both JSON Schema validation and Pydantic model validation "
        "to check whether the test case conforms to the expected schema including "
        "ID format (TC-{TYPE}-{MODULE}-{SEQ}), required fields, enum values, "
        "and structural constraints. Returns validation result with any "
        "field-level errors."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "case_json": {
                "type": "object",
                "description": "The test case dict to validate.",
            },
        },
        "required": ["case_json"],
    },
)


class ValidateResult:
    """Container for validation result data."""

    def __init__(self, valid: bool, errors: list[str] | None = None) -> None:
        self.valid = valid
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": self.errors}


async def handle(arguments: dict, config) -> dict:
    """Execute validate_case tool.

    Runs both JSON Schema validation and Pydantic model validation.
    JSON Schema errors are reported first, then Pydantic errors are
    appended for a comprehensive result.
    """
    audit = get_audit_logger()
    start = time.monotonic()
    case_json = arguments["case_json"]

    # Step 1: JSON Schema validation
    schema_result = validate_json(case_json, TESTCASE_SCHEMA)
    errors: list[str] = list(schema_result.errors)

    # Step 2: Pydantic model validation (provides friendlier errors)
    if schema_result.valid:
        try:
            TestCase.model_validate(case_json)
        except Exception as exc:
            # Append Pydantic validation errors for friendlier messages
            errors.append(str(exc))

    result = ValidateResult(
        valid=len(errors) == 0,
        errors=errors,
    ).to_dict()

    duration_ms = (time.monotonic() - start) * 1000
    audit.log("validate_case", case_json, result, duration_ms, "ok", "mcp")
    return result