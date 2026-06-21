"""Integration tests for the Runner's concurrent execution mode (workers>1).

Validates that:

* Independent cases in the same topology layer run concurrently and all
  results are collected.
* Cases with dependencies execute in the correct layer order (a
  dependency always completes before its dependent case starts).
* Concurrent execution produces the same outcome set as serial
  execution (determinism).
* The ``_split_into_layers`` helper groups cases by dependency depth.

Uses the same in-process mock HTTP server pattern as ``test_e2e.py``.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testmind.config.settings import ProjectConfig
from testmind.core.runner import Runner, get_results, save_case_to_project


# ---------------------------------------------------------------------------
# Mock server that records call timestamps (for concurrency verification)
# ---------------------------------------------------------------------------


class _ConcurrencyHandler(BaseHTTPRequestHandler):
    """Records per-case request timestamps so tests can assert overlap."""

    # Class-level shared state (reset per fixture invocation).
    CALL_LOG: list[dict] = []

    def log_message(self, format, *args):
        pass

    def do_GET(self):  # noqa: N802
        # Path is /api/<case_id>; record start/end so the test can verify
        # that independent cases overlapped.
        t0 = time.monotonic()
        body = json.dumps({"ok": True, "path": self.path}).encode("utf-8")
        # Simulate a small latency so concurrency is observable.
        time.sleep(0.2)
        t1 = time.monotonic()
        _ConcurrencyHandler.CALL_LOG.append({
            "path": self.path,
            "start": t0,
            "end": t1,
        })
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def concurrency_server():
    _ConcurrencyHandler.CALL_LOG = []
    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _ConcurrencyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"base_url": f"http://127.0.0.1:{port}", "call_log": _ConcurrencyHandler.CALL_LOG}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def project(tmp_path: Path, concurrency_server) -> ProjectConfig:
    base_url = concurrency_server["base_url"]
    tm_dir = tmp_path / "testmind"
    (tm_dir / "envs").mkdir(parents=True, exist_ok=True)
    (tm_dir / "cases").mkdir(parents=True, exist_ok=True)
    (tm_dir / "results").mkdir(parents=True, exist_ok=True)
    (tm_dir / "project.json").write_text(
        json.dumps({"name": "conc", "base_url": base_url, "default_env": "dev"}),
        encoding="utf-8",
    )
    (tm_dir / "envs" / "dev.json").write_text(
        json.dumps({"name": "dev", "base_url": base_url}), encoding="utf-8"
    )
    config = ProjectConfig(name="conc", base_url=base_url, default_env="dev")
    config.project_dir = tmp_path
    return config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _save(case_id: str, depends: list[str] | None, project: ProjectConfig) -> None:
    case = {
        "id": case_id, "name": case_id, "type": "api", "priority": "P1",
        "request": {"method": "GET", "path": f"/api/{case_id}"},
        "expect": {"status": 200},
    }
    if depends:
        case["depends"] = depends
    res = asyncio.run(save_case_to_project(project, case))
    assert res.get("status") == "saved", f"save failed for {case_id}: {res}"


def _had_overlap(call_log: list[dict]) -> bool:
    """Return True if any two recorded calls overlapped in time."""
    if len(call_log) < 2:
        return False
    intervals = sorted(call_log, key=lambda e: e["start"])
    for i in range(len(intervals) - 1):
        if intervals[i]["end"] > intervals[i + 1]["start"]:
            return True
    return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSplitIntoLayers:
    """Unit-test the layer-splitting helper directly."""

    def _runner(self, tmp_path: Path) -> Runner:
        config = ProjectConfig(name="t", base_url="http://localhost")
        config.project_dir = tmp_path
        return Runner(config)

    def test_no_dependencies_single_layer(self, tmp_path: Path):
        from testmind.models.testcase import TestCase
        runner = self._runner(tmp_path)
        cases = [
            TestCase(id="A", name="A", request={"method": "GET", "path": "/a"}, expect={"status": 200}),
            TestCase(id="B", name="B", request={"method": "GET", "path": "/b"}, expect={"status": 200}),
            TestCase(id="C", name="C", request={"method": "GET", "path": "/c"}, expect={"status": 200}),
        ]
        layers = runner._split_into_layers(cases)
        assert len(layers) == 1
        assert {c.id for c in layers[0]} == {"A", "B", "C"}

    def test_chain_three_layers(self, tmp_path: Path):
        from testmind.models.testcase import TestCase
        runner = self._runner(tmp_path)
        cases = [
            TestCase(id="C", name="C", depends=["B"], request={"method": "GET", "path": "/c"}, expect={"status": 200}),
            TestCase(id="A", name="A", request={"method": "GET", "path": "/a"}, expect={"status": 200}),
            TestCase(id="B", name="B", depends=["A"], request={"method": "GET", "path": "/b"}, expect={"status": 200}),
        ]
        layers = runner._split_into_layers(cases)
        assert len(layers) == 3
        assert {c.id for c in layers[0]} == {"A"}
        assert {c.id for c in layers[1]} == {"B"}
        assert {c.id for c in layers[2]} == {"C"}

    def test_diamond_dependency(self, tmp_path: Path):
        """Diamond: A -> {B, C} -> D. B and C share layer 1."""
        from testmind.models.testcase import TestCase
        runner = self._runner(tmp_path)
        cases = [
            TestCase(id="D", name="D", depends=["B", "C"], request={"method": "GET", "path": "/d"}, expect={"status": 200}),
            TestCase(id="B", name="B", depends=["A"], request={"method": "GET", "path": "/b"}, expect={"status": 200}),
            TestCase(id="C", name="C", depends=["A"], request={"method": "GET", "path": "/c"}, expect={"status": 200}),
            TestCase(id="A", name="A", request={"method": "GET", "path": "/a"}, expect={"status": 200}),
        ]
        layers = runner._split_into_layers(cases)
        assert len(layers) == 3
        assert {c.id for c in layers[0]} == {"A"}
        assert {c.id for c in layers[1]} == {"B", "C"}
        assert {c.id for c in layers[2]} == {"D"}


class TestConcurrentExecution:
    """End-to-end concurrent execution against a mock server."""

    def test_independent_cases_overlap(self, project: ProjectConfig, concurrency_server):
        """Three independent cases on the same layer should overlap in time
        when run with workers>=3, but NOT when run serially (workers=1)."""
        for cid in ["TC-API-A-001", "TC-API-B-001", "TC-API-C-001"]:
            _save(cid, None, project)

        # --- Serial run ---
        concurrency_server["call_log"].clear()
        runner = Runner(project)
        runner.run(env="dev", workers=1)
        serial_log = list(concurrency_server["call_log"])
        assert not _had_overlap(serial_log), "serial run should NOT overlap"

        # --- Concurrent run ---
        concurrency_server["call_log"].clear()
        runner2 = Runner(project)
        run_id = runner2.run(env="dev", workers=3)
        concurrent_log = list(concurrency_server["call_log"])
        assert _had_overlap(concurrent_log), "concurrent run should overlap"

        # Results are equivalent: all pass, three cases.
        results = get_results(project, run_id=run_id)
        assert len(results) == 3
        assert all(r.status == "pass" for r in results)

    def test_dependency_order_preserved(self, project: ProjectConfig, concurrency_server):
        """A -> B chain: B must start after A finishes, even with workers>1."""
        _save("TC-API-A-001", None, project)
        _save("TC-API-B-001", ["TC-API-A-001"], project)

        runner = Runner(project)
        run_id = runner.run(env="dev", workers=4)
        results = get_results(project, run_id=run_id)
        assert len(results) == 2
        assert all(r.status == "pass" for r in results)

        # Verify A finished before B started by inspecting the call log.
        log = {e["path"]: e for e in concurrency_server["call_log"]}
        a_path = "/api/TC-API-A-001"
        b_path = "/api/TC-API-B-001"
        # The mock server recorded requests; ensure A's end <= B's start.
        assert log[a_path]["end"] <= log[b_path]["start"], "dependency B ran before A completed"

    def test_concurrent_results_match_serial(self, project: ProjectConfig, concurrency_server):
        """Concurrent execution yields the same set of case outcomes as serial."""
        # Mix of independent and dependent cases.
        _save("TC-API-A-001", None, project)
        _save("TC-API-B-001", None, project)
        _save("TC-API-C-001", ["TC-API-A-001"], project)

        runner_s = Runner(project)
        run_s = runner_s.run(env="dev", workers=1)
        serial_statuses = {r.case_id: r.status for r in get_results(project, run_id=run_s)}

        runner_c = Runner(project)
        run_c = runner_c.run(env="dev", workers=3)
        concurrent_statuses = {r.case_id: r.status for r in get_results(project, run_id=run_c)}

        assert serial_statuses == concurrent_statuses

    def test_summary_counts_correct_concurrent(self, project: ProjectConfig, concurrency_server):
        """Summary totals are correct after a concurrent run."""
        for cid in ["TC-API-A-001", "TC-API-B-001", "TC-API-C-001", "TC-API-D-001"]:
            _save(cid, None, project)

        runner = Runner(project)
        run_id = runner.run(env="dev", workers=2)
        summary_file = project.project_dir / "testmind" / "results" / run_id / "summary.json"
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        assert summary["total"] == 4
        assert summary["passed"] == 4
        assert summary["failed"] == 0
        assert summary["error"] == 0
