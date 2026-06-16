"""TestMind test case data models.

Defines the structure for test cases, including request definitions,
expectations, assertions, data-driven parameters, variable extraction,
hooks, and metadata. All models use Pydantic v2 and support full
JSON serialization/deserialization via ``model_dump()`` and
``model_validate()``.

Case ID format: ``TC-{TYPE}-{MODULE}-{SEQ}``  e.g. ``TC-API-USERS-001``
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class SkipCondition(BaseModel):
    """A condition under which a test case should be skipped.

    Attributes:
        condition: Expression to evaluate, e.g. ``"env == 'prod'"``.
        reason: Human-readable explanation for the skip.
    """

    condition: str
    reason: str


class AssertionDef(BaseModel):
    """A single assertion within a test case's ``expect`` block.

    Supported types: ``jsonpath``, ``status_code``, ``header``,
    ``response_time``, ``json_schema``, ``body_contains``, ``custom``.

    Attributes:
        type: Assertion type (e.g. ``jsonpath``, ``status_code``).
        operator: Comparison operator (e.g. ``eq``, ``gt``, ``contains``).
        path: JSONPath expression or header name, depending on type.
        expected: The expected value to compare against.
        name: Optional identifier used for custom assertions.
    """

    type: str
    operator: str | None = None
    path: str | None = None
    expected: Any = None
    name: str | None = None


class DataDriven(BaseModel):
    """Data-driven test parameters.

    When present, the execution engine generates one test instance per
    row in ``parameters``, replacing fields listed in
    ``parameterized_fields`` with the row values.  Result IDs are
    suffixed with ``_DD0``, ``_DD1``, etc.

    Attributes:
        name: Descriptive name for the parameterized group.
        parameters: List of parameter dictionaries (at least one row).
        parameterized_fields: Dot-separated paths to fields that vary
            per row, e.g. ``["request.params.body", "expect.status"]``.
    """

    name: str
    parameters: list[dict[str, Any]] = Field(min_length=1)
    parameterized_fields: list[str] = Field(default_factory=list)


class ExtractVar(BaseModel):
    """Definition for extracting a variable from a test response.

    The meaning of ``path`` and ``name`` depends on ``type``:

    * ``jsonpath`` – ``path`` is a JSONPath expression (e.g. ``$.data.id``).
    * ``header`` – ``name`` is the response header name (e.g.
      ``X-User-Token``).
    * ``regex`` – ``path`` is the regular expression pattern.
    * ``status_code`` – neither ``path`` nor ``name`` is needed.

    Attributes:
        type: Extraction mechanism.
        path: JSONPath expression, regex pattern, or other selector.
        name: Header name (used when ``type="header"``).
        pattern: Regex capture pattern (used when ``type="regex"``).
    """

    type: Literal["jsonpath", "header", "regex", "status_code"]
    path: str | None = None
    name: str | None = None
    pattern: str | None = None


class HookConfig(BaseModel):
    """Before/after hook references for a test case.

    Each entry is the filename (without ``.py``) of a script under
    the ``hooks/`` directory.

    Attributes:
        before: Hook scripts to run before the test case.
        after: Hook scripts to run after the test case (always executed,
            even on failure).
    """

    before: list[str] = Field(default_factory=list)
    after: list[str] = Field(default_factory=list)


class RequestDef(BaseModel):
    """HTTP request definition within a test case.

    Attributes:
        method: HTTP method (GET, POST, PUT, PATCH, DELETE, …).
        path: URL path, e.g. ``/api/users``.  Supports ``{{variable}}``
            interpolation.
        headers: Optional dict of request headers.
        params: Optional dict that may contain ``body``, ``query``,
            and ``form`` sub-dicts.
    """

    method: str
    path: str
    headers: dict[str, str] | None = None
    params: dict[str, Any] | None = None


class ExpectDef(BaseModel):
    """Expected response definition for a test case.

    Attributes:
        status: Expected HTTP status code.
        body: Optional dict of field expectations.  Values of the
            form ``{{type:TYPE}}`` trigger type assertions.
        assertions: Optional list of structured assertions.
    """

    status: int
    body: dict[str, Any] | None = None
    assertions: list[AssertionDef] | None = None


class CaseMetadata(BaseModel):
    """Authoring and version tracking metadata for a test case.

    ``created_at`` and ``updated_at`` default to the current UTC
    timestamp when not explicitly provided.

    Attributes:
        author: Creator of the test case.
        version: Monotonically increasing version number.
        created_at: ISO-8601 timestamp of initial creation.
        updated_at: ISO-8601 timestamp of last modification.
        changelog: Optional list of version change records.
    """

    author: str = "testmind"
    version: int = 1
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    changelog: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Top-level model
# ---------------------------------------------------------------------------


class TestCase(BaseModel):
    """A single test case.

    Case IDs follow the format ``TC-{TYPE}-{MODULE}-{SEQ}``, e.g.
    ``TC-API-USERS-001``.

    Attributes:
        id: Unique case identifier.
        name: Human-readable name.
        type: Test type – ``api``, ``web``, or ``mobile``.
        priority: Priority tier ``P0`` – ``P3`` (default ``P1``).
        tags: Free-form tags for filtering / categorisation.
        disabled: When ``True`` the case is skipped at execution time.
        environments: If set, the case only runs in the listed
            environments.
        skip_if: Conditional skip rules evaluated at runtime.
        request: The HTTP request to send.
        expect: The expected response / assertions.
        data_driven: Parameterised test data (optional).
        extract: Variables to extract from the response (optional).
        hooks: Before/after hook references (optional).
        depends: IDs of cases that must complete before this one.
        metadata: Authoring and version information.
    """

    id: str
    name: str
    type: Literal["api", "web", "mobile"] = "api"
    priority: Literal["P0", "P1", "P2", "P3"] = "P1"
    tags: list[str] = Field(default_factory=list)
    disabled: bool = False
    environments: list[str] | None = None
    skip_if: list[SkipCondition] | None = None
    request: RequestDef
    expect: ExpectDef
    data_driven: DataDriven | None = None
    extract: dict[str, ExtractVar] | None = None
    hooks: HookConfig | None = None
    depends: list[str] | None = None
    metadata: CaseMetadata | None = None

    # -- helpers ----------------------------------------------------------

    def compute_fingerprint(self) -> str:
        """SHA-256 fingerprint of (method, path, params) for dedup."""
        raw: dict[str, Any] = {
            "method": self.request.method,
            "path": self.request.path,
            "params": (
                dict(sorted(self.request.params.items()))
                if self.request.params
                else {}
            ),
        }
        digest = hashlib.sha256(
            json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return digest
