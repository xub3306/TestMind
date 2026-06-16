"""TestMind execution result data models.

Defines the structure for individual case results, request/response
snapshots, assertion outcomes, and run summaries.  All models use
Pydantic v2 and support full JSON serialization/deserialization via
``model_dump()`` and ``model_validate()``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RequestSnapshot(BaseModel):
    """Captured HTTP request details for result reporting.

    Attributes:
        method: HTTP method used.
        url: Fully resolved URL that was requested.
        headers: Request headers dict (sensitive values redacted in logs).
        body: Request body (often a dict for JSON payloads).
    """

    method: str
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None


class ResponseSnapshot(BaseModel):
    """Captured HTTP response details for result reporting.

    Attributes:
        status_code: HTTP status code returned by the server.
        headers: Response headers dict.
        body: Parsed response body (dict for JSON, str otherwise).
        duration_ms: Round-trip time in milliseconds.
    """

    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    duration_ms: int = 0


class AssertionResult(BaseModel):
    """Outcome of a single assertion evaluation.

    Attributes:
        type: Assertion type (e.g. ``jsonpath``, ``status_code``).
        path: JSONPath expression or header name evaluated.
        operator: Comparison operator used (e.g. ``eq``, ``gt``).
        expected: The expected value.
        actual: The actual value observed.
        passed: Whether the assertion succeeded.
        message: Human-readable description, non-empty on failure.
    """

    type: str
    path: str | None = None
    operator: str | None = None
    expected: Any = None
    actual: Any = None
    passed: bool
    message: str | None = None


class CaseResult(BaseModel):
    """Execution result of a single test case.

    Attributes:
        case_id: The ID of the test case (``TC-API-…``).
        run_id: Unique identifier for this run.
        env: The environment name (e.g. ``dev``, ``staging``).
        status: Result status – ``pass``, ``fail``, ``error``, or
            ``skipped``.
        duration_ms: Execution time in milliseconds.
        started_at: ISO-8601 start timestamp.
        finished_at: ISO-8601 end timestamp.
        request_snapshot: Captured request details (``None`` on skip/error).
        response_snapshot: Captured response details (``None`` on skip/error).
        assertions_result: List of individual assertion outcomes.
        error: Error message when ``status`` is ``error`` or ``skipped``.
        retry_count: Number of retries attempted (0 = no retry).
    """

    case_id: str
    run_id: str
    env: str
    status: Literal["pass", "fail", "error", "skipped"]
    duration_ms: int = 0
    started_at: str = ""
    finished_at: str = ""
    request_snapshot: RequestSnapshot | None = None
    response_snapshot: ResponseSnapshot | None = None
    assertions_result: list[AssertionResult] = Field(default_factory=list)
    error: str | None = None
    retry_count: int = 0


class SummaryResult(BaseModel):
    """Aggregated summary for an entire test run.

    Attributes:
        run_id: Unique run identifier.
        project: Project name.
        env: Environment name.
        started_at: ISO-8601 start timestamp.
        finished_at: ISO-8601 end timestamp.
        total: Total number of cases executed.
        passed: Number of passed cases.
        failed: Number of failed cases.
        error: Number of error cases.
        skipped: Number of skipped cases.
        total_duration_ms: Cumulative duration in milliseconds.
        failures: List of ``{case_id, reason}`` dicts for failed cases.
        errors: List of ``{case_id, reason}`` dicts for error cases.
    """

    run_id: str
    project: str
    env: str
    started_at: str
    finished_at: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0
    skipped: int = 0
    total_duration_ms: int = 0
    failures: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
