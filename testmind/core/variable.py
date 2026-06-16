from __future__ import annotations

import re
import string
import uuid
from datetime import datetime
from random import randint, choices
from typing import Any


_BUILTIN_FUNCTIONS: dict[str, Any] = {}


def _timestamp() -> str:
    return str(int(datetime.now().timestamp()))


def _uuid() -> str:
    return str(uuid.uuid4())


def _random_int() -> str:
    return str(randint(10000, 99999))


def _random_string(length: int = 8) -> str:
    return "".join(choices(string.ascii_letters + string.digits, k=length))


def _random_email() -> str:
    return f"test_{_timestamp()}@example.com"


_BUILTIN_FUNCTIONS = {
    "timestamp": _timestamp,
    "uuid": _uuid,
    "random_int": _random_int,
    "random_string": _random_string,
    "random_email": _random_email,
}

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")
_RESPONSE_VAR_PATTERN = re.compile(r"\{\{\$response\.(body|headers?|status_code)(?:\.(.+?))?\}\}")


def replace_variables(data: Any, context: dict[str, Any]) -> Any:
    if isinstance(data, str):
        return _replace_string(data, context)
    if isinstance(data, dict):
        return {k: replace_variables(v, context) for k, v in data.items()}
    if isinstance(data, list):
        return [replace_variables(item, context) for item in data]
    return data


def _replace_string(text: str, context: dict[str, Any]) -> str:
    text = _RESPONSE_VAR_PATTERN.sub(lambda m: _resolve_response_var(m, context), text)
    text = _VAR_PATTERN.sub(lambda m: _resolve_var(m.group(1), context), text)
    return text


def _resolve_var(name: str, context: dict[str, Any]) -> str:
    if name in context:
        return str(context[name])
    if name in _BUILTIN_FUNCTIONS:
        result = _BUILTIN_FUNCTIONS[name]
        return result() if callable(result) else str(result)
    return ""


def _resolve_response_var(match: re.Match, context: dict[str, Any]) -> str:
    part = match.group(1)
    path = match.group(2)
    response = context.get("$response")
    if response is None:
        return ""
    if part == "status_code":
        return str(response.get("status_code", ""))
    if part == "body":
        if path is None:
            return str(response.get("body", ""))
        return str(_resolve_jsonpath(response.get("body", {}), path))
    if part in ("header", "headers"):
        headers = response.get("headers", {})
        if path:
            return str(headers.get(path, ""))
        return str(headers)
    return ""


def _resolve_jsonpath(obj: Any, path: str) -> Any:
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return ""
        else:
            return ""
        if current is None:
            return ""
    return current


def extract_variables(response_data: dict, extract_defs: dict[str, dict]) -> dict[str, str]:
    result: dict[str, str] = {}
    for var_name, extract_def in extract_defs.items():
        ext_type = extract_def.get("type", "jsonpath")
        path = extract_def.get("path", "")
        if ext_type == "jsonpath":
            value = _resolve_jsonpath(response_data.get("body", {}), path.lstrip("$."))
            result[var_name] = str(value) if value is not None else ""
        elif ext_type == "header":
            headers = response_data.get("headers", {})
            header_name = extract_def.get("name", path)
            result[var_name] = str(headers.get(header_name, ""))
        elif ext_type == "regex":
            import re as _re
            pattern = extract_def.get("pattern", path)
            body_str = str(response_data.get("body", ""))
            match = _re.search(pattern, body_str)
            result[var_name] = match.group(1) if match and match.lastindex else ""
        elif ext_type == "status_code":
            result[var_name] = str(response_data.get("status_code", ""))
    return result


def build_variable_context(
    cli_vars: dict[str, Any] | None = None,
    env_vars: dict[str, Any] | None = None,
    project_vars: dict[str, Any] | None = None,
    case_vars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a merged variable context respecting priority order.

    Priority (highest → lowest):
    1. CLI arguments (``cli_vars``) – ``--var key=value``
    2. Environment config (``env_vars``) – ``envs/{env}.json``
    3. Project config (``project_vars``) – ``project.json``
    4. Case-local variables (``case_vars``)
    5. Built-in variables are resolved at replacement time by
       :func:`_resolve_var`.
    """
    ctx: dict[str, Any] = {}
    # Apply in order of increasing priority so higher-priority sources
    # overwrite lower-priority ones.
    for src in (case_vars, project_vars, env_vars, cli_vars):
        if src:
            ctx.update(src)
    return ctx
