"""Result analysis engine for TestMind test runs.

Scans ``testmind/results/*/summary.json`` to compute:

* **Run history** — chronological list of all runs with pass/fail/error/skip counts.
* **Pass rate trend** — pass percentage over time (chronological chart data).
* **Top failures** — cases that fail most frequently across runs.
* **Duration trends** — average and total duration per run.
* **Overall statistics** — total runs, average pass rate, total cases.

All functions are pure-data (no I/O aside from reading JSON), making
them easy to unit test.  The CLI layer is responsible for formatting and
HTML integration.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from testmind.config.settings import ProjectConfig
from testmind.core.runner import _workspace_dir


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_run_history(config: ProjectConfig) -> list[dict[str, Any]]:
    """Load every ``summary.json`` across all run directories.

    Returns a list of dicts sorted chronologically by ``run_id`` (which
    encodes the timestamp: ``YYYYMMDD_HHMMSS_xxxx``).
    """
    results_dir = _workspace_dir(config) / "results"
    if not results_dir.is_dir():
        return []

    runs: list[dict[str, Any]] = []
    for run_dir in sorted(results_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        summary = run_dir / "summary.json"
        if not summary.is_file():
            continue
        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
            data["_run_dir"] = run_dir.name
            runs.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    # Sort by run_id (which is chronologically ordered by construction,
    # but be explicit to handle any naming edge-case).
    runs.sort(key=lambda r: r.get("run_id", ""))
    return runs


def compute_overview(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate statistics across all runs.

    Returns a dict with keys: ``total_runs``, ``total_cases``,
    ``total_passed``, ``total_failed``, ``total_errors``,
    ``avg_pass_rate`` (float 0-100), ``avg_duration_ms``.
    """
    runs = len(history)
    if runs == 0:
        return {
            "total_runs": 0, "total_cases": 0, "total_passed": 0,
            "total_failed": 0, "total_errors": 0,
            "avg_pass_rate": 0.0, "avg_duration_ms": 0,
        }
    total = sum(r.get("total", 0) for r in history)
    passed = sum(r.get("passed", 0) for r in history)
    failed = sum(r.get("failed", 0) for r in history)
    errors = sum(r.get("error", 0) for r in history)
    pass_rates = [_pass_rate(r) for r in history]
    avg_rate = round(sum(pass_rates) / len(pass_rates), 1) if pass_rates else 0.0
    durations = [r.get("total_duration_ms", 0) for r in history]
    avg_dur = round(sum(durations) / len(durations)) if durations else 0
    return {
        "total_runs": runs, "total_cases": total,
        "total_passed": passed, "total_failed": failed, "total_errors": errors,
        "avg_pass_rate": avg_rate, "avg_duration_ms": avg_dur,
    }


def compute_pass_rate_trend(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chronological pass rate per run (for charting / table display).

    Each entry: ``{"run_id": ..., "pass_rate": ..., "total": ...}``
    """
    trend: list[dict[str, Any]] = []
    for r in history:
        trend.append({
            "run_id": r.get("run_id", ""),
            "pass_rate": _pass_rate(r),
            "total": r.get("total", 0),
            "passed": r.get("passed", 0),
            "failed": r.get("failed", 0),
            "error": r.get("error", 0),
        })
    return trend


def compute_top_failures(history: list[dict[str, Any]], top_n: int = 10) -> list[dict[str, Any]]:
    """Return the *top_n* cases that fail most frequently across all runs.

    Each entry: ``{"case_id": ..., "failures": ..., "appearances": ...}``
    """
    from collections import Counter
    fail_counts: Counter = Counter()
    appear_counts: Counter = Counter()
    for r in history:
        for f in r.get("failures", []) or []:
            cid = f.get("case_id", "unknown")
            fail_counts[cid] += 1
        for e in r.get("errors", []) or []:
            cid = e.get("case_id", "unknown")
            fail_counts[cid] += 1
        # Count appearances from total.
        # (We can't know per-case from summary alone without loading case files.)
    # Sort by failure count descending.
    result = []
    for cid, count in fail_counts.most_common(top_n):
        result.append({"case_id": cid, "failures": count})
    return result


def compute_duration_trend(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Duration per run (total_duration_ms and average per case)."""
    trend: list[dict[str, Any]] = []
    for r in history:
        total_dur = r.get("total_duration_ms", 0)
        case_count = r.get("total", 0)
        avg = round(total_dur / case_count) if case_count > 0 else 0
        trend.append({
            "run_id": r.get("run_id", ""),
            "total_duration_ms": total_dur,
            "avg_per_case_ms": avg,
            "total_cases": case_count,
        })
    return trend


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pass_rate(run: dict[str, Any]) -> float:
    total = run.get("total", 0)
    if total <= 0:
        return 0.0
    return round(run.get("passed", 0) / total * 100, 1)
