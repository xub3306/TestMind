"""TestMind test suite data model.

A suite groups test cases by ID or directory for organised execution.
A suite can also carry its own execution strategy (workers, retry,
fail_fast) that overrides the project/CLI defaults when the suite is
selected.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TestSuite(BaseModel):
    """A named collection of test cases for organised execution.

    Attributes:
        id: Unique suite identifier (e.g. ``SUITE-LOGIN-001``).
        name: Human-readable suite name.
        description: Optional longer description.
        tags: Free-form tags for filtering.
        cases: Explicit list of case IDs to include.
        case_dirs: Directories to scan for cases (relative to
            ``cases/``).
        setup: Hook scripts to run before the entire suite.
        teardown: Hook scripts to run after the entire suite (always
            executed).
        workers: Number of parallel workers to use for this suite.
            When ``None`` (default), the value passed to ``run`` /
            ``--workers`` is used.
        retry: Number of retries for failed cases within this suite.
            When ``None``, the value passed to ``run`` / ``--retry`` is
            used.
        fail_fast: Stop after this many consecutive failures (0 =
            disabled).  When ``None``, the value passed to ``run`` /
            ``--fail-fast`` is used.
    """

    id: str = ""
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    cases: list[str] = Field(default_factory=list)
    case_dirs: list[str] = Field(default_factory=list)
    setup: list[str] | None = None
    teardown: list[str] | None = None
    workers: int | None = None
    retry: int | None = None
    fail_fast: int | None = None
