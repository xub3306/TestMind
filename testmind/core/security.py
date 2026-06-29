"""Security testing engine — automated vulnerability scanning.

Sends common attack payloads (SQL injection, XSS, path traversal) against
HTTP endpoints and reports potential vulnerabilities based on response
patterns.  Designed as a quick first-pass scanner — it does NOT replace
a dedicated security tool like OWASP ZAP or Burp Suite.

Payload libraries sourced from OWASP and community-standard test suites.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Payload libraries
# ---------------------------------------------------------------------------

SQLI_PAYLOADS = [
    "' OR '1'='1",
    "' OR 1=1 --",
    "'; DROP TABLE users; --",
    "admin'--",
    "1' OR '1'='1' --",
    "' UNION SELECT NULL--",
    "' UNION SELECT username, password FROM users--",
    "1; SELECT SLEEP(5)",
    "' AND 1=1 --",
    "' AND 1=2 --",
    "\" OR \"1\"=\"1",
    "1') OR ('1'='1",
    "\" OR 1=1 --",
]

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "\"><script>alert(1)</script>",
    "<svg onload=alert(1)>",
    "'><script>alert(1)</script>",
    "<body onload=alert(1)>",
    "<iframe src=javascript:alert(1)>",
]

PATH_TRAVERSAL_PAYLOADS = [
    "../../../etc/passwd",
    "..\\..\\..\\windows\\win.ini",
    "....//....//....//etc/passwd",
    "..;/..;/..;/etc/passwd",
    "/etc/passwd%00",
]

# Patterns that suggest a successful SQL injection.
SQLI_DETECTORS = [
    re.compile(r"SQL\s*syntax", re.IGNORECASE),
    re.compile(r"mysql_fetch", re.IGNORECASE),
    re.compile(r"ORA-\d{5}", re.IGNORECASE),
    re.compile(r"PostgreSQL.*ERROR", re.IGNORECASE),
    re.compile(r"sqlite3\.OperationalError", re.IGNORECASE),
    re.compile(r"unclosed quotation", re.IGNORECASE),
]

# Patterns that suggest a reflected XSS (payload appears in response).
# We check each payload against the response body — if the raw payload
# is echoed back, it likely means the site does not encode output.
XSS_DETECT_REFLEXIVE = True  # check for payload in response body

# Patterns that indicate a successful path traversal.
PATH_TRAVERSAL_DETECTORS = [
    re.compile(r"root:.*:0:0:", re.IGNORECASE),   # /etc/passwd
    re.compile(r"\[fonts\]", re.IGNORECASE),       # win.ini
    re.compile(r"\[extensions\]", re.IGNORECASE),  # win.ini
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ScanResult:
    """Container for a single vulnerability finding."""

    def __init__(self, category: str, payload: str, url: str, detail: str) -> None:
        self.category = category
        self.payload = payload
        self.url = url
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "payload": self.payload,
            "url": self.url,
            "detail": self.detail,
        }


class SecurityReport:
    """Aggregated report from a security scan."""

    def __init__(self, base_url: str, findings: list[ScanResult],
                 scanned_count: int = 0) -> None:
        self.base_url = base_url
        self.findings = findings
        self.scanned_count = scanned_count
        self.scanned_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "scanned_at": self.scanned_at,
            "total_payloads": self.scanned_count,
            "vulnerabilities_found": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
        }


def run_security_scan(
    base_url: str,
    path: str = "/api/users",
    param_name: str = "q",
    timeout: float = 10,
    include_sqli: bool = True,
    include_xss: bool = True,
    include_path_traversal: bool = True,
) -> dict[str, Any]:
    """Run a security scan against *base_url + path* and return a report.

    Args:
        base_url: Root URL (e.g. ``http://localhost:8080``).
        path: Endpoint path to append.
        param_name: Query parameter name to inject payloads into.
        timeout: Per-request timeout in seconds.
        include_sqli: Whether to test SQL injection payloads.
        include_xss: Whether to test XSS payloads.
        include_path_traversal: Whether to test path traversal payloads.

    Returns a dict with keys: ``base_url``, ``scanned_at``,
    ``total_payloads``, ``vulnerabilities_found``, ``findings``.
    """
    client = httpx.Client(timeout=timeout, trust_env=False)
    findings: list[ScanResult] = []
    scanned = 0
    target_url = f"{base_url.rstrip('/')}{path}"

    # ---- SQL Injection ----
    if include_sqli:
        for payload in SQLI_PAYLOADS:
            scanned += 1
            try:
                resp = client.get(target_url, params={param_name: payload})
                body = resp.text
                for pattern in SQLI_DETECTORS:
                    if pattern.search(body):
                        findings.append(ScanResult(
                            "sql_injection", payload, target_url,
                            f"Response matched pattern: {pattern.pattern}"
                        ))
                        break
            except Exception:
                pass

    # ---- XSS ----
    if include_xss:
        for payload in XSS_PAYLOADS:
            scanned += 1
            try:
                resp = client.get(target_url, params={param_name: payload})
                body = resp.text
                if XSS_DETECT_REFLEXIVE and payload in body:
                    findings.append(ScanResult(
                        "xss_reflected", payload, target_url,
                        "Payload reflected in response body"
                    ))
            except Exception:
                pass

    # ---- Path Traversal ----
    if include_path_traversal:
        for payload in PATH_TRAVERSAL_PAYLOADS:
            scanned += 1
            try:
                resp = client.get(target_url, params={param_name: payload})
                body = resp.text
                for pattern in PATH_TRAVERSAL_DETECTORS:
                    if pattern.search(body):
                        findings.append(ScanResult(
                            "path_traversal", payload, target_url,
                            f"Response matched: {pattern.pattern}"
                        ))
                        break
            except Exception:
                pass

    report = SecurityReport(base_url, findings, scanned)
    return report.to_dict()
