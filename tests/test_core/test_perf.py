"""Tests for the performance testing engine (testmind.core.perf)."""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from click.testing import CliRunner

from testmind.config.settings import ProjectConfig
from testmind.core.perf import (
    compare_to_baseline,
    load_baseline,
    save_baseline,
    run_perf_test,
)
from testmind.cli import main


# ---------------------------------------------------------------------------
# Mock server
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def mock_server():
    port_socket = socket.socket()
    port_socket.bind(("127.0.0.1", 0))
    port = port_socket.getsockname()[1]
    port_socket.close()
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/api/test"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunPerfTest:
    def test_basic_benchmark(self, mock_server):
        result = run_perf_test(mock_server, rounds=5, warmups=0)
        assert result["success"] == 5
        assert result["errors"] == 0
        s = result["stats"]
        assert s["min_ms"] >= 0
        assert s["max_ms"] >= 0
        assert s["avg_ms"] >= 0
        assert isinstance(s["median_ms (p50)"], (int, float))
        assert isinstance(s["p90_ms"], (int, float))

    def test_threshold_pass(self, mock_server):
        result = run_perf_test(mock_server, rounds=3, warmups=0, max_avg_ms=99999)
        assert result["threshold_pass"] is True

    def test_threshold_fail(self, mock_server):
        result = run_perf_test(mock_server, rounds=3, warmups=0, max_avg_ms=0.001)
        assert result["threshold_pass"] is False

    def test_errors_with_invalid_url(self):
        result = run_perf_test("http://127.0.0.1:1/no", rounds=2, warmups=0, timeout=1)
        assert result["errors"] > 0

    def test_many_rounds(self, mock_server):
        result = run_perf_test(mock_server, rounds=50, warmups=0)
        assert result["success"] == 50
        assert len(result["durations_ms"]) == 50


class TestPercentiles:
    def test_p90_p95_p99_ordering(self, mock_server):
        result = run_perf_test(mock_server, rounds=30, warmups=0)
        s = result["stats"]
        assert s["p90_ms"] >= s["min_ms"]
        assert s["p99_ms"] >= s["p90_ms"]


class TestBaseline:
    def test_save_and_load(self, tmp_path: Path):
        (tmp_path / "testmind").mkdir()
        config = ProjectConfig(name="p", base_url="http://localhost")
        config.project_dir = tmp_path
        result = {"url": "/x", "stats": {"avg_ms": 42.0}}
        path = save_baseline(config, result)
        assert Path(path).is_file()

        loaded = load_baseline(config)
        assert loaded is not None
        assert loaded["url"] == "/x"
        assert loaded["stats"]["avg_ms"] == 42.0

    def test_compare_regression(self):
        baseline = {"url": "/x", "stats": {"avg_ms": 100, "p95_ms": 200}}
        result = {"url": "/x", "stats": {"avg_ms": 150, "p95_ms": 250}}
        comp = compare_to_baseline(result, baseline, regression_pct=20)
        assert comp["regression"] is True  # 50% regression on avg
        assert comp["details"]["avg_ms"]["delta_pct"] == 50.0

    def test_compare_no_regression(self):
        baseline = {"url": "/x", "stats": {"avg_ms": 100}}
        result = {"url": "/x", "stats": {"avg_ms": 105}}
        comp = compare_to_baseline(result, baseline, regression_pct=20)
        assert comp["regression"] is False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCliPerf:
    def test_perf_run_command(self, mock_server, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "perf", "run", mock_server, "--rounds", "3", "--warmups", "0",
        ])
        assert result.exit_code == 0
        assert "Success:" in result.output
        assert "Avg:" in result.output
