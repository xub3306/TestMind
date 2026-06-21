"""Tests for the HTML report generator (testmind.core.report)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from testmind.core.report import generate_html_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_run(results_dir: Path, summary: dict, cases: list[dict]) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    for c in cases:
        (results_dir / f"{c['case_id']}.json").write_text(json.dumps(c), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGenerateHtmlReport:
    """Cover report generation from summary + case files."""

    def test_generates_html_file(self, tmp_path: Path):
        rdir = tmp_path / "testmind" / "results" / "run1"
        _write_run(
            rdir,
            summary={
                "run_id": "run1", "project": "demo", "env": "dev",
                "started_at": "2026-06-21T10:00:00Z", "finished_at": "2026-06-21T10:00:05Z",
                "total": 2, "passed": 1, "failed": 1, "error": 0, "skipped": 0,
                "total_duration_ms": 500,
                "failures": [{"case_id": "TC-API-X-001", "reason": "status mismatch"}],
                "errors": [],
            },
            cases=[
                {"case_id": "TC-API-A-001", "run_id": "run1", "env": "dev", "status": "pass",
                 "duration_ms": 200, "assertions_result": [{"type": "status_code", "passed": True}],
                 "request_snapshot": {"method": "GET", "url": "http://x/api", "headers": {}},
                 "response_snapshot": {"status_code": 200, "headers": {}, "duration_ms": 200}},
                {"case_id": "TC-API-X-001", "run_id": "run1", "env": "dev", "status": "fail",
                 "duration_ms": 300, "error": "status mismatch",
                 "assertions_result": [{"type": "status_code", "passed": False, "expected": 200, "actual": 500}],
                 "request_snapshot": {"method": "POST", "url": "http://x/api", "headers": {}},
                 "response_snapshot": {"status_code": 500, "headers": {}, "duration_ms": 300}},
            ],
        )
        path = generate_html_report(rdir)
        assert Path(path).is_file()
        content = Path(path).read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")
        # Key data is rendered.
        assert "run1" in content
        assert "demo" in content
        assert "TC-API-A-001" in content
        assert "TC-API-X-001" in content
        assert "Pass Rate: 50.0%" in content
        # Status badges present.
        assert "PASS" in content
        assert "FAIL" in content

    def test_missing_summary_raises(self, tmp_path: Path):
        rdir = tmp_path / "results" / "runx"
        rdir.mkdir(parents=True, exist_ok=True)
        with pytest.raises(FileNotFoundError, match="summary.json"):
            generate_html_report(rdir)

    def test_empty_run(self, tmp_path: Path):
        """A run with zero cases still produces a valid report."""
        rdir = tmp_path / "results" / "empty"
        _write_run(
            rdir,
            summary={
                "run_id": "empty", "project": "p", "env": "dev",
                "started_at": "", "finished_at": "",
                "total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0,
                "total_duration_ms": 0, "failures": [], "errors": [],
            },
            cases=[],
        )
        path = generate_html_report(rdir)
        content = Path(path).read_text(encoding="utf-8")
        assert "Pass Rate: 0.0%" in content
        assert "No case result files found" in content

    def test_all_pass_rate_100(self, tmp_path: Path):
        rdir = tmp_path / "results" / "ok"
        _write_run(
            rdir,
            summary={
                "run_id": "ok", "project": "p", "env": "dev",
                "started_at": "", "finished_at": "",
                "total": 3, "passed": 3, "failed": 0, "error": 0, "skipped": 0,
                "total_duration_ms": 100, "failures": [], "errors": [],
            },
            cases=[
                {"case_id": f"TC-API-A-{i:03d}", "run_id": "ok", "env": "dev", "status": "pass", "duration_ms": 30}
                for i in range(1, 4)
            ],
        )
        content = Path(generate_html_report(rdir), encoding="utf-8") if False else Path(generate_html_report(rdir)).read_text(encoding="utf-8")
        assert "Pass Rate: 100.0%" in content
        # No failures section when everything passed.
        assert "Failures & Errors" not in content

    def test_error_cases_section(self, tmp_path: Path):
        rdir = tmp_path / "results" / "err"
        _write_run(
            rdir,
            summary={
                "run_id": "err", "project": "p", "env": "dev",
                "started_at": "", "finished_at": "",
                "total": 1, "passed": 0, "failed": 0, "error": 1, "skipped": 0,
                "total_duration_ms": 0, "failures": [],
                "errors": [{"case_id": "TC-API-E-001", "reason": "connection refused"}],
            },
            cases=[
                {"case_id": "TC-API-E-001", "run_id": "err", "env": "dev", "status": "error",
                 "duration_ms": 0, "error": "connection refused"},
            ],
        )
        content = Path(generate_html_report(rdir)).read_text(encoding="utf-8")
        assert "Failures & Errors" in content
        assert "connection refused" in content
        assert "ERROR" in content

    def test_retry_files_skipped(self, tmp_path: Path):
        """Files matching *_retry_*.json are detail artifacts, not cases."""
        rdir = tmp_path / "results" / "rt"
        _write_run(
            rdir,
            summary={
                "run_id": "rt", "project": "p", "env": "dev",
                "started_at": "", "finished_at": "",
                "total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0,
                "total_duration_ms": 10, "failures": [], "errors": [],
            },
            cases=[
                {"case_id": "TC-API-A-001", "run_id": "rt", "env": "dev", "status": "pass", "duration_ms": 10},
            ],
        )
        # Write a stray retry file that should NOT appear as a top-level case row.
        (rdir / "TC-API-A-001_retry_1.json").write_text(
            json.dumps({"case_id": "TC-API-A-001", "status": "fail"}), encoding="utf-8"
        )
        content = Path(generate_html_report(rdir)).read_text(encoding="utf-8")
        # The case appears exactly once in the cases table body.
        assert content.count("<tr class='pass'>") == 1

    def test_html_escaping(self, tmp_path: Path):
        """Case IDs / reasons with HTML special chars are escaped."""
        rdir = tmp_path / "results" / "esc"
        _write_run(
            rdir,
            summary={
                "run_id": "esc", "project": "p<>&", "env": "dev",
                "started_at": "", "finished_at": "",
                "total": 1, "passed": 0, "failed": 1, "error": 0, "skipped": 0,
                "total_duration_ms": 0,
                "failures": [{"case_id": "TC-API-X-001", "reason": "<script>bad</script>"}],
                "errors": [],
            },
            cases=[
                {"case_id": "TC-API-X-001", "run_id": "esc", "env": "dev", "status": "fail",
                 "duration_ms": 0, "error": "<script>bad</script>"},
            ],
        )
        content = Path(generate_html_report(rdir)).read_text(encoding="utf-8")
        # Raw script tag must NOT appear (it must be escaped).
        assert "<script>bad</script>" not in content
        assert "&lt;script&gt;bad&lt;/script&gt;" in content
