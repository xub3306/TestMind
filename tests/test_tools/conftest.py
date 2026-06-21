"""Shared fixtures for the MCP tool unit tests.

Provides:

* ``mock_api_server`` -- a deterministic in-process HTTP server (mirrors
  the pattern used by ``tests/test_e2e.py``) so that ``run_cases`` can
  issue real ``httpx`` requests without touching the network.
* ``project`` -- a real TestMind project on disk pointing at the mock
  server, with ``config.project_dir`` set so the runner resolves the
  workspace correctly regardless of the current working directory.
* an autouse ``_chdir_tmp_path`` fixture that pins the current working
  directory to ``tmp_path`` for every test in this package.  This is
  essential because the tool handlers instantiate a fresh audit logger
  (``get_audit_logger()``) which writes ``logs/audit.jsonl`` relative
  to the cwd; without the chdir the un-ignored ``audit.jsonl`` would
  leak into the repository root.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testmind.config.settings import ProjectConfig


# ---------------------------------------------------------------------------
# In-process mock API server (deterministic, offline)
# ---------------------------------------------------------------------------


class _MockAPIHandler(BaseHTTPRequestHandler):
    """Deterministic mock handler; routes are declared on the class."""

    ROUTES: dict[tuple[str, str], dict] = {}

    def log_message(self, format, *args):  # silence stderr noise
        pass

    def _handle(self, method: str) -> None:
        key = (method, self.path)
        route = self.ROUTES.get(key)
        if route is None:
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
        length = int(self.headers.get("content-length", 0) or 0)
        if length:
            self.rfile.read(length)
        self._handle("POST")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def mock_api_server():
    """Start a deterministic mock API server on a random port."""
    port = _free_port()
    routes: dict[tuple[str, str], dict] = {
        ("GET", "/api/users"): {
            "status": 200,
            "body": {"data": [{"id": 1, "name": "Alice"}], "total": 1},
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
    """Create a real TestMind project on disk pointing at the mock server."""
    base_url = mock_api_server["base_url"]
    tm_dir = tmp_path / "testmind"
    (tm_dir / "envs").mkdir(parents=True, exist_ok=True)
    (tm_dir / "specs").mkdir(parents=True, exist_ok=True)
    (tm_dir / "cases").mkdir(parents=True, exist_ok=True)
    (tm_dir / "results").mkdir(parents=True, exist_ok=True)

    (tm_dir / "project.json").write_text(
        json.dumps(
            {
                "name": "tool_demo",
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

    config = ProjectConfig(name="tool_demo", base_url=base_url, default_env="dev")
    config.project_dir = tmp_path
    return config


# ---------------------------------------------------------------------------
# Autouse cwd isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _chdir_tmp_path(tmp_path: Path, monkeypatch):
    """Pin cwd to tmp_path so audit.jsonl lands in the temp dir, not the repo."""
    monkeypatch.chdir(tmp_path)
    yield
