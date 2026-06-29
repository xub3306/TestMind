"""Tests for the security scanning engine (testmind.core.security)."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from testmind.core.security import run_security_scan
from testmind.cli import main


# ---------------------------------------------------------------------------
# Mock servers
# ---------------------------------------------------------------------------


class _VulnHandler(BaseHTTPRequestHandler):
    """Echoes back the query parameter — simulates a reflected XSS vuln."""
    def log_message(self, *a): pass
    def do_GET(self):
        import urllib.parse
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        body = qs.get("q", [""])[0]
        resp = f"<html><body>Search: {body}</body></html>".encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.send_header("content-length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


class _SafeHandler(BaseHTTPRequestHandler):
    """Escapes output — no vulnerability."""
    def log_message(self, *a): pass
    def do_GET(self):
        import html
        import urllib.parse
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        body = html.escape(qs.get("q", [""])[0])
        resp = f"<html><body>Search: {body}</body></html>".encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.send_header("content-length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


def _start_server(handler_class) -> str:
    port_socket = socket.socket()
    port_socket.bind(("127.0.0.1", 0))
    port = port_socket.getsockname()[1]
    port_socket.close()
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}", server, thread


@pytest.fixture()
def vuln_server():
    base, server, thread = _start_server(_VulnHandler)
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def safe_server():
    base, server, thread = _start_server(_SafeHandler)
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSecurityScan:
    def test_xss_detected_on_vulnerable(self, vuln_server):
        report = run_security_scan(vuln_server, path="/search", param_name="q",
                                   include_sqli=False, include_path_traversal=False)
        assert report["vulnerabilities_found"] > 0
        categories = {f["category"] for f in report["findings"]}
        assert "xss_reflected" in categories

    def test_xss_not_detected_on_safe(self, safe_server):
        report = run_security_scan(safe_server, path="/search", param_name="q",
                                   include_sqli=False, include_path_traversal=False)
        assert report["vulnerabilities_found"] == 0

    def test_sqli_payloads_sent(self, vuln_server):
        report = run_security_scan(vuln_server, path="/search", param_name="q",
                                   include_sqli=True, include_xss=False, include_path_traversal=False)
        assert report["total_payloads"] > 0

    def test_no_xss_when_disabled(self, vuln_server):
        report = run_security_scan(vuln_server, path="/search", param_name="q",
                                   include_sqli=False, include_xss=False, include_path_traversal=False)
        assert report["total_payloads"] == 0
        assert report["vulnerabilities_found"] == 0


class TestCliSecurity:
    def test_scan_command(self, vuln_server):
        runner = CliRunner()
        result = runner.invoke(main, [
            "security", "scan", vuln_server, "--path", "/search", "--no-sqli", "--no-traversal",
        ])
        assert result.exit_code == 0
        assert "Payloads sent:" in result.output
