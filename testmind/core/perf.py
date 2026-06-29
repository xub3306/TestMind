"""Performance testing engine — HTTP response time benchmarking.

Runs controlled rounds of HTTP requests against a target and computes
descriptive statistics: min / max / avg / median (p50) / p90 / p95 /
p99 / standard deviation.  Each run can be compared against a stored
baseline so that performance regressions are detected automatically.

Design:

* **Warm-up** — 2 optional warm-up rounds (excluded from stats) to let
  the server-side caches / JIT settle.
* **Rounds** — configurable number of measurement iterations.
* **Threshold** — a ``max_avg_ms`` threshold causes the run to be
  marked as ``fail`` when the average exceeds it.
* **Baseline** — save a run as the baseline (``perf-baseline.json``)
  and compare subsequent runs against it.  A configurable regression
  percentage triggers a warning.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from testmind.config.settings import ProjectConfig
from testmind.core.runner import _workspace_dir


class PerfResult:
    """Aggregated performance test result."""

    def __init__(
        self,
        url: str,
        method: str = "GET",
        warmups: int = 2,
        rounds: int = 10,
        durations: list[float] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.url = url
        self.method = method
        self.warmups = warmups
        self.rounds = rounds
        self._durations = durations or []
        self._errors = errors or []

    # ------------------------------------------------------------------
    # Statistics (computed lazily)
    # ------------------------------------------------------------------

    @property
    def durations_ms(self) -> list[float]:
        return [d * 1000 for d in self._durations]

    @property
    def min_ms(self) -> float:
        return round(min(self._durations) * 1000, 2) if self._durations else 0

    @property
    def max_ms(self) -> float:
        return round(max(self._durations) * 1000, 2) if self._durations else 0

    @property
    def avg_ms(self) -> float:
        return round(statistics.mean(self._durations) * 1000, 2) if self._durations else 0

    @property
    def median_ms(self) -> float:
        return round(statistics.median(self._durations) * 1000, 2) if self._durations else 0

    @property
    def p90_ms(self) -> float:
        return round(_percentile(self._durations, 90) * 1000, 2) if self._durations else 0

    @property
    def p95_ms(self) -> float:
        return round(_percentile(self._durations, 95) * 1000, 2) if self._durations else 0

    @property
    def p99_ms(self) -> float:
        return round(_percentile(self._durations, 99) * 1000, 2) if self._durations else 0

    @property
    def stddev_ms(self) -> float:
        return round(statistics.stdev(self._durations) * 1000, 2) if len(self._durations) >= 2 else 0.0

    @property
    def error_count(self) -> int:
        return len(self._errors)

    @property
    def success_count(self) -> int:
        return len(self._durations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "method": self.method,
            "warmups": self.warmups,
            "rounds": self.rounds,
            "success": self.success_count,
            "errors": self.error_count,
            "durations_ms": self.durations_ms,
            "stats": {
                "min_ms": self.min_ms,
                "max_ms": self.max_ms,
                "avg_ms": self.avg_ms,
                "median_ms (p50)": self.median_ms,
                "p90_ms": self.p90_ms,
                "p95_ms": self.p95_ms,
                "p99_ms": self.p99_ms,
                "stddev_ms": self.stddev_ms,
            },
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_perf_test(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    warmups: int = 2,
    rounds: int = 20,
    timeout: float = 30,
    max_avg_ms: float | None = None,
) -> dict[str, Any]:
    """Execute a performance benchmark and return a structured result dict.

    Args:
        url: Target URL to test.
        method: HTTP method.
        headers: Optional request headers.
        body: Optional JSON body for POST/PUT.
        warmups: Number of warm-up rounds (excluded from stats).
        rounds: Number of measurement rounds.
        timeout: Per-request timeout in seconds.
        max_avg_ms: If set, the result includes a ``threshold_pass``
            field (``True`` when ``avg_ms <= max_avg_ms``).

    Returns a dict with keys: ``url``, ``method``, ``warmups``,
    ``rounds``, ``success``, ``errors``, ``durations_ms``, ``stats``,
    and optionally ``threshold_pass``.
    """
    client = httpx.Client(timeout=timeout, trust_env=False)
    durations: list[float] = []
    errors: list[str] = []

    # Warm-up (excluded from stats).
    for _ in range(warmups):
        try:
            _do_request(client, method, url, headers, body)
        except Exception:
            pass

    # Measurement rounds.
    for _ in range(rounds):
        try:
            elapsed = _do_request(client, method, url, headers, body)
            durations.append(elapsed)
        except Exception as e:
            errors.append(str(e))

    result = PerfResult(url=url, method=method, warmups=warmups, rounds=rounds,
                        durations=durations, errors=errors)
    out = result.to_dict()
    if max_avg_ms is not None:
        out["threshold_pass"] = result.avg_ms <= max_avg_ms
        out["threshold_max_avg_ms"] = max_avg_ms
    return out


def save_baseline(config: ProjectConfig, perf_result: dict[str, Any]) -> str:
    """Save a performance result as the project baseline.

    Returns the path to ``perf-baseline.json``.
    """
    perfs_dir = _workspace_dir(config) / "perf"
    perfs_dir.mkdir(parents=True, exist_ok=True)
    baseline_file = perfs_dir / "baseline.json"
    data = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "url": perf_result["url"],
        "stats": perf_result.get("stats", {}),
    }
    baseline_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(baseline_file)


def load_baseline(config: ProjectConfig) -> dict[str, Any] | None:
    """Load the stored performance baseline, or None."""
    baseline_file = _workspace_dir(config) / "perf" / "baseline.json"
    if not baseline_file.is_file():
        return None
    try:
        return json.loads(baseline_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def compare_to_baseline(perf_result: dict[str, Any], baseline: dict[str, Any],
                        regression_pct: float = 20.0) -> dict[str, Any]:
    """Compare *perf_result* against *baseline*.

    Returns a dict with ``regression`` (bool), ``regression_pct``, and
    ``details`` (dict mapping metric → old → new → delta_pct).
    """
    old_stats = baseline.get("stats", {})
    new_stats = perf_result.get("stats", {})
    details = {}
    has_regression = False
    for key in ("avg_ms", "median_ms (p50)", "p95_ms", "p99_ms"):
        old_val = old_stats.get(key)
        new_val = new_stats.get(key)
        if old_val is None or new_val is None or old_val <= 0:
            continue
        delta = round((new_val - old_val) / old_val * 100, 1)
        details[key] = {"old": old_val, "new": new_val, "delta_pct": delta}
        if delta > regression_pct:
            has_regression = True
    return {"regression": has_regression, "regression_pct_threshold": regression_pct,
            "details": details, "baseline_url": baseline.get("url", "")}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _do_request(
    client: httpx.Client,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
) -> float:
    """Send one request and return the elapsed wall-clock seconds."""
    start = time.monotonic()
    client.request(method=method, url=url, headers=headers or {},
                   json=body if isinstance(body, dict) else None)
    end = time.monotonic()
    return end - start


def _percentile(data: list[float], pct: float) -> float:
    """Compute the *pct*-th percentile using linear interpolation."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct / 100
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_data):
        return sorted_data[f] + c * (sorted_data[f + 1] - sorted_data[f])
    return sorted_data[f]
