"""Unit tests for the discover_spec MCP tool.

Exercises ``testmind.tools.discover_spec.handle`` against an in-process
mock HTTP server that supports HEAD (the prober sends HEAD first).  The
conftest ``mock_api_server`` fixture only implements GET/POST, so this
file uses a dedicated handler.
"""

from __future__ import annotations

import asyncio
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testmind.tools import discover_spec


# ---------------------------------------------------------------------------
# Mock server with HEAD support
# ---------------------------------------------------------------------------


class _SpecProbeHandler(BaseHTTPRequestHandler):
    """Mock handler that supports HEAD and GET on a configurable route map.

    ``ROUTES`` maps ``(method, path)`` to a dict with ``status``,
    ``body`` and optional ``content_type``.  HEAD echoes the same
    status/content-type as GET but omits the body.
    """

    ROUTES: dict[tuple[str, str], dict] = {}

    def log_message(self, format, *args):  # silence stderr
        pass

    def _route(self, method: str):
        key = (method, self.path)
        route = self.ROUTES.get(key)
        if route is None:
            self.send_response(404)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", "0")
            self.end_headers()
            return None
        status = route.get("status", 200)
        ct = route.get("content_type", "application/json")
        body_obj = route.get("body", {})
        body = json.dumps(body_obj).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", ct)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        return body

    def do_HEAD(self):  # noqa: N802
        # Reuse GET routing but do not write the body.
        key = ("GET", self.path)
        route = self.ROUTES.get(key)
        if route is None:
            self.send_response(404)
            self.send_header("content-length", "0")
            self.end_headers()
            return
        status = route.get("status", 200)
        ct = route.get("content_type", "application/json")
        body = json.dumps(route.get("body", {})).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", ct)
        self.send_header("content-length", str(len(body)))
        self.end_headers()

    def do_GET(self):  # noqa: N802
        body = self._route("GET")
        if body is not None:
            self.wfile.write(body)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def spec_server():
    """Start a mock server that serves spec payloads on common paths."""
    openapi_doc = {
        "openapi": "3.0.0",
        "info": {"title": "Demo", "version": "1.0"},
        "paths": {"/users": {"get": {"responses": {"200": {"description": "ok"}}}}},
    }
    routes = {
        ("GET", "/v3/api-docs"): {"status": 200, "body": openapi_doc},
        ("GET", "/swagger.json"): {"status": 200, "body": {"swagger": "2.0"}},
    }
    _SpecProbeHandler.ROUTES = routes

    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _SpecProbeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"base_url": f"http://127.0.0.1:{port}", "routes": routes}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDiscoverSpecToolDef:
    """Verify the MCP tool metadata."""

    def test_tool_name(self):
        assert discover_spec.TOOL_NAME == "discover_spec"

    def test_tool_def_has_required_fields(self):
        td = discover_spec.TOOL_DEF
        assert td.name == "discover_spec"
        assert td.description
        assert "base_url" in td.inputSchema["properties"]
        assert td.inputSchema["required"] == ["base_url"]


class TestDiscoverSpecHandle:
    """Exercise the handle() function against a mock server."""

    def test_discovers_spec_urls(self, spec_server, tmp_path: Path):
        result = asyncio.run(
            discover_spec.handle({"base_url": spec_server["base_url"]}, config=None)
        )
        # Two spec paths are served → both should be discovered.
        found_urls = {entry["url"] for entry in result["found"]}
        assert f"{spec_server['base_url']}/v3/api-docs" in found_urls
        assert f"{spec_server['base_url']}/swagger.json" in found_urls
        assert result["base_url"] == spec_server["base_url"].rstrip("/")

    def test_no_specs_found(self, spec_server, tmp_path: Path):
        # Point at a base URL whose only routes are the spec routes, but
        # probe a *different* base URL with nothing served.
        result = asyncio.run(
            discover_spec.handle({"base_url": "http://127.0.0.1:1"}, config=None)
        )
        # Unreachable host → empty found list, no exception.
        assert result["found"] == []

    def test_handles_missing_base_url_arg(self):
        with pytest.raises(KeyError):
            asyncio.run(discover_spec.handle({}, config=None))


class TestDiscoverSpecExtended:
    """Cover the extended path probing mode."""

    def test_discovery_paths_helper(self):
        from testmind.core.spec_fetcher import _discovery_paths, DISCOVERY_PATHS_MVP, DISCOVERY_PATHS_EXTENDED

        mvp = _discovery_paths(extended=False)
        assert mvp == DISCOVERY_PATHS_MVP
        assert "/v3/api-docs" in mvp

        ext = _discovery_paths(extended=True)
        assert len(ext) == len(DISCOVERY_PATHS_MVP) + len(DISCOVERY_PATHS_EXTENDED)
        # MVP paths come first, extended paths appended.
        assert ext[: len(DISCOVERY_PATHS_MVP)] == DISCOVERY_PATHS_MVP
        # Extended-only paths are present.
        assert "/.well-known/openapi" in ext
        assert "/api-docs/default" in ext

    def test_extended_probes_more_paths(self, tmp_path: Path):
        """extended=True discovers a URL only present in the extended list."""
        # Build a mock server that only serves an extended-only path.
        openapi_doc = {"openapi": "3.0.0", "info": {"title": "X", "version": "1"}, "paths": {}}
        _SpecProbeHandler.ROUTES = {
            ("GET", "/.well-known/openapi"): {"status": 200, "body": openapi_doc},
        }
        port = _free_port()
        server = ThreadingHTTPServer(("127.0.0.1", port), _SpecProbeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{port}"
        try:
            # MVP-only probe misses it.
            r_mvp = asyncio.run(discover_spec.handle({"base_url": base}, config=None))
            assert r_mvp["found"] == []
            # Extended probe finds it.
            r_ext = asyncio.run(
                discover_spec.handle({"base_url": base, "extended": True}, config=None)
            )
            urls = {e["url"] for e in r_ext["found"]}
            assert f"{base}/.well-known/openapi" in urls
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_extended_count_exceeds_mvp(self, spec_server, tmp_path: Path):
        """When the server serves both MVP and extended paths, extended
        mode discovers at least as many URLs as MVP mode."""
        # Add an extended-only route to the shared server's routes.
        _SpecProbeHandler.ROUTES[("GET", "/swagger-resources")] = {
            "status": 200,
            "body": {"resources": []},
        }
        r_mvp = asyncio.run(discover_spec.handle({"base_url": spec_server["base_url"]}, config=None))
        r_ext = asyncio.run(
            discover_spec.handle({"base_url": spec_server["base_url"], "extended": True}, config=None)
        )
        assert len(r_ext["found"]) > len(r_mvp["found"])
