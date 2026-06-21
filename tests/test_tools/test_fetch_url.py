"""Unit tests for the fetch_url MCP tool.

Exercises ``testmind.tools.fetch_url.handle`` against the shared
``mock_api_server`` fixture, with routes overridden to serve spec-like
payloads on well-known paths.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from testmind.tools import fetch_url
from tests.test_tools.test_discover_spec import _SpecProbeHandler  # reuse HEAD-capable handler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFetchUrlToolDef:
    """Verify the MCP tool metadata."""

    def test_tool_name(self):
        assert fetch_url.TOOL_NAME == "fetch_url"

    def test_tool_def_has_required_fields(self):
        td = fetch_url.TOOL_DEF
        assert td.name == "fetch_url"
        assert td.description
        assert "url" in td.inputSchema["properties"]
        assert td.inputSchema["required"] == ["url"]


class TestFetchUrlHandle:
    """Exercise handle() to download content to local storage."""

    def test_fetch_json_spec(self, tmp_path: Path):
        """fetch_url downloads a JSON spec and saves it under testmind/specs/."""
        # Stand up a tiny mock server with a spec payload.
        import socket
        import threading
        from http.server import ThreadingHTTPServer

        port_socket = socket.socket()
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
        port_socket.close()

        openapi_body = {"openapi": "3.0.0", "info": {"title": "X", "version": "1"}}
        _SpecProbeHandler.ROUTES = {
            ("GET", "/openapi.json"): {"status": 200, "body": openapi_body},
        }
        server = ThreadingHTTPServer(("127.0.0.1", port), _SpecProbeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{port}/openapi.json"
            result = asyncio.run(fetch_url.handle({"url": url}, config=None))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        assert result["url"] == url
        assert result["format"] == "json"
        assert result["size_bytes"] > 0
        # File is saved under cwd/testmind/specs/ (cwd is pinned to tmp_path).
        saved = Path(result["file_path"])
        assert saved.is_file()
        assert saved.read_text(encoding="utf-8") == json.dumps(openapi_body)

    def test_fetch_nonexistent_url_raises(self):
        """A 404 response raises an HTTPError via raise_for_status()."""
        import socket
        import threading
        from http.server import ThreadingHTTPServer

        port_socket = socket.socket()
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
        port_socket.close()

        _SpecProbeHandler.ROUTES = {}  # no routes → 404
        server = ThreadingHTTPServer(("127.0.0.1", port), _SpecProbeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with pytest.raises(Exception):
                asyncio.run(
                    fetch_url.handle({"url": f"http://127.0.0.1:{port}/missing.json"}, config=None)
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_missing_url_arg_raises(self):
        with pytest.raises(KeyError):
            asyncio.run(fetch_url.handle({}, config=None))
