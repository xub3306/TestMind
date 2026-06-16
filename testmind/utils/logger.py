from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SENSITIVE_URL_PARAMS = {
    "token", "access_token", "refresh_token", "api_key", "apikey",
    "secret", "password", "passwd", "pwd", "auth", "key", "credential",
}

_AUTH_HEADER_PATTERN = re.compile(
    r"^(authorization|proxy-authorization|x-api-key)$", re.IGNORECASE
)


def sanitize_url(url: str) -> str:
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)

    sanitized: dict[str, list[str]] = {}
    for key, values in qs.items():
        if key.lower() in _SENSITIVE_URL_PARAMS:
            sanitized[key] = ["***"]
        else:
            sanitized[key] = values

    new_query = urlencode(sanitized, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers.items():
        if _AUTH_HEADER_PATTERN.match(key):
            result[key] = "***"
        else:
            result[key] = value
    return result


def _sanitize_record(record: logging.LogRecord) -> bool:
    msg = record.getMessage()
    record.msg = _sanitize_string(msg)
    record.args = ()
    return True


def _sanitize_string(text: str) -> str:
    text = re.sub(
        r'(token["\s:=]+)([^\s"\',;}&]+)',
        r'\1***',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'(password["\s:=]+)([^\s"\',;}&]+)',
        r'\1***',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'(Authorization["\s:=]+)([^\s"\',;}&]+)',
        r'\1***',
        text,
        flags=re.IGNORECASE,
    )
    return text


class _SanitizingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _sanitize_string(str(record.msg))
        if record.args:
            record.args = tuple(
                _sanitize_string(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True


class _AuditLogger:
    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._path = log_dir / "audit.jsonl"

    def log(
        self,
        tool: str,
        input_data: Any,
        output_data: Any,
        duration_ms: float,
        status: str,
        caller: str = "",
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "input": _sanitize_string(str(input_data)),
            "output": _sanitize_string(str(output_data)),
            "duration_ms": round(duration_ms, 2),
            "status": status,
            "caller": caller,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class AuditContext:
    def __init__(self, audit: _AuditLogger, tool: str, input_data: Any, caller: str = "") -> None:
        self._audit = audit
        self._tool = tool
        self._input = input_data
        self._caller = caller
        self._start: float = 0

    def __enter__(self) -> "AuditContext":
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration_ms = (time.monotonic() - self._start) * 1000
        status = "error" if exc_type else "ok"
        self._audit.log(
            tool=self._tool,
            input_data=self._input,
            output_data=str(exc_val) if exc_val else "",
            duration_ms=duration_ms,
            status=status,
            caller=self._caller,
        )


def setup_logger(
    name: str = "testmind",
    level: int = logging.INFO,
) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    sanitizing_filter = _SanitizingFilter()
    logger.addFilter(sanitizing_filter)

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    console_handler.addFilter(sanitizing_filter)
    logger.addHandler(console_handler)

    run_handler = logging.FileHandler(
        log_dir / "testmind.log", encoding="utf-8"
    )
    run_handler.setLevel(logging.INFO)
    run_handler.setFormatter(console_fmt)
    run_handler.addFilter(sanitizing_filter)
    logger.addHandler(run_handler)

    debug_handler = logging.FileHandler(
        log_dir / "debug.log", encoding="utf-8"
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    debug_handler.setFormatter(debug_fmt)
    debug_handler.addFilter(sanitizing_filter)
    logger.addHandler(debug_handler)

    return logger


def get_audit_logger(log_dir: Path | None = None) -> _AuditLogger:
    if log_dir is None:
        log_dir = Path("logs")
    return _AuditLogger(log_dir)


def get_run_logger(name: str = "testmind.runner", level: int = logging.INFO) -> logging.Logger:
    """Get a logger for the test run engine.

    This is a convenience wrapper around :func:`setup_logger` that
    returns a logger with the given *name*.
    """
    return setup_logger(name, level)
