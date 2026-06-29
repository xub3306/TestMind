"""Tests for the result analysis engine (testmind.core.analyze)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from testmind.config.settings import ProjectConfig
from testmind.core.analyze import (
    compute_duration_trend,
    compute_overview,
    compute_pass_rate_trend,
    compute_top_failures,
    load_run_history,
)
from testmind.cli import main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_run(results_dir: Path, run_id: str, total: int, passed: int, failed: int = 0,
              error: int = 0, failures: list | None = None, errors: list | None = None,
              duration: int = 1000) -> dict:
    return {
        "run_id": run_id, "project": "demo", "env": "dev",
        "started_at": "2026-01-01T00:00:00Z", "finished_at": "2026-01-01T00:00:01Z",
        "total": total, "passed": passed, "failed": failed, "error": error, "skipped": 0,
        "total_duration_ms": duration,
        "failures": failures or [],
        "errors": errors or [],
    }


def _write_runs(tmp_path: Path, runs: list[dict]) -> ProjectConfig:
    tm_dir = tmp_path / "testmind"
    tm_dir.mkdir(parents=True, exist_ok=True)
    (tm_dir / "project.json").write_text(
        json.dumps({"name": "analyze", "base_url": "http://localhost", "default_env": "dev"}),
        encoding="utf-8",
    )
    results_dir = tm_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    for r in runs:
        rd = results_dir / r["run_id"]
        rd.mkdir(parents=True, exist_ok=True)
        (rd / "summary.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    config = ProjectConfig(name="analyze", base_url="http://localhost", default_env="dev")
    config.project_dir = tmp_path
    return config


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadRunHistory:
    def test_empty_project(self, tmp_path: Path):
        config = _write_runs(tmp_path, [])
        assert load_run_history(config) == []

    def test_multiple_runs_sorted(self, tmp_path: Path):
        config = _write_runs(tmp_path, [
            _make_run(tmp_path, "20260621_100000_aaaa", 10, 8, 2),
            _make_run(tmp_path, "20260620_090000_bbbb", 5, 5, 0),
            _make_run(tmp_path, "20260622_110000_cccc", 8, 7, 1),
        ])
        history = load_run_history(config)
        assert len(history) == 3
        ids = [r["run_id"] for r in history]
        assert ids[0] == "20260620_090000_bbbb"
        assert ids[-1] == "20260622_110000_cccc"


class TestComputeOverview:
    def test_aggregates_correctly(self):
        runs = [
            _make_run(Path(), "r1", 10, 8, 2, duration=1000),
            _make_run(Path(), "r2", 10, 10, 0, duration=2000),
        ]
        ov = compute_overview(runs)
        assert ov["total_runs"] == 2
        assert ov["total_cases"] == 20
        assert ov["total_passed"] == 18
        assert ov["total_failed"] == 2
        assert ov["avg_pass_rate"] == 90.0
        assert ov["avg_duration_ms"] == 1500

    def test_empty_input(self):
        ov = compute_overview([])
        assert ov["total_runs"] == 0


class TestPassRateTrend:
    def test_chronological_rates(self):
        runs = [
            _make_run(Path(), "r1", 10, 5, 5),
            _make_run(Path(), "r2", 10, 10, 0),
        ]
        trend = compute_pass_rate_trend(runs)
        assert len(trend) == 2
        assert trend[0]["pass_rate"] == 50.0
        assert trend[1]["pass_rate"] == 100.0


class TestTopFailures:
    def test_ranks_by_failure_count(self):
        runs = [
            _make_run(Path(), "r1", 10, 8, 2,
                      failures=[{"case_id": "TC-API-A-001", "reason": "x"},
                                 {"case_id": "TC-API-A-001", "reason": "y"}]),
            _make_run(Path(), "r2", 5, 4, 1,
                      failures=[{"case_id": "TC-API-B-001", "reason": "z"}]),
        ]
        top = compute_top_failures(runs, 10)
        ids = [t["case_id"] for t in top]
        assert ids[0] == "TC-API-A-001"
        assert top[0]["failures"] == 2
        assert ids[1] == "TC-API-B-001"


class TestDurationTrend:
    def test_total_and_average(self):
        runs = [_make_run(Path(), "r1", 5, 5, 0, duration=1000)]
        d = compute_duration_trend(runs)
        assert d[0]["total_duration_ms"] == 1000
        assert d[0]["avg_per_case_ms"] == 200


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCliAnalyze:
    def test_analyze_output(self, tmp_path: Path):
        config = _write_runs(tmp_path, [
            _make_run(tmp_path, "20260621_100000_aaaa", 5, 5, 0, duration=500),
        ])
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", "--project", str(tmp_path)])
        assert result.exit_code == 0
        assert "Avg pass rate" in result.output
        assert "100.0%" in result.output

    def test_analyze_empty_project(self, tmp_path: Path):
        config = _write_runs(tmp_path, [])
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", "--project", str(tmp_path)])
        assert result.exit_code == 0
        assert "No test runs found" in result.output

    def test_analyze_with_top(self, tmp_path: Path):
        config = _write_runs(tmp_path, [
            _make_run(tmp_path, "20260621_100000_aaaa", 3, 1, 2,
                      failures=[{"case_id": "TC-X", "reason": "a"},
                                 {"case_id": "TC-Y", "reason": "b"}]),
        ])
        runner = CliRunner()
        result = runner.invoke(main, ["analyze", "--project", str(tmp_path), "--top", "1"])
        assert result.exit_code == 0
        assert "TC-X" in result.output
