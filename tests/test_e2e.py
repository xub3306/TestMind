"""End-to-end integration tests for the TestMind MVP pipeline.

Exercises the full workflow against a real (in-process) HTTP server so
that every layer is exercised together:

    init project → write spec → parse_spec → validate_case →
    save_case → list_cases → run_cases → get_results

A lightweight ``http.server``-based mock is spun up in a background
thread so that the runner's ``httpx`` requests hit a deterministic
endpoint instead of the network.  This keeps the tests fast, offline,
and reproducible (honouring the "deterministic results" principle).
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testmind.config.settings import ProjectConfig
from testmind.core.runner import (
    Runner,
    get_results,
    list_all_cases,
    save_case_to_project,
    validate_single_case,
)
from testmind.core.spec_parser import SpecParser


# ---------------------------------------------------------------------------
# In-process mock API server
# ---------------------------------------------------------------------------


class _MockAPIHandler(BaseHTTPRequestHandler):
    """Deterministic mock handler used by the end-to-end tests.

    Routes are declared on the class as ``ROUTES`` so the fixture can
    configure responses without subclassing.  All responses are JSON.
    """

    ROUTES: dict[tuple[str, str], dict] = {}

    def log_message(self, format, *args):  # silence stderr noise
        pass

    def _handle(self, method: str) -> None:
        key = (method, self.path)
        route = self.ROUTES.get(key)
        if route is None:
            # Fall back to a generic 404 JSON response.
            payload = {"error": "not found", "path": self.path}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(404)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        status = route.get("status", 200)
        body_obj = route.get("body", {})
        body = json.dumps(body_obj).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - http.server convention
        self._handle("GET")

    def do_POST(self):  # noqa: N802 - http.server convention
        # Drain the request body so the connection stays clean.
        length = int(self.headers.get("content-length", 0) or 0)
        if length:
            self.rfile.read(length)
        self._handle("POST")


def _free_port() -> int:
    """Allocate an ephemeral free port for the mock server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def mock_api_server():
    """Start a deterministic mock API server on a random port.

    Yields a dict with ``base_url`` and a mutable ``routes`` mapping so
    individual tests can customise responses.  The server is shut down
    on teardown.
    """
    port = _free_port()
    routes: dict[tuple[str, str], dict] = {
        ("GET", "/api/users"): {
            "status": 200,
            "body": {"data": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}], "total": 2},
        },
        ("POST", "/api/users"): {
            "status": 201,
            "body": {"id": 3, "name": "Charlie", "created": True},
        },
        ("GET", "/api/users/1"): {
            "status": 200,
            "body": {"id": 1, "name": "Alice", "email": "alice@example.com"},
        },
    }
    _MockAPIHandler.ROUTES = routes

    server = ThreadingHTTPServer(("127.0.0.1", port), _MockAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield {"base_url": f"http://127.0.0.1:{port}", "routes": routes}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Project fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def project(tmp_path: Path, mock_api_server) -> ProjectConfig:
    """Create a real TestMind project on disk pointing at the mock server.

    Returns a :class:`ProjectConfig` whose ``project_dir`` is set so the
    runner resolves the workspace correctly regardless of the current
    working directory.
    """
    base_url = mock_api_server["base_url"]
    tm_dir = tmp_path / "testmind"
    (tm_dir / "envs").mkdir(parents=True, exist_ok=True)
    (tm_dir / "specs").mkdir(parents=True, exist_ok=True)
    (tm_dir / "cases").mkdir(parents=True, exist_ok=True)
    (tm_dir / "results").mkdir(parents=True, exist_ok=True)

    (tm_dir / "project.json").write_text(
        json.dumps(
            {
                "name": "e2e_demo",
                "type": "api",
                "base_url": base_url,
                "default_env": "dev",
            }
        ),
        encoding="utf-8",
    )
    (tm_dir / "envs" / "dev.json").write_text(
        json.dumps({"name": "dev", "base_url": base_url}),
        encoding="utf-8",
    )

    config = ProjectConfig(name="e2e_demo", base_url=base_url, default_env="dev")
    config.project_dir = tmp_path
    return config


# ---------------------------------------------------------------------------
# End-to-end pipeline tests
# ---------------------------------------------------------------------------


def _write_openapi_spec(specs_dir: Path) -> Path:
    """Write a minimal OpenAPI 3.0 document and return its path."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Demo API", "version": "1.0.0"},
        "paths": {
            "/api/users": {
                "get": {
                    "summary": "List users",
                    "parameters": [
                        {"name": "page", "in": "query", "required": False, "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "A list of users"}},
                },
                "post": {
                    "summary": "Create user",
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "object"}}},
                        "required": True,
                    },
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/api/users/1": {
                "get": {
                    "summary": "Get a single user",
                    "responses": {"200": {"description": "A user"}},
                },
            },
        },
    }
    spec_file = specs_dir / "openapi.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    return spec_file


class TestEndToEndPipeline:
    """Full pipeline: parse → validate → save → list → run → results."""

    def test_parse_spec_generates_standardised_json(self, project: ProjectConfig):
        specs_dir = project.project_dir / "testmind" / "specs"
        spec_file = _write_openapi_spec(specs_dir)

        parser = SpecParser(config=project)
        result = parser.parse(str(spec_file))

        assert result.endpoints_count == 3
        assert result.format == "openapi_3.0"
        api_spec = specs_dir / "api-spec.json"
        assert api_spec.is_file()
        data = json.loads(api_spec.read_text(encoding="utf-8"))
        assert data["format"] == "testmind-spec-1.0"
        paths = {ep["path"] for ep in data["endpoints"]}
        assert "/api/users" in paths
        assert "/api/users/1" in paths

    def test_validate_case_accepts_well_formed_case(self):
        case = {
            "id": "TC-API-USERS-001",
            "name": "List users",
            "type": "api",
            "priority": "P1",
            "tags": ["smoke"],
            "request": {"method": "GET", "path": "/api/users"},
            "expect": {"status": 200},
        }
        result = validate_single_case(case)
        assert result.valid, f"Unexpected errors: {result.errors}"
        assert result.case_id == "TC-API-USERS-001"

    def test_validate_case_rejects_missing_request(self):
        result = validate_single_case({"id": "TC-API-X-001", "name": "bad"})
        assert not result.valid
        assert result.errors

    def test_save_and_list_case(self, project: ProjectConfig):
        case = {
            "id": "TC-API-USERS-001",
            "name": "List users",
            "type": "api",
            "priority": "P1",
            "tags": ["smoke"],
            "request": {"method": "GET", "path": "/api/users"},
            "expect": {"status": 200},
        }
        save_result = asyncio.run(save_case_to_project(project, case))
        assert save_result["status"] == "saved"
        assert Path(save_result["path"]).is_file()

        listed = list_all_cases(project)
        ids = [c.id for c in listed]
        assert "TC-API-USERS-001" in ids

    def test_save_duplicate_fingerprint_rejected(self, project: ProjectConfig):
        case = {
            "id": "TC-API-USERS-001",
            "name": "List users",
            "type": "api",
            "priority": "P1",
            "request": {"method": "GET", "path": "/api/users"},
            "expect": {"status": 200},
        }
        asyncio.run(save_case_to_project(project, case))
        # Same fingerprint, different ID → duplicate.
        dup = dict(case)
        dup["id"] = "TC-API-USERS-099"
        result = asyncio.run(save_case_to_project(project, dup))
        assert result["status"] == "duplicate"

    def test_full_run_pipeline(self, project: ProjectConfig, mock_api_server):
        """The headline end-to-end test: save cases, run, inspect results."""
        # Two independent cases against the mock routes.
        cases = [
            {
                "id": "TC-API-USERS-001",
                "name": "List users",
                "type": "api",
                "priority": "P1",
                "tags": ["smoke"],
                "request": {"method": "GET", "path": "/api/users"},
                "expect": {
                    "status": 200,
                    "assertions": [
                        {"type": "jsonpath", "path": "$.data[0].id", "operator": "eq", "expected": 1},
                    ],
                },
            },
            {
                "id": "TC-API-USERS-002",
                "name": "Create user",
                "type": "api",
                "priority": "P1",
                "tags": ["smoke"],
                "request": {
                    "method": "POST",
                    "path": "/api/users",
                    "params": {"body": {"name": "Charlie"}},
                },
                "expect": {"status": 201},
            },
            {
                "id": "TC-API-USERS-003",
                "name": "Get user detail",
                "type": "api",
                "priority": "P2",
                "request": {"method": "GET", "path": "/api/users/1"},
                "expect": {"status": 200},
            },
        ]
        for c in cases:
            res = asyncio.run(save_case_to_project(project, c))
            assert res["status"] == "saved", f"Failed to save {c['id']}: {res}"

        runner = Runner(project)
        run_id = runner.run(env="dev")

        assert run_id  # non-empty run id
        results = get_results(project, run_id=run_id)
        assert len(results) == 3
        statuses = {r.case_id: r.status for r in results}
        assert statuses["TC-API-USERS-001"] == "pass"
        assert statuses["TC-API-USERS-002"] == "pass"
        assert statuses["TC-API-USERS-003"] == "pass"

        # Exit code reflects all-pass.
        assert runner.get_exit_code(results) == 0

        # Summary file written.
        summary_file = project.project_dir / "testmind" / "results" / run_id / "summary.json"
        assert summary_file.is_file()
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        assert summary["total"] == 3
        assert summary["passed"] == 3

    def test_failing_case_recorded(self, project: ProjectConfig, mock_api_server):
        """A case whose assertion fails is marked ``fail`` (not ``error``)."""
        case = {
            "id": "TC-API-USERS-010",
            "name": "Expect wrong status",
            "type": "api",
            "priority": "P1",
            "request": {"method": "GET", "path": "/api/users"},
            "expect": {"status": 500},  # mock returns 200
        }
        asyncio.run(save_case_to_project(project, case))

        runner = Runner(project)
        run_id = runner.run(env="dev")
        results = get_results(project, run_id=run_id)
        assert len(results) == 1
        assert results[0].status == "fail"
        assert runner.get_exit_code(results) == 1  # EXIT_HAS_FAIL

    def test_list_filters_by_tag(self, project: ProjectConfig):
        for i, tag in enumerate(["smoke", "regression"], start=1):
            asyncio.run(
                save_case_to_project(
                    project,
                    {
                        "id": f"TC-API-USERS-{i:03d}",
                        "name": f"case {i}",
                        "type": "api",
                        "priority": "P1",
                        "tags": [tag],
                        "request": {"method": "GET", "path": f"/api/users/{i}"},
                        "expect": {"status": 200},
                    },
                )
            )
        smoke = list_all_cases(project, tags=["smoke"])
        assert len(smoke) == 1
        assert smoke[0].tags == ["smoke"]
